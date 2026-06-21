"""Supplementary unit tests for core modules.

Fills coverage gaps left by ``tests/test_core/test_runner.py``:

* assertion: header / response_time / json_schema / body_contains /
  body ``{{type:}}`` / _resolve_path / _compare operators
* variable: ``{{$response.*}}`` substitution, regex extraction, list
  replacement, multi-source context merge
* hooks: load_hook / execute_hooks / async hooks / error propagation
* requirements_saver: JSON+MD dual output, Markdown section rendering
* runner: topological sort, cycle detection, env filtering, collect

All tests are offline (no HTTP) unless explicitly noted.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.core.assertion import (
    _compare,
    _resolve_path,
    assert_response,
)
from testmind.core.hooks import execute_hooks, execute_hooks_async, load_hook
from testmind.core.requirements_saver import RequirementsSaver, _generate_markdown
from testmind.core.runner import Runner
from testmind.core.variable import (
    build_variable_context,
    extract_variables,
    replace_variables,
)
from testmind.config.settings import ProjectConfig
from testmind.models.project import (
    BusinessFlow,
    BusinessRequirements,
    BusinessRule,
    ModuleInfo,
    PageInfo,
    RequirementsSource,
)
from testmind.models.testcase import TestCase


# ---------------------------------------------------------------------------
# Assertion — extended coverage
# ---------------------------------------------------------------------------


class TestAssertionExtended:
    """Cover assertion types and helpers beyond status_code/jsonpath."""

    def test_header_assertion_pass(self):
        from testmind.models.testcase import AssertionDef
        ad = AssertionDef(type="header", path="X-Request-Id", operator="eq", expected="req-1")
        response = {"status_code": 200, "headers": {"X-Request-Id": "req-1"}, "body": {}}
        from testmind.core.assertion import _assert_header
        r = _assert_header(ad, response)
        assert r.passed

    def test_header_assertion_contains(self):
        from testmind.models.testcase import AssertionDef
        ad = AssertionDef(type="header", path="Content-Type", operator="contains", expected="json")
        response = {"headers": {"Content-Type": "application/json"}, "body": {}}
        from testmind.core.assertion import _assert_header
        assert _assert_header(ad, response).passed

    def test_response_time_lt_pass(self):
        from testmind.models.testcase import AssertionDef
        ad = AssertionDef(type="response_time", operator="lt", expected=500)
        response = {"duration_ms": 100, "body": {}}
        from testmind.core.assertion import _assert_response_time
        assert _assert_response_time(ad, response).passed

    def test_response_time_gt_fail(self):
        from testmind.models.testcase import AssertionDef
        ad = AssertionDef(type="response_time", operator="gt", expected=50)
        response = {"duration_ms": 10, "body": {}}
        from testmind.core.assertion import _assert_response_time
        assert not _assert_response_time(ad, response).passed

    def test_json_schema_pass(self):
        from testmind.models.testcase import AssertionDef
        schema = {"type": "object", "required": ["id"]}
        ad = AssertionDef(type="json_schema", expected=schema)
        response = {"body": {"id": 1, "name": "x"}}
        from testmind.core.assertion import _assert_json_schema
        assert _assert_json_schema(ad, response).passed

    def test_json_schema_fail(self):
        from testmind.models.testcase import AssertionDef
        schema = {"type": "object", "required": ["id"]}
        ad = AssertionDef(type="json_schema", expected=schema)
        response = {"body": {"name": "x"}}  # missing id
        from testmind.core.assertion import _assert_json_schema
        assert not _assert_json_schema(ad, response).passed

    def test_body_contains_pass(self):
        from testmind.models.testcase import AssertionDef
        ad = AssertionDef(type="body_contains", expected="alice")
        response = {"body": {"user": "alice"}}
        from testmind.core.assertion import _assert_body_contains
        assert _assert_body_contains(ad, response).passed

    def test_body_type_assertion(self):
        """Body expectations with ``{{type:int}}`` trigger a type check."""
        response = {"body": {"count": 42, "name": "x"}}
        results = assert_response(None, response, {"status": 200, "body": {"count": "{{type:int}}", "name": "{{type:str}}"}})
        type_results = [r for r in results if r.operator == "type"]
        assert len(type_results) == 2
        assert all(r.passed for r in type_results)

    def test_body_type_assertion_fail(self):
        response = {"body": {"count": "not-int"}}
        results = assert_response(None, response, {"status": 200, "body": {"count": "{{type:int}}"}})
        type_results = [r for r in results if r.operator == "type"]
        assert len(type_results) == 1
        assert not type_results[0].passed

    def test_unknown_assertion_type_fails_gracefully(self):
        from testmind.models.testcase import AssertionDef
        ad = AssertionDef(type="bogus", operator="eq", expected=1)
        results = assert_response(None, {"body": {}}, {"status": 200, "assertions": [ad.model_dump()]})
        bogus = [r for r in results if r.type == "bogus"]
        assert len(bogus) == 1
        assert not bogus[0].passed
        assert "Unknown assertion type" in bogus[0].message

    def test_resolve_path_nested(self):
        obj = {"a": {"b": {"c": 42}}}
        assert _resolve_path(obj, "a.b.c") == 42

    def test_resolve_path_list_index(self):
        obj = {"items": [10, 20, 30]}
        assert _resolve_path(obj, "items.1") == 20

    def test_resolve_path_missing_returns_none(self):
        assert _resolve_path({"a": 1}, "b.c") is None

    def test_compare_ne(self):
        assert _compare(1, "ne", 2) is True
        assert _compare(1, "ne", 1) is False

    def test_compare_contains(self):
        assert _compare("hello world", "contains", "world") is True
        assert _compare("hello", "contains", "xyz") is False

    def test_compare_not_contains(self):
        assert _compare("hello", "not_contains", "xyz") is True

    def test_compare_regex(self):
        assert _compare("abc123", "regex", r"\d+") is True
        assert _compare("abc", "regex", r"\d+") is False

    def test_compare_in(self):
        assert _compare(2, "in", [1, 2, 3]) is True
        assert _compare(5, "in", [1, 2, 3]) is False

    def test_compare_type_operator(self):
        assert _compare(42, "type", "int") is True
        assert _compare("x", "type", "int") is False

    def test_compare_invalid_returns_false(self):
        # Comparing incompatible types should not raise.
        assert _compare("x", "gt", 10) is False


# ---------------------------------------------------------------------------
# Variable — extended coverage
# ---------------------------------------------------------------------------


class TestVariableExtended:
    """Cover $response vars, regex extraction, list replacement."""

    def test_response_var_status_code(self):
        ctx = {"$response": {"status_code": 201, "body": {}, "headers": {}}}
        assert replace_variables("code={{$response.status_code}}", ctx) == "code=201"

    def test_response_var_body_path(self):
        ctx = {"$response": {"body": {"data": {"id": 7}}, "headers": {}}}
        assert replace_variables("id={{$response.body.data.id}}", ctx) == "id=7"

    def test_response_var_header(self):
        ctx = {"$response": {"headers": {"X-Token": "abc"}, "body": {}}}
        assert replace_variables("t={{$response.header.X-Token}}", ctx) == "t=abc"

    def test_response_var_missing_returns_empty(self):
        # No $response in context → empty substitution.
        assert replace_variables("x={{$response.body.id}}", {}) == "x="

    def test_replace_list_of_strings(self):
        ctx = {"v": "1"}
        result = replace_variables(["a={{v}}", "b={{v}}"], ctx)
        assert result == ["a=1", "b=1"]

    def test_extract_variables_regex(self):
        response = {"body": "token=abc123;exp=99"}
        defs = {"tok": {"type": "regex", "path": r"token=(\w+)"}}
        result = extract_variables(response, defs)
        assert result["tok"] == "abc123"

    def test_extract_variables_regex_no_match(self):
        response = {"body": "no token here"}
        defs = {"tok": {"type": "regex", "path": r"token=(\w+)"}}
        result = extract_variables(response, defs)
        assert result["tok"] == ""

    def test_build_context_all_sources_merge(self):
        ctx = build_variable_context(
            cli_vars={"a": "cli", "shared": "cli"},
            env_vars={"b": "env", "shared": "env"},
            project_vars={"c": "proj", "shared": "proj"},
            case_vars={"d": "case"},
        )
        # CLI wins for shared; all others present.
        assert ctx["a"] == "cli"
        assert ctx["b"] == "env"
        assert ctx["c"] == "proj"
        assert ctx["d"] == "case"
        assert ctx["shared"] == "cli"


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def _write_hook(project_dir: Path, name: str, body: str) -> None:
    hooks_dir = project_dir / "testmind" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / f"{name}.py").write_text(body, encoding="utf-8")


class TestHooks:
    """Cover hook loading, execution, and error handling."""

    def test_load_hook_success(self, tmp_path: Path):
        _write_hook(tmp_path, "setup_db", "def run(ctx):\n    return {'token': 'abc'}\n")
        ctx = {"project_dir": str(tmp_path)}
        result = load_hook("setup_db", ctx)
        assert result == {"token": "abc"}

    def test_load_hook_missing_project_dir(self):
        with pytest.raises(ValueError, match="project_dir"):
            load_hook("any", {})

    def test_load_hook_not_found(self, tmp_path: Path):
        ctx = {"project_dir": str(tmp_path)}
        with pytest.raises(FileNotFoundError):
            load_hook("nope", ctx)

    def test_load_hook_no_run_function(self, tmp_path: Path):
        _write_hook(tmp_path, "bad", "# no run function here\nx = 1\n")
        ctx = {"project_dir": str(tmp_path)}
        with pytest.raises(AttributeError, match="no 'run'"):
            load_hook("bad", ctx)

    def test_execute_hooks_before_failure_raises(self, tmp_path: Path):
        _write_hook(tmp_path, "boom", "def run(ctx):\n    raise RuntimeError('kaboom')\n")
        ctx = {"project_dir": str(tmp_path)}
        with pytest.raises(RuntimeError, match="kaboom"):
            execute_hooks(["boom"], ctx, "before")

    def test_execute_hooks_after_failure_does_not_raise(self, tmp_path: Path):
        _write_hook(tmp_path, "boom", "def run(ctx):\n    raise RuntimeError('kaboom')\n")
        ctx = {"project_dir": str(tmp_path)}
        # after hooks swallow errors so teardown is best-effort.
        results = execute_hooks(["boom"], ctx, "after")
        assert results[0]["status"] == "error"
        assert "kaboom" in results[0]["error"]

    def test_execute_hooks_updates_variables(self, tmp_path: Path):
        _write_hook(tmp_path, "seed", "def run(ctx):\n    return {'seeded': 'yes'}\n")
        ctx = {"project_dir": str(tmp_path)}
        execute_hooks(["seed"], ctx, "before")
        assert ctx["variables"]["seeded"] == "yes"

    def test_execute_hooks_async_run(self, tmp_path: Path):
        _write_hook(tmp_path, "async_hook", "async def run(ctx):\n    return {'a': 1}\n")
        ctx = {"project_dir": str(tmp_path)}
        results = asyncio.run(execute_hooks_async(["async_hook"], ctx, "before"))
        assert results[0]["status"] == "success"
        assert results[0]["result"] == {"a": 1}


# ---------------------------------------------------------------------------
# Requirements saver — Markdown generation
# ---------------------------------------------------------------------------


class TestRequirementsSaver:
    """Cover save_async and _generate_markdown sections."""

    def test_save_json_and_markdown(self, tmp_path: Path):
        tm_dir = tmp_path / "testmind"
        (tm_dir / "requirements").mkdir(parents=True, exist_ok=True)
        (tm_dir / "project.json").write_text(
            json.dumps({"name": "demo", "base_url": "http://localhost"}),
            encoding="utf-8",
        )
        saver = RequirementsSaver()
        result = saver.save(
            {"project": "demo", "modules": [
                {"id": "M1", "name": "Mod", "flows": [{"id": "F1", "name": "Flow"}]},
            ]},
            {"type": "manual"},
            project_name=str(tmp_path),
        )
        # save() returns a RequirementsSaveResult object (not a dict).
        assert Path(result.requirements_path).is_file()
        assert Path(result.markdown_path).is_file()
        assert result.modules_count == 1
        assert result.flows_count == 1

    def test_save_no_project_raises(self):
        saver = RequirementsSaver()
        with pytest.raises(FileNotFoundError):
            saver.save({"project": "x", "modules": []}, {"type": "manual"}, "/no/such")

    def test_markdown_contains_title_and_stats(self):
        req = BusinessRequirements(
            format="testmind-requirements-1.0",
            project="demo",
            source=RequirementsSource(type="manual", explored_at="2026-01-01T00:00:00Z"),
            modules=[ModuleInfo(id="M1", name="User", description="user mod")],
        )
        md = _generate_markdown(req)
        assert "demo" in md
        assert "概览" in md
        assert "模块数" in md
        assert "User" in md

    def test_markdown_renders_steps_table(self):
        req = BusinessRequirements(
            format="testmind-requirements-1.0",
            project="p",
            source=RequirementsSource(type="manual"),
            modules=[ModuleInfo(
                id="M1", name="Mod",
                flows=[BusinessFlow(
                    id="F1", name="Login",
                    steps=[{"screen": "login", "action": "input", "input": {"u": "a"}}],
                )],
            )],
        )
        md = _generate_markdown(req)
        assert "流程步骤" in md
        assert "login" in md
        assert "input" in md

    def test_markdown_renders_error_flows(self):
        req = BusinessRequirements(
            format="testmind-requirements-1.0",
            project="p",
            source=RequirementsSource(type="manual"),
            modules=[ModuleInfo(
                id="M1", name="Mod",
                flows=[BusinessFlow(
                    id="F1", name="Flow",
                    error_flows=[{"name": "timeout", "expected": "retry"}],
                )],
            )],
        )
        md = _generate_markdown(req)
        assert "异常流程" in md
        assert "timeout" in md

    def test_markdown_renders_pages(self):
        req = BusinessRequirements(
            format="testmind-requirements-1.0",
            project="p",
            source=RequirementsSource(type="manual"),
            modules=[ModuleInfo(
                id="M1", name="Mod",
                pages=[PageInfo(id="P1", name="Home", elements=["button1"], entry_points=["nav"])],
            )],
        )
        md = _generate_markdown(req)
        assert "页面" in md
        assert "Home" in md

    def test_markdown_renders_business_rules(self):
        req = BusinessRequirements(
            format="testmind-requirements-1.0",
            project="p",
            source=RequirementsSource(type="manual"),
            modules=[],
            business_rules=[BusinessRule(id="BR-1", description="rule one", applies_to=["auth"])],
        )
        md = _generate_markdown(req)
        assert "业务规则" in md
        assert "BR-1" in md
        assert "rule one" in md


# ---------------------------------------------------------------------------
# Runner — topological sort, filtering, collection
# ---------------------------------------------------------------------------


def _make_case(cid: str, depends: list[str] | None = None, envs: list[str] | None = None,
               disabled: bool = False, tags: list[str] | None = None) -> TestCase:
    return TestCase(
        id=cid, name=cid, type="api", priority="P1",
        tags=tags or [], disabled=disabled, environments=envs,
        depends=depends,
        request={"method": "GET", "path": f"/{cid}"},
        expect={"status": 200},
    )


class TestRunnerTopology:
    """Cover topological sort and cycle detection."""

    def _runner(self, tmp_path: Path) -> Runner:
        config = ProjectConfig(name="t", base_url="http://localhost")
        config.project_dir = tmp_path
        return Runner(config)

    def test_sort_respects_dependencies(self, tmp_path: Path):
        runner = self._runner(tmp_path)
        cases = [
            _make_case("C", depends=["B"]),
            _make_case("A"),
            _make_case("B", depends=["A"]),
        ]
        ordered = runner._topological_sort(cases)
        ids = [c.id for c in ordered]
        assert ids.index("A") < ids.index("B") < ids.index("C")

    def test_sort_detects_cycle(self, tmp_path: Path):
        runner = self._runner(tmp_path)
        cases = [
            _make_case("A", depends=["B"]),
            _make_case("B", depends=["A"]),
        ]
        with pytest.raises(ValueError, match="Circular dependency"):
            runner._topological_sort(cases)

    def test_sort_handles_missing_dependency(self, tmp_path: Path):
        """A dependency on a non-collected case is silently ignored."""
        runner = self._runner(tmp_path)
        cases = [_make_case("A", depends=["GHOST"])]
        ordered = runner._topological_sort(cases)
        assert [c.id for c in ordered] == ["A"]


class TestRunnerFiltering:
    """Cover env filtering and case collection."""

    def _setup_project(self, tmp_path: Path, cases: list[TestCase]) -> Runner:
        config = ProjectConfig(name="t", base_url="http://localhost", default_env="dev")
        config.project_dir = tmp_path
        cases_dir = tmp_path / "testmind" / "cases"
        cases_dir.mkdir(parents=True, exist_ok=True)
        for c in cases:
            (cases_dir / f"{c.id}.json").write_text(
                json.dumps(c.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return Runner(config)

    def test_filter_by_environment(self, tmp_path: Path):
        runner = self._setup_project(tmp_path, [
            _make_case("TC-API-A-001", envs=["dev"]),
            _make_case("TC-API-B-001", envs=["prod"]),
        ])
        collected = runner._collect_cases()
        filtered = runner._filter_cases(collected, env_name="dev")
        ids = {c.id for c in filtered}
        assert "TC-API-A-001" in ids
        assert "TC-API-B-001" not in ids

    def test_filter_no_env_restrictions_runs_all(self, tmp_path: Path):
        runner = self._setup_project(tmp_path, [
            _make_case("TC-API-A-001"),
            _make_case("TC-API-B-001"),
        ])
        collected = runner._collect_cases()
        filtered = runner._filter_cases(collected, env_name="dev")
        assert len(filtered) == 2

    def test_collect_by_tags(self, tmp_path: Path):
        runner = self._setup_project(tmp_path, [
            _make_case("TC-API-A-001", tags=["smoke"]),
            _make_case("TC-API-B-001", tags=["regression"]),
        ])
        collected = runner._collect_cases(tags=["smoke"])
        assert {c.id for c in collected} == {"TC-API-A-001"}

    def test_collect_target_subdir(self, tmp_path: Path):
        config = ProjectConfig(name="t", base_url="http://localhost")
        config.project_dir = tmp_path
        cases_dir = tmp_path / "testmind" / "cases" / "users"
        cases_dir.mkdir(parents=True, exist_ok=True)
        c = _make_case("TC-API-USERS-001")
        (cases_dir / f"{c.id}.json").write_text(
            json.dumps(c.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        runner = Runner(config)
        collected = runner._collect_cases(target="users")
        assert {c.id for c in collected} == {"TC-API-USERS-001"}
