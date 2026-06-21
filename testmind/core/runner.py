"""TestMind core execution engine.

Execution flow (REQUIREMENTS.md §15):
1. Load config (project.json + envs/{env}.json → merge)
1.5 Run setup hooks
2. Collect cases (scan cases/, filter by target/tags/suite, skip disabled/environments/skip_if)
3. Topological sort (resolve depends, detect cycles)
4. Variable replacement (replace {{var}})
5. Execute cases (before hooks → api_request → extract_var → assertions → after hooks)
5.5 Run teardown hooks
6. Generate results (write to results/{run_id}/)

run_id format: ``{YYYYMMDD}_{HHMMSS}_{random4}``

Variable priority (high → low):
1. CLI --var key=value
2. Environment config envs/{env}.json
3. Project config project.json
4. Case-local variables
5. Built-in variables (timestamp, uuid, random_int, random_string, random_email)

Result output:
    results/20260608_143022/
    ├── summary.json
    ├── TC-API-USERS-001.json
    ├── TC-API-USERS-001_retry_1.json  (if retried)
    └── ...
"""

import asyncio
import hashlib
import json
import os
import random
import string
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from testmind.config.settings import ProjectConfig, load_project_config
from testmind.models.result import AssertionResult, CaseResult, RequestSnapshot, ResponseSnapshot, SummaryResult
from testmind.models.testcase import TestCase
from testmind.utils.logger import get_audit_logger, get_run_logger


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_ALL_PASS = 0
EXIT_HAS_FAIL = 1
EXIT_HAS_ERROR = 2
EXIT_CONFIG_ERROR = 10
EXIT_MCP_SERVER_FAIL = 20


def _workspace_dir(config: ProjectConfig) -> Path:
    """Resolve the ``testmind/`` workspace directory for *config*.

    Prefers ``config.project_dir`` (populated by
    :func:`load_project_config`) so that case/result discovery works
    independent of the current working directory.  Falls back to the
    current working directory when ``project_dir`` is unset, preserving
    backward compatibility with unit tests that build a bare
    :class:`ProjectConfig`.
    """
    root = config.project_dir if config.project_dir is not None else Path(os.getcwd())
    return root / "testmind"


class Runner:
    """Core test execution engine.

    Supports serial and concurrent execution modes.  When ``workers > 1``,
    cases that share the same dependency *layer* (same depth in the topology)
    are executed concurrently using ``asyncio``.
    """

    def __init__(self, config: ProjectConfig) -> None:
        self.config = config
        self.logger = get_run_logger("testmind.runner")

    # ------------------------------------------------------------------
    # Workspace resolution
    # ------------------------------------------------------------------

    def _get_workspace(self) -> Path:
        """Resolve the project workspace root.

        Prefers the config's resolved ``project_dir`` (set by
        :func:`load_project_config`) so that the runner works correctly
        regardless of the current working directory — this is essential
        for the MCP server, which may be launched from any directory.
        Falls back to the current working directory when ``project_dir``
        is unset (e.g. in unit tests that construct a bare
        :class:`ProjectConfig`).
        """
        return _workspace_dir(self.config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        env: str | None = None,
        tags: list[str] | None = None,
        target: str | None = None,
        suite: str | None = None,
        fail_fast: int = 0,
        workers: int = 1,
        retry: int | None = None,
        device: str | None = None,
        devices: list[str] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> str:
        """Run collected test cases synchronously.

        Returns the ``run_id`` for result retrieval.

        When *suite* is provided, the suite's own ``setup`` / ``teardown``
        hooks are executed around the run, and the suite's ``workers``,
        ``retry`` and ``fail_fast`` fields override the corresponding
        arguments when set.
        """
        env_name = env or self.config.default_env
        env_config = self.config.get_env_config(env_name)
        run_id = _generate_run_id()
        self.logger.info(f"Starting run {run_id} with env={env_name}")

        # Load the suite definition (if any) so we can apply its strategy
        # overrides and setup/teardown hooks.  ``_collect_cases`` also
        # loads it, but we load it here once to avoid double disk I/O.
        suite_obj = self._load_suite(suite) if suite else None

        cases = self._collect_cases(target=target, tags=tags, suite=suite)
        cases = self._filter_cases(cases, env_name=env_name)
        ordered = self._topological_sort(cases)

        results_dir = self._get_results_dir(run_id)
        results_dir.mkdir(parents=True, exist_ok=True)

        # Apply suite-level strategy overrides (None = keep caller value).
        if suite_obj is not None:
            if suite_obj.workers is not None:
                workers = suite_obj.workers
            if suite_obj.retry is not None:
                retry = suite_obj.retry
            if suite_obj.fail_fast is not None:
                fail_fast = suite_obj.fail_fast

        retry_count = retry if retry is not None else self.config.retry
        context = self._build_context(env_config, variables or {})
        consecutive_failures = 0
        all_results: list[CaseResult] = []
        summary = SummaryResult(
            run_id=run_id,
            project=self.config.name,
            env=env_name,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at="",
            total=0,
            passed=0,
            failed=0,
            error=0,
            skipped=0,
            total_duration_ms=0,
            failures=[],
            errors=[],
        )

        # Global setup (project-level) runs first.
        self._execute_setup(context)

        # Suite-level setup hooks run after project setup but before any
        # case executes.  Errors here abort the run (same semantics as
        # before-hooks on individual cases).
        suite_setup_failed = False
        if suite_obj is not None and suite_obj.setup:
            try:
                from testmind.core.hooks import execute_hooks
                execute_hooks(suite_obj.setup, context, "before")
            except Exception as e:
                self.logger.error(f"Suite setup hook failed: {e}")
                suite_setup_failed = True

        try:
            if suite_setup_failed:
                # Skip case execution; teardown still runs.
                self.logger.info("Skipping case execution due to suite setup failure")
            elif workers > 1:
                # Concurrent execution: split into layers by topology, run each layer concurrently
                self._execute_concurrent(ordered, context, run_id, env_name, retry_count, workers, all_results, summary, fail_fast)
            else:
                # Serial execution
                for case in ordered:
                    result = self._run_single_case(case, context, run_id, env_name, retry_count, all_results, results_dir)
                    all_results.append(result)
                    self._update_summary(summary, result)

                    if result.status == "fail":
                        consecutive_failures += 1
                    else:
                        consecutive_failures = 0

                    if fail_fast > 0 and consecutive_failures >= fail_fast:
                        self.logger.info(f"Fail-fast triggered after {consecutive_failures} consecutive failures")
                        break
        finally:
            # Suite-level teardown (best-effort, errors are logged but not raised).
            if suite_obj is not None and suite_obj.teardown:
                try:
                    from testmind.core.hooks import execute_hooks
                    execute_hooks(suite_obj.teardown, context, "after")
                except Exception as e:
                    self.logger.warning(f"Suite teardown hook error: {e}")
            self._execute_teardown(context)

        summary.total = len(all_results)
        summary.finished_at = datetime.now(timezone.utc).isoformat()

        self._save_results(results_dir, all_results, summary)
        self._print_summary(all_results, summary)
        return run_id

    async def run_async(
        self,
        env: str | None = None,
        tags: list[str] | None = None,
        target: str | None = None,
        suite: str | None = None,
        fail_fast: int = 0,
        workers: int = 1,
        retry: int | None = None,
        device: str | None = None,
        devices: list[str] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> str:
        """Asynchronous entry point – wraps :meth:`run` in an executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run(
                env=env, tags=tags, target=target, suite=suite,
                fail_fast=fail_fast, workers=workers, retry=retry,
                device=device, devices=devices, variables=variables,
            ),
        )

    def get_exit_code(self, all_results: list[CaseResult]) -> int:
        """Determine CLI exit code from results.

        Returns:
            0 if all pass, 1 if any fail, 2 if any error.
        """
        statuses = {r.status for r in all_results}
        if "error" in statuses:
            return EXIT_HAS_ERROR
        if "fail" in statuses:
            return EXIT_HAS_FAIL
        return EXIT_ALL_PASS

    def _collect_cases(self, target: str | None = None, tags: list[str] | None = None, suite: str | None = None) -> list[TestCase]:
        cases: list[TestCase] = []
        cases_dir = self._get_cases_dir()

        if suite:
            suite_cases = self._load_suite(suite)
            case_ids = set(suite_cases.cases) if suite_cases else set()
            case_dirs = suite_cases.case_dirs if suite_cases else []
        else:
            case_ids = set()
            case_dirs = []

        if case_dirs:
            for d in case_dirs:
                dir_path = cases_dir / d
                if dir_path.exists():
                    cases.extend(self._load_cases_from_dir(dir_path))

        if case_ids:
            for case_id in case_ids:
                found = self._find_case_by_id(cases_dir, case_id)
                if found and found not in cases:
                    cases.append(found)

        if not suite:
            if target:
                dir_path = cases_dir / target
                if dir_path.exists():
                    cases.extend(self._load_cases_from_dir(dir_path))
            else:
                cases.extend(self._load_cases_from_dir(cases_dir))

        if tags:
            cases = [c for c in cases if any(t in c.tags for t in tags)]

        seen_ids: set[str] = set()
        unique: list[TestCase] = []
        for c in cases:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                unique.append(c)
        return unique

    def _filter_cases(self, cases: list[TestCase], env_name: str) -> list[TestCase]:
        return [c for c in cases if not c.environments or env_name in c.environments]

    def _topological_sort(self, cases: list[TestCase]) -> list[TestCase]:
        case_map = {c.id: c for c in cases}
        visited: set[str] = set()
        ordering: list[TestCase] = []
        in_stack: set[str] = set()

        def visit(case_id: str) -> None:
            if case_id in in_stack:
                raise ValueError(f"Circular dependency detected involving {case_id}")
            if case_id in visited:
                return
            if case_id not in case_map:
                return
            in_stack.add(case_id)
            case = case_map[case_id]
            if case.depends:
                for dep_id in case.depends:
                    visit(dep_id)
            in_stack.remove(case_id)
            visited.add(case_id)
            ordering.append(case)

        for c in cases:
            visit(c.id)
        return ordering

    # ------------------------------------------------------------------
    # Single-case execution helpers
    # ------------------------------------------------------------------

    def _run_single_case(
        self,
        case: TestCase,
        context: dict,
        run_id: str,
        env_name: str,
        retry_count: int,
        all_results: list[CaseResult],
        results_dir: Path,
    ) -> CaseResult:
        """Handle skip/disabled checks, dependency checks, data-driven, then execute."""
        if case.disabled:
            return self._make_skipped_result(case, run_id, env_name, "Case is disabled")

        skip_reason = self._evaluate_skip_if(case, env_name)
        if skip_reason:
            return self._make_skipped_result(case, run_id, env_name, skip_reason)

        dep_failed = self._check_dependencies(case, all_results)
        if dep_failed:
            return self._make_skipped_result(case, run_id, env_name, f"Dependency {dep_failed} failed")

        data_driven = case.data_driven
        if data_driven:
            # For data-driven, execute and return last result; all sub-results should be
            # appended by the caller — but since this returns a single CaseResult we
            # need special handling. The caller should check data_driven separately.
            case_results = self._execute_data_driven(case, data_driven, context, run_id, env_name, retry_count)
            # Return first result; caller should extend all_results
            # Actually, we return a special marker — the caller should handle
            # data_driven explicitly. For backwards compat, return first result.
            for cr in case_results:
                all_results.append(cr)
            return case_results[-1] if case_results else self._make_error_result(
                case, run_id, env_name, datetime.now(timezone.utc).isoformat(), "Data-driven produced no results"
            )

        return self._execute_case(case, context, run_id, env_name, retry_count, results_dir)

    def _execute_case(self, case: TestCase, context: dict, run_id: str, env_name: str, retry_count: int, results_dir: Path | None = None) -> CaseResult:
        """Execute a single test case: hooks → request → extract → assertions → after hooks."""
        started_at = datetime.now(timezone.utc).isoformat()
        self.logger.info(f"Running case: {case.id} - {case.name}")

        merged_context = {**context, **(case.metadata and {} or {})}
        from testmind.core.variable import replace_variables

        request_data = replace_variables(case.request.model_dump(), merged_context)

        # Before hooks
        try:
            before_hooks = case.hooks.before if case.hooks else []
            from testmind.core.hooks import execute_hooks
            hook_result = execute_hooks(before_hooks, merged_context, "before")
            merged_context.update(hook_result)
        except Exception as e:
            return self._make_error_result(case, run_id, env_name, started_at, f"Before hook failed: {e}")

        # Send request
        try:
            response_data = self._send_request(request_data, merged_context, env_name)
        except Exception as e:
            return self._make_error_result(case, run_id, env_name, started_at, f"Request failed: {e}")

        duration_ms = response_data.get("duration_ms", 0)
        request_snapshot = RequestSnapshot(
            method=request_data.get("method", ""),
            url=response_data.get("url", ""),
            headers=request_data.get("headers") or {},
            body=(request_data.get("params") or {}).get("body"),
        )
        response_snapshot = ResponseSnapshot(
            status_code=response_data.get("status_code", 0),
            headers=response_data.get("headers", {}),
            body=response_data.get("body"),
            duration_ms=duration_ms,
        )

        # Assertions
        from testmind.core.assertion import assert_response
        assertions = assert_response(case, response_data, case.expect)

        all_passed = all(a.passed for a in assertions)
        status = "pass" if all_passed else "fail"
        actual_retry_count = 0

        # Retry: only for status=fail (not error); error does not retry
        if status == "fail" and retry_count > 0:
            for attempt in range(retry_count):
                self.logger.info(f"Retrying case {case.id}, attempt {attempt + 1}")
                import time
                time.sleep(1)  # 1-second interval between retries
                try:
                    retry_response_data = self._send_request(request_data, merged_context, env_name)
                    retry_assertions = assert_response(case, retry_response_data, case.expect)
                    if all(a.passed for a in retry_assertions):
                        status = "pass"
                        assertions = retry_assertions
                        response_snapshot = ResponseSnapshot(
                            status_code=retry_response_data.get("status_code", 0),
                            headers=retry_response_data.get("headers", {}),
                            body=retry_response_data.get("body"),
                            duration_ms=retry_response_data.get("duration_ms", 0),
                        )
                        actual_retry_count = attempt + 1
                        # Persist retry detail
                        if results_dir is not None:
                            retry_result = CaseResult(
                                case_id=case.id,
                                run_id=run_id,
                                env=env_name,
                                status="fail",
                                duration_ms=retry_response_data.get("duration_ms", 0),
                                started_at=started_at,
                                finished_at=datetime.now(timezone.utc).isoformat(),
                                request_snapshot=request_snapshot,
                                response_snapshot=ResponseSnapshot(
                                    status_code=retry_response_data.get("status_code", 0),
                                    headers=retry_response_data.get("headers", {}),
                                    body=retry_response_data.get("body"),
                                    duration_ms=retry_response_data.get("duration_ms", 0),
                                ),
                                assertions_result=retry_assertions,
                                error=None,
                                retry_count=attempt + 1,
                            )
                            retry_file = results_dir / f"{case.id}_retry_{attempt + 1}.json"
                            retry_file.write_text(retry_result.model_dump_json(indent=2), encoding="utf-8")
                        break
                except Exception:
                    continue
                # Persist retry detail for failed retry
                if results_dir is not None and status == "fail":
                    retry_result = CaseResult(
                        case_id=case.id,
                        run_id=run_id,
                        env=env_name,
                        status="fail",
                        duration_ms=0,
                        started_at=started_at,
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        request_snapshot=request_snapshot,
                        response_snapshot=None,
                        assertions_result=assertions,
                        error="Retry attempt failed",
                        retry_count=attempt + 1,
                    )
                    retry_file = results_dir / f"{case.id}_retry_{attempt + 1}.json"
                    retry_file.write_text(retry_result.model_dump_json(indent=2), encoding="utf-8")

        # Extract variables
        if case.extract:
            extracted = self._extract_variables(case.extract, response_data)
            merged_context.update(extracted)

        # After hooks (always executed, like finally)
        try:
            after_hooks = case.hooks.after if case.hooks else []
            from testmind.core.hooks import execute_hooks
            execute_hooks(after_hooks, merged_context, "after")
        except Exception as e:
            self.logger.warning(f"After hook failed for {case.id}: {e}")

        finished_at = datetime.now(timezone.utc).isoformat()
        return CaseResult(
            case_id=case.id,
            run_id=run_id,
            env=env_name,
            status=status,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
            request_snapshot=request_snapshot,
            response_snapshot=response_snapshot,
            assertions_result=assertions,
            error=None,
            retry_count=actual_retry_count,
        )

    def _execute_data_driven(self, case: TestCase, data_driven: Any, context: dict, run_id: str, env_name: str, retry_count: int) -> list[CaseResult]:
        """Execute a data-driven test case, producing one result per parameter row."""
        results: list[CaseResult] = []
        for idx, params in enumerate(data_driven.parameters):
            variant = case.model_copy(update={"id": f"{case.id}_DD{idx}"})
            for field_path in data_driven.parameterized_fields:
                parts = field_path.split(".")
                target = variant
                for part in parts[:-1]:
                    target = getattr(target, part, target)
                if hasattr(target, parts[-1]):
                    setattr(target, parts[-1], params.get(parts[-1]))
            result = self._execute_case(variant, context, run_id, env_name, retry_count)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Concurrent execution
    # ------------------------------------------------------------------

    def _execute_concurrent(
        self,
        ordered: list[TestCase],
        context: dict,
        run_id: str,
        env_name: str,
        retry_count: int,
        workers: int,
        all_results: list[CaseResult],
        summary: SummaryResult,
        fail_fast: int,
    ) -> None:
        """Execute cases concurrently using topology layers.

        Cases in the same layer (same depth in the dependency graph) are
        executed in parallel with up to *workers* concurrent tasks.
        """
        layers = self._split_into_layers(ordered)
        for layer in layers:
            # For each layer, execute cases concurrently
            if len(layer) <= 1 or workers <= 1:
                for case in layer:
                    result = self._run_single_case(
                        case, context, run_id, env_name, retry_count,
                        all_results, self._get_results_dir(run_id),
                    )
                    all_results.append(result)
                    self._update_summary(summary, result)
            else:
                # Run up to ``workers`` cases concurrently
                batch_size = min(workers, len(layer))
                with ThreadPoolExecutor(max_workers=batch_size) as executor:
                    futures = []
                    for case in layer:
                        fut = executor.submit(
                            self._run_single_case,
                            case, context, run_id, env_name, retry_count,
                            all_results, self._get_results_dir(run_id),
                        )
                        futures.append(fut)
                    for fut in futures:
                        result = fut.result()
                        all_results.append(result)
                        self._update_summary(summary, result)

    def _split_into_layers(self, ordered: list[TestCase]) -> list[list[TestCase]]:
        """Split topologically-sorted cases into layers for concurrent execution.

        Cases in the same layer have no dependency on each other and can
        be executed in parallel.
        """
        case_map = {c.id: c for c in ordered}
        depth: dict[str, int] = {}

        def get_depth(case_id: str) -> int:
            if case_id in depth:
                return depth[case_id]
            if case_id not in case_map:
                return 0
            case = case_map[case_id]
            if not case.depends:
                depth[case_id] = 0
                return 0
            max_dep = max(get_depth(d) for d in case.depends)
            depth[case_id] = max_dep + 1
            return depth[case_id]

        for c in ordered:
            get_depth(c.id)

        # Group by depth
        layers_dict: dict[int, list[TestCase]] = defaultdict(list)
        for c in ordered:
            layers_dict[depth.get(c.id, 0)].append(c)

        max_depth = max(depth.values()) if depth else 0
        return [layers_dict[d] for d in range(max_depth + 1)]

    def _send_request(self, request_data: dict, context: dict, env_name: str) -> dict:
        """Send an HTTP request and return the response data dict."""
        base_url = context.get("base_url", self.config.base_url)
        method = request_data.get("method", "GET").upper()
        path = request_data.get("path", "/")
        url = f"{base_url}{path}"

        headers = dict(request_data.get("headers") or {})
        auth_header = self._build_auth_header(env_name)
        if auth_header:
            headers.update(auth_header)

        proxy = None
        if self.config.proxy:
            proxy = self.config.proxy.https or self.config.proxy.http

        verify = self.config.verify_ssl

        params = request_data.get("params") or {}
        body = params.get("body")
        query = params.get("query")
        timeout = float(context.get("timeout", self.config.timeout))

        start = datetime.now(timezone.utc)
        # Use an explicit Client so that ``trust_env`` is under our
        # control.  When the project does not configure a proxy we set
        # ``trust_env=False`` to avoid silently inheriting the OS-level
        # proxy (e.g. IE/Edge settings on Windows), which can reroute
        # localhost traffic and produce misleading 502 responses.  When
        # the user explicitly configures a proxy we still disable
        # ``trust_env`` and rely on the provided ``proxy`` argument so
        # behaviour stays deterministic across machines.
        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "verify": verify,
            "trust_env": False,
        }
        if proxy:
            client_kwargs["proxy"] = proxy
        with httpx.Client(**client_kwargs) as client:
            response = client.request(
                method=method,
                url=url,
                headers=headers,
                json=body if isinstance(body, dict) else None,
                params=query if isinstance(query, dict) else None,
            )
        end = datetime.now(timezone.utc)
        duration_ms = int((end - start).total_seconds() * 1000)

        response_body: Any
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text
        else:
            response_body = response.text

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response_body,
            "duration_ms": duration_ms,
            "url": str(response.url),
        }

    def _build_auth_header(self, env_name: str) -> dict[str, str]:
        auth = self.config.auth
        env_config = self.config.get_env_config(env_name) if env_name != self.config.default_env else None
        if env_config and env_config.auth:
            auth = env_config.auth
        if not auth or auth.type == "none":
            return {}
        if auth.type == "bearer":
            token = os.environ.get(auth.token_env or "", "")
            return {"Authorization": f"Bearer {token}"}
        if auth.type == "basic":
            import base64
            username = os.environ.get(auth.username_env or "", "")
            password = os.environ.get(auth.password_env or "", "")
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        if auth.type == "api_key":
            key = os.environ.get(auth.key_env or "", "")
            header_name = auth.header_name or "X-API-Key"
            return {header_name: key}
        return {}

    def _extract_variables(self, extract: dict, response_data: dict) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for var_name, spec in extract.items():
            if spec.type == "jsonpath":
                from jsonpath_ng import parse
                matches = parse(spec.path).find(response_data.get("body", {}))
                result[var_name] = matches[0].value if matches else None
            elif spec.type == "header":
                headers = response_data.get("headers", {})
                result[var_name] = headers.get(spec.name or spec.path, "")
        return result

    def _evaluate_skip_if(self, case: TestCase, env_name: str) -> str | None:
        if not case.skip_if:
            return None
        for condition in case.skip_if:
            if condition.condition == f"env == '{env_name}'":
                return condition.reason
        return None

    def _check_dependencies(self, case: TestCase, results: list[CaseResult]) -> str | None:
        if not case.depends:
            return None
        result_map = {r.case_id: r for r in results}
        for dep_id in case.depends:
            dep_result = result_map.get(dep_id)
            if dep_result and dep_result.status in ("fail", "error", "skipped"):
                return dep_id
        return None

    def _make_skipped_result(self, case: TestCase, run_id: str, env_name: str, reason: str) -> CaseResult:
        now = datetime.now(timezone.utc).isoformat()
        return CaseResult(
            case_id=case.id,
            run_id=run_id,
            env=env_name,
            status="skipped",
            duration_ms=0,
            started_at=now,
            finished_at=now,
            request_snapshot=None,
            response_snapshot=None,
            assertions_result=[],
            error=reason,
            retry_count=0,
        )

    def _make_error_result(self, case: TestCase, run_id: str, env_name: str, started_at: str, error: str) -> CaseResult:
        now = datetime.now(timezone.utc).isoformat()
        return CaseResult(
            case_id=case.id,
            run_id=run_id,
            env=env_name,
            status="error",
            duration_ms=0,
            started_at=started_at,
            finished_at=now,
            request_snapshot=None,
            response_snapshot=None,
            assertions_result=[],
            error=error,
            retry_count=0,
        )

    def _update_summary(self, summary: SummaryResult, result: CaseResult) -> None:
        if result.status == "pass":
            summary.passed += 1
        elif result.status == "fail":
            summary.failed += 1
            summary.failures.append({"case_id": result.case_id, "reason": result.error or "Assertion failed"})
        elif result.status == "error":
            summary.error += 1
            summary.errors.append({"case_id": result.case_id, "reason": result.error or "Unknown error"})
        summary.total_duration_ms += result.duration_ms

    def _execute_setup(self, context: dict) -> None:
        if not self.config.setup:
            return
        from testmind.core.hooks import execute_hooks
        execute_hooks(self.config.setup, context, "setup")

    def _execute_teardown(self, context: dict) -> None:
        if not self.config.teardown:
            return
        from testmind.core.hooks import execute_hooks
        try:
            execute_hooks(self.config.teardown, context, "teardown")
        except Exception as e:
            self.logger.warning(f"Teardown hook failed: {e}")

    def _build_context(self, env_config: Any, variables: dict[str, Any]) -> dict:
        context: dict[str, Any] = {}
        # Expose the resolved project_dir so hook scripts can locate
        # project resources (hooks/, cases/, etc.) without relying on
        # the current working directory.
        if self.config.project_dir is not None:
            context["project_dir"] = str(self.config.project_dir)
        context.update(self.config.variables or {})
        if env_config and hasattr(env_config, "variables"):
            context.update(env_config.variables or {})
        context.update(variables)
        if env_config and hasattr(env_config, "base_url") and env_config.base_url:
            context["base_url"] = env_config.base_url
        else:
            context["base_url"] = self.config.base_url
        return context

    def _get_cases_dir(self) -> Path:
        workspace = self._get_workspace()
        return workspace / "cases"

    def _get_results_dir(self, run_id: str) -> Path:
        workspace = self._get_workspace()
        return workspace / "results" / run_id

    def _load_cases_from_dir(self, dir_path: Path) -> list[TestCase]:
        cases: list[TestCase] = []
        if not dir_path.exists():
            return cases
        for json_file in dir_path.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if "id" in data and "request" in data:
                    cases.append(TestCase(**data))
            except Exception as e:
                self.logger.warning(f"Failed to load case from {json_file}: {e}")
        return cases

    def _find_case_by_id(self, cases_dir: Path, case_id: str) -> TestCase | None:
        for json_file in cases_dir.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if data.get("id") == case_id:
                    return TestCase(**data)
            except Exception:
                continue
        return None

    def _load_suite(self, suite_name: str) -> Any:
        from testmind.models.suite import TestSuite
        suites_dir = self._get_cases_dir().parent / "suites"
        suite_file = suites_dir / f"{suite_name}.json"
        if suite_file.exists():
            data = json.loads(suite_file.read_text(encoding="utf-8"))
            return TestSuite(**data)
        return None

    def _save_results(self, results_dir: Path, results: list[CaseResult], summary: SummaryResult) -> None:
        results_dir.mkdir(parents=True, exist_ok=True)
        for result in results:
            result_file = results_dir / f"{result.case_id}.json"
            result_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        summary_file = results_dir / "summary.json"
        summary_file.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        # Generate a self-contained HTML report alongside the JSON files
        # so users can open it directly from the filesystem.  Failure to
        # generate the report must not fail the run.
        try:
            from testmind.core.report import generate_html_report
            generate_html_report(results_dir)
        except Exception as e:
            self.logger.warning(f"HTML report generation failed: {e}")

    def _print_summary(self, all_results: list[CaseResult], summary: SummaryResult) -> None:
        """Print a human-readable summary of the run.

        Uses ASCII status icons rather than Unicode glyphs (✓/✗/○) so
        output stays safe on Windows legacy consoles that default to a
        non-UTF-8 code page (e.g. GBK), where the Unicode symbols would
        raise :class:`UnicodeEncodeError`.
        """
        from rich.console import Console

        console = Console()
        console.print(f"\n{'='*50}")
        console.print(f"TestMind Run: {summary.run_id}")
        console.print(f"Project: {summary.project}  Env: {summary.env}")
        console.print(f"{'='*50}")
        # ASCII icons for cross-platform terminal safety.
        icon = {
            "pass": "[green]PASS[/green]",
            "fail": "[red]FAIL[/red]",
            "error": "[yellow]ERR ![/yellow]",
            "skipped": "[dim]SKIP[/dim]",
        }.get  # type: ignore[assignment]
        for result in all_results:
            console.print(f"  {icon(result.status, '?')} {result.case_id}: {result.status} ({result.duration_ms}ms)")
        console.print(f"\nTotal: {summary.total}  Pass: {summary.passed}  Fail: {summary.failed}  Error: {summary.error}  Skip: {summary.skipped}")
        console.print(f"Duration: {summary.total_duration_ms}ms")
        if summary.failures:
            console.print("\nFailed cases:")
            for f in summary.failures:
                console.print(f"  {f['case_id']}: {f['reason']}")
        if summary.errors:
            console.print("\nError cases:")
            for e in summary.errors:
                console.print(f"  {e['case_id']}: {e['reason']}")
        console.print(f"\nRun ID: {summary.run_id}")
        console.print(f"Results saved to: {self._get_results_dir(summary.run_id)}")


def _generate_run_id() -> str:
    now = datetime.now()
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{suffix}"


class _ValidationResult:
    """Lightweight validation result for :func:`validate_single_case`."""

    def __init__(self, valid: bool, errors: list[str] | None = None, case_id: str = "") -> None:
        self.valid = valid
        self.errors = errors or []
        self.case_id = case_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "valid": self.valid,
            "errors": self.errors,
        }


def validate_single_case(case_json: dict) -> _ValidationResult:
    """Validate a single test case JSON against the TestCase schema.

    This is used by the MCP server (``server.py``) to validate
    cases before saving.
    """
    from testmind.config.schema import TESTCASE_SCHEMA, validate_json
    schema_result = validate_json(case_json, TESTCASE_SCHEMA)
    errors = schema_result.errors if not schema_result.valid else []

    # Also try Pydantic model validation
    if schema_result.valid:
        try:
            TestCase(**case_json)
        except Exception as e:
            errors.append(str(e))

    return _ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        case_id=case_json.get("id", "unknown"),
    )


def get_results(config: ProjectConfig, run_id: str | None = None, status_filter: str | None = None) -> list[CaseResult]:
    results_dir = _workspace_dir(config) / "results"
    if run_id:
        results_dir = results_dir / run_id
        if not results_dir.exists():
            return []
    results: list[CaseResult] = []
    for result_file in results_dir.rglob("*.json"):
        if result_file.name == "summary.json":
            continue
        # Skip retry detail files (e.g. TC-X_retry_1.json) — those are
        # per-attempt snapshots, not top-level case results.
        if "_retry_" in result_file.stem:
            continue
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
            result = CaseResult(**data)
            if status_filter and result.status != status_filter:
                continue
            results.append(result)
        except Exception:
            continue
    return results


async def get_results_data(config: ProjectConfig, run_id: str | None = None, status_filter: str | None = None) -> dict:
    results = get_results(config, run_id, status_filter)
    return {"results": [r.model_dump() for r in results], "total": len(results)}


def list_all_cases(config: ProjectConfig, tags: list[str] | None = None) -> list[TestCase]:
    runner = Runner(config)
    return runner._collect_cases(tags=tags)


async def list_all_cases_data(config: ProjectConfig, project: str | None = None, tags: list[str] | None = None) -> dict:
    cases = list_all_cases(config, tags=tags)
    return {"cases": [{"id": c.id, "name": c.name, "priority": c.priority, "tags": c.tags} for c in cases], "total": len(cases)}


def validate_cases(config: ProjectConfig, path: str) -> list[dict]:
    from testmind.config.schema import TESTCASE_SCHEMA, validate_json
    target = Path(path)
    results: list[dict] = []
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
        result = validate_json(data, TESTCASE_SCHEMA)
        results.append({"case_id": data.get("id", "unknown"), "valid": result.valid, "errors": result.errors})
    elif target.is_dir():
        for json_file in target.rglob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                result = validate_json(data, TESTCASE_SCHEMA)
                results.append({"case_id": data.get("id", json_file.stem), "valid": result.valid, "errors": result.errors})
            except Exception as e:
                results.append({"case_id": json_file.stem, "valid": False, "errors": [str(e)]})
    return results


async def save_case_to_project(config: ProjectConfig, case_json: dict, project: str | None = None) -> dict:
    """Save a test case JSON to the project directory (async-safe wrapper)."""
    from testmind.config.schema import TESTCASE_SCHEMA, validate_json
    result = validate_json(case_json, TESTCASE_SCHEMA)
    if not result.valid:
        return {"status": "validation_error", "errors": result.errors}

    case = TestCase(**case_json)
    fingerprint = case.compute_fingerprint()

    cases_dir = _workspace_dir(config) / "cases"
    module_dir = cases_dir / case.id.split("-")[2].lower() if "-" in case.id else cases_dir / "default"
    module_dir.mkdir(parents=True, exist_ok=True)

    existing = _find_case_by_fingerprint(cases_dir, fingerprint)
    if existing:
        return {"status": "duplicate", "message": f"Case with same fingerprint already exists: {existing}"}

    existing_by_id = _find_case_by_id(cases_dir, case.id)
    if existing_by_id:
        pending_dir = cases_dir / ".pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        pending_file = pending_dir / f"{case.id}.json"
        pending_file.write_text(json.dumps(case_json, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"status": "pending_review", "message": f"Case {case.id} already exists, saved to .pending/", "path": str(pending_file)}

    case_file = module_dir / f"{case.id}.json"
    case_file.write_text(json.dumps(case_json, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "saved", "path": str(case_file), "case_id": case.id}


def approve_cases(config: ProjectConfig, case_ids: list[str]) -> int:
    cases_dir = _workspace_dir(config) / "cases"
    pending_dir = cases_dir / ".pending"
    approved = 0
    for case_id in case_ids:
        pending_file = pending_dir / f"{case_id}.json"
        if pending_file.exists():
            data = json.loads(pending_file.read_text(encoding="utf-8"))
            case = TestCase(**data)
            module_dir = cases_dir / (case.id.split("-")[2].lower() if "-" in case.id and len(case.id.split("-")) > 2 else "default")
            module_dir.mkdir(parents=True, exist_ok=True)
            target = module_dir / f"{case.id}.json"
            pending_file.rename(target)
            approved += 1
    return approved


def cleanup_results(config: ProjectConfig, keep_last: int | None = None, before: str | None = None, clean_all: bool = False) -> int:
    results_dir = _workspace_dir(config) / "results"
    if not results_dir.exists():
        return 0
    if clean_all:
        count = len(list(results_dir.iterdir()))
        import shutil
        shutil.rmtree(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)
        return count

    run_dirs = sorted([d for d in results_dir.iterdir() if d.is_dir()], key=lambda d: d.name)

    if keep_last is not None:
        to_remove = run_dirs[:-keep_last] if keep_last > 0 else run_dirs
    elif before:
        to_remove = [d for d in run_dirs if d.name < before.replace("-", "")]
    else:
        return 0

    removed = 0
    for d in to_remove:
        import shutil
        shutil.rmtree(d)
        removed += 1
    return removed


def _find_case_by_fingerprint(cases_dir: Path, fingerprint: str) -> str | None:
    for json_file in cases_dir.rglob("*.json"):
        if json_file.parent.name == ".pending":
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            case = TestCase(**data)
            if case.compute_fingerprint() == fingerprint:
                return case.id
        except Exception:
            continue
    return None


def _find_case_by_id(cases_dir: Path, case_id: str) -> str | None:
    for json_file in cases_dir.rglob("*.json"):
        if json_file.parent.name == ".pending":
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if data.get("id") == case_id:
                return case_id
        except Exception:
            continue
    return None