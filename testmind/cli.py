"""TestMind CLI entry point."""

import sys

import click

from testmind.config.settings import load_project_config
from testmind.core.runner import EXIT_CONFIG_ERROR, EXIT_HAS_ERROR, EXIT_HAS_FAIL


@click.group()
@click.version_option(version="0.1.0", prog_name="testmind")
def main():
    """TestMind - Intelligent testing AI platform."""
    pass


@main.command()
@click.argument("project_name")
@click.option("--type", "project_type", default="api", type=click.Choice(["api", "web", "mobile"]))
@click.option("--base-url", default="", help="Base URL of the API")
@click.option("--auth", "auth_type", default="none", type=click.Choice(["none", "bearer", "basic", "api_key"]))
@click.option("--agent", default="", help="Agent config: claude,opencode,both,skip")
@click.option("--env", "envs", default="dev", help="Comma-separated env names")
def init(project_name: str, project_type: str, base_url: str, auth_type: str, agent: str, envs: str):
    """Initialize a new TestMind project."""
    from testmind.core.project_init import init_project

    agent_list = [a.strip() for a in agent.split(",") if a.strip()] if agent else []
    result = init_project(
        name=project_name,
        project_type=project_type,
        base_url=base_url,
        auth_type=auth_type,
        agents=agent_list,
        envs=envs.split(","),
    )
    click.echo(f"Project initialized: {result}")


@main.command()
@click.option("--env", default=None, help="Environment name")
@click.option("--tags", default=None, help="Comma-separated tags")
@click.option("--target", default=None, help="Target case directory")
@click.option("--suite", default=None, help="Test suite name")
@click.option("--fail-fast", default=0, type=int, help="Stop after N consecutive failures")
@click.option("--workers", default=1, type=int, help="Number of parallel workers")
@click.option("--retry", default=None, type=int, help="Retry failed cases N times")
@click.option("--device", default=None, help="Device name (V3)")
@click.option("--devices", default=None, help="Comma-separated device names (V3)")
@click.option("--var", "variables", multiple=True, help="Override variables: key=value")
def run(env: str, tags: str, target: str, suite: str, fail_fast: int, workers: int, retry: int, device: str, devices: str, variables: tuple):
    """Run test cases."""
    from testmind.core.runner import Runner

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    runner = Runner(config)

    try:
        run_id = runner.run(
            env=env,
            tags=tags.split(",") if tags else None,
            target=target,
            suite=suite,
            fail_fast=fail_fast,
            workers=workers,
            retry=retry,
            device=device,
            devices=devices.split(",") if devices else None,
            variables=dict(v.split("=", 1) for v in variables) if variables else None,
        )
        click.echo(f"Run completed: {run_id}")

        # Determine exit code from results
        results_dir = runner._get_results_dir(run_id)
        from testmind.core.runner import get_results
        all_results = get_results(config, run_id=run_id)
        exit_code = runner.get_exit_code(all_results)
        sys.exit(exit_code)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(EXIT_HAS_ERROR)


@main.command()
@click.option("--run", "run_id", default=None, help="Run ID to query")
@click.option("--status", "status_filter", default=None, type=click.Choice(["pass", "fail", "error", "skipped"]))
def results(run_id: str, status_filter: str):
    """View test results."""
    from testmind.core.runner import get_results

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    results_data = get_results(config, run_id=run_id, status_filter=status_filter)
    for r in results_data:
        # ASCII icons for cross-platform terminal safety (Windows GBK).
        status_icon = {"pass": "PASS", "fail": "FAIL", "error": "ERR!", "skipped": "SKIP"}.get(r.status, "?")
        click.echo(f"  [{status_icon}] {r.case_id}: {r.status} ({r.duration_ms}ms)")


@main.command("list")
@click.option("--tags", default=None, help="Filter by tags")
def list_cases(tags: str):
    """List test cases in the project."""
    from testmind.core.runner import list_all_cases

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    cases = list_all_cases(config, tags=tags.split(",") if tags else None)
    for c in cases:
        click.echo(f"  {c.id}: {c.name} [{c.priority}]")


@main.command()
@click.option("--keep-last", default=None, type=int, help="Keep last N runs")
@click.option("--before", default=None, help="Remove runs before date (YYYY-MM-DD)")
@click.option("--all", "clean_all", is_flag=True, help="Remove all results")
def clean(keep_last: int, before: str, clean_all: bool):
    """Clean up old test results."""
    from testmind.core.runner import cleanup_results

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    removed = cleanup_results(config, keep_last=keep_last, before=before, clean_all=clean_all)
    click.echo(f"Removed {removed} result directories.")


@main.command("discover-spec")
@click.argument("base_url")
@click.option("--extended", is_flag=True, default=False, help="Probe extended path list (slower, more thorough)")
def discover_spec(base_url: str, extended: bool):
    """Discover API specification URLs from a base URL."""
    from testmind.core.spec_fetcher import SpecFetcher

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    fetcher = SpecFetcher(config)
    result = fetcher.discover(base_url, extended=extended)
    if not result.found:
        click.echo("No API spec URLs found.")
        return
    for item in result.found:
        click.echo(f"  {item['url']} ({item['format']})")


@main.command()
@click.argument("url")
@click.option("--project", "project_name", default=None, help="Target project name")
@click.option("--save-path", default=None, help="Custom save path")
def fetch_url(url: str, project_name: str, save_path: str):
    """Download a URL's content to the local project."""
    from testmind.core.spec_fetcher import SpecFetcher

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    fetcher = SpecFetcher(config)
    result = fetcher.fetch(url, project_name=project_name, save_path=save_path)
    click.echo(f"Saved: {result.file_path} ({result.size_bytes} bytes, format: {result.format})")


@main.command()
@click.argument("spec_path")
@click.option("--project", "project_name", default=None, help="Target project name")
def parse_spec(spec_path: str, project_name: str):
    """Parse a local OpenAPI/Swagger spec file into standardized api-spec.json."""
    from testmind.core.spec_parser import SpecParser

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    parser = SpecParser(config)
    result = parser.parse(spec_path, project_name=project_name)
    click.echo(f"Parsed {result.endpoints_count} endpoints, saved to {result.api_spec_path}")


@main.command()
@click.argument("path")
def validate(path: str):
    """Validate test case files in the given path."""
    from testmind.core.runner import validate_cases

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    results = validate_cases(config, path)
    for r in results:
        status = "OK" if r["valid"] else f"FAIL {r['errors']}"
        click.echo(f"  {r['case_id']}: {status}")


@main.command()
@click.argument("ids")
@click.option("--project", "project_path", default=".", help="Project directory")
def approve(ids, project_path):
    """Approve pending test cases by IDs (comma-separated)."""
    from testmind.core.runner import approve_cases

    try:
        config = load_project_config(project_path)
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    case_ids = [i.strip() for i in ids.split(",")]
    approved = approve_cases(config, case_ids)
    click.echo(f"Approved {approved} cases.")


@main.command()
@click.option("--project", "project_path", default=".", help="Project directory")
def serve(project_path: str):
    """Start TestMind MCP Server."""
    from testmind.server import start_server

    try:
        start_server(project_path)
    except Exception as e:
        click.echo(f"MCP Server failed: {e}", err=True)
        sys.exit(EXIT_MCP_SERVER_FAIL)


@main.command("hooks")
@click.option("--project", "project_path", default=".", help="Project directory")
def hooks_list(project_path: str):
    """List available hook scripts in the project."""
    from pathlib import Path

    project_dir = Path(project_path).resolve()
    hooks_dir = project_dir / "testmind" / "hooks"

    if not hooks_dir.exists():
        click.echo("No hooks directory found.")
        return

    hook_files = sorted(hooks_dir.glob("*.py"))
    # Exclude __init__.py and assert_*.py (those are custom assertion scripts)
    hook_files = [f for f in hook_files if f.name != "__init__.py" and not f.name.startswith("assert_")]

    if not hook_files:
        click.echo("No hook scripts found.")
        return

    click.echo("Available hook scripts:")
    for hf in hook_files:
        module_name = hf.stem
        # Try to read the module docstring
        doc = ""
        try:
            content = hf.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    quote = stripped[:3]
                    remainder = stripped[3:]
                    if remainder.endswith(quote) and len(remainder) > 3:
                        doc = remainder[:-3]
                        break
                    elif remainder:
                        doc = remainder
                        break
                elif stripped.startswith("#"):
                    doc = stripped.lstrip("# ").strip()
                    break
                elif stripped and not stripped.startswith(("import", "from", "__")):
                    break
        except Exception:
            pass
        click.echo(f"  {module_name}" + (f" - {doc}" if doc else ""))


@main.command()
@click.argument("run_id")
@click.option("--project", "project_path", default=".", help="Project directory")
def report(run_id: str, project_path: str):
    """Generate an HTML report for a completed run.

    Reads the JSON results under testmind/results/<run_id>/ and writes
    a self-contained report.html in the same directory.  The report is
    also generated automatically at the end of every ``testmind run``.
    """
    from pathlib import Path

    from testmind.core.report import generate_html_report

    project_dir = Path(project_path).resolve()
    results_dir = project_dir / "testmind" / "results" / run_id
    if not results_dir.is_dir():
        click.echo(f"Run results not found: {results_dir}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        path = generate_html_report(results_dir)
        click.echo(f"Report generated: {path}")
    except FileNotFoundError as e:
        click.echo(f"Report generation failed: {e}", err=True)
        sys.exit(EXIT_HAS_ERROR)


@main.group()
def suite():
    """Manage test suites (group cases, set execution strategy)."""


@suite.command("create")
@click.argument("name")
@click.option("--id", "suite_id", default=None, help="Suite ID (e.g. SUITE-LOGIN-001)")
@click.option("--description", default="", help="Suite description")
@click.option("--case", "cases", multiple=True, help="Case ID to include (repeatable)")
@click.option("--case-dir", "case_dirs", multiple=True, help="Case directory to include (repeatable)")
@click.option("--tag", "tags", multiple=True, help="Tag for filtering (repeatable)")
@click.option("--setup", "setup", multiple=True, help="Setup hook script name (repeatable)")
@click.option("--teardown", "teardown", multiple=True, help="Teardown hook script name (repeatable)")
@click.option("--workers", type=int, default=None, help="Parallel workers (overrides CLI --workers)")
@click.option("--retry", type=int, default=None, help="Retry count (overrides CLI --retry)")
@click.option("--fail-fast", type=int, default=None, help="Stop after N consecutive failures (overrides CLI --fail-fast)")
@click.option("--project", "project_path", default=".", help="Project directory")
def suite_create(name, suite_id, description, cases, case_dirs, tags, setup, teardown, workers, retry, fail_fast, project_path):
    """Create a new test suite JSON file under testmind/suites/."""
    from pathlib import Path
    import json as _json

    project_dir = Path(project_path).resolve()
    suites_dir = project_dir / "testmind" / "suites"
    suites_dir.mkdir(parents=True, exist_ok=True)

    suite_data = {
        "name": name,
        "description": description,
        "tags": list(tags),
        "cases": list(cases),
        "case_dirs": list(case_dirs),
        "setup": list(setup) if setup else None,
        "teardown": list(teardown) if teardown else None,
    }
    if suite_id:
        suite_data["id"] = suite_id
    if workers is not None:
        suite_data["workers"] = workers
    if retry is not None:
        suite_data["retry"] = retry
    if fail_fast is not None:
        suite_data["fail_fast"] = fail_fast

    out_file = suites_dir / f"{name}.json"
    out_file.write_text(_json.dumps(suite_data, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"Suite created: {out_file}")


@suite.command("list")
@click.option("--project", "project_path", default=".", help="Project directory")
def suite_list(project_path):
    """List all test suites in the project."""
    from pathlib import Path
    import json as _json

    project_dir = Path(project_path).resolve()
    suites_dir = project_dir / "testmind" / "suites"
    if not suites_dir.is_dir():
        click.echo("No suites directory found.")
        return

    files = sorted(suites_dir.glob("*.json"))
    if not files:
        click.echo("No suites found.")
        return

    click.echo("Test suites:")
    for f in files:
        try:
            data = _json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name", f.stem)
            count = len(data.get("cases", [])) + len(data.get("case_dirs", []))
            click.echo(f"  {f.stem}: {name} ({count} entries)")
        except Exception:
            click.echo(f"  {f.stem}: <invalid JSON>")


@suite.command("show")
@click.argument("name")
@click.option("--project", "project_path", default=".", help="Project directory")
def suite_show(name, project_path):
    """Show the contents of a test suite."""
    from pathlib import Path
    import json as _json

    project_dir = Path(project_path).resolve()
    suite_file = project_dir / "testmind" / "suites" / f"{name}.json"
    if not suite_file.is_file():
        click.echo(f"Suite not found: {suite_file}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    data = _json.loads(suite_file.read_text(encoding="utf-8"))
    click.echo(_json.dumps(data, ensure_ascii=False, indent=2))


@main.group()
def case():
    """Manage test cases (review, history, version tracking)."""


@case.command("pending")
@click.option("--project", "project_path", default=".", help="Project directory")
def case_pending(project_path):
    """List test cases awaiting approval (.pending/ directory)."""
    from testmind.core.runner import list_pending_cases

    try:
        config = load_project_config(project_path)
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    pending = list_pending_cases(config)
    if not pending:
        click.echo("No pending cases.")
        return
    click.echo(f"Pending cases ({len(pending)}):")
    for p in pending:
        click.echo(f"  {p['case_id']}: {p['name']}")


@case.command("reject")
@click.argument("ids")
@click.option("--project", "project_path", default=".", help="Project directory")
def case_reject(ids, project_path):
    """Reject pending test cases by IDs (comma-separated). Deletes from .pending/."""
    from testmind.core.runner import reject_cases

    try:
        config = load_project_config(project_path)
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    case_ids = [i.strip() for i in ids.split(",")]
    rejected = reject_cases(config, case_ids)
    click.echo(f"Rejected {rejected} cases.")


@case.command("history")
@click.argument("case_id")
@click.option("--project", "project_path", default=".", help="Project directory")
def case_history(case_id, project_path):
    """Show the version history and changelog for a test case."""
    from testmind.core.runner import get_case_history

    try:
        config = load_project_config(project_path)
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    data = get_case_history(config, case_id)
    if data is None:
        click.echo(f"Case not found: {case_id}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    meta = data.get("metadata", {})
    click.echo(f"Case ID:    {data['id']}")
    click.echo(f"Name:       {data['name']}")
    click.echo(f"Priority:   {data.get('priority', '')}")
    click.echo(f"Version:    {meta.get('version', 1)}")
    click.echo(f"Created:    {meta.get('created_at', '')}")
    click.echo(f"Updated:    {meta.get('updated_at', '')}")
    changelog = meta.get("changelog")
    if changelog:
        click.echo("\nChangelog:")
        for entry in changelog:
            click.echo(f"  v{entry.get('version', '?')} [{entry.get('date', '')}] {entry.get('message', '')} by {entry.get('author', '?')}")
    else:
        click.echo("\nChangelog: (no entries)")


@case.command("show")
@click.argument("case_id")
@click.option("--project", "project_path", default=".", help="Project directory")
def case_show(case_id, project_path):
    """Show the full JSON content of a test case."""
    from testmind.core.runner import get_case_history

    try:
        config = load_project_config(project_path)
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    data = get_case_history(config, case_id)
    if data is None:
        click.echo(f"Case not found: {case_id}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    import json as _json
    click.echo(_json.dumps(data, ensure_ascii=False, indent=2))


@main.command()
@click.option("--project", "project_path", default=".", help="Project directory")
@click.option("--top", "top_n", default=10, help="Number of top failures to show")
@click.option("--html", "output_html", is_flag=True, help="Generate an HTML analysis report")
def analyze(project_path, top_n, output_html):
    """Analyze test results across all runs.

    Shows pass rate trend, top failing cases, and duration statistics.
    With --html, generates a self-contained HTML report alongside the
    terminal output.
    """
    from testmind.core.analyze import (
        compute_duration_trend,
        compute_overview,
        compute_pass_rate_trend,
        compute_top_failures,
        load_run_history,
    )

    try:
        config = load_project_config(project_path)
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    history = load_run_history(config)
    if not history:
        click.echo("No test runs found.")
        return

    overview = compute_overview(history)
    trend = compute_pass_rate_trend(history)
    top = compute_top_failures(history, top_n)
    dur = compute_duration_trend(history)

    # ---- Terminal output ----
    click.echo(f"\nTestMind Analysis — {overview['total_runs']} runs, "
               f"{overview['total_cases']} cases total\n")
    click.echo(f"  Avg pass rate: {overview['avg_pass_rate']}%")
    click.echo(f"  Avg duration:  {overview['avg_duration_ms']} ms")
    click.echo(f"  Total passed:  {overview['total_passed']}")
    click.echo(f"  Total failed:  {overview['total_failed']}")
    click.echo(f"  Total errors:  {overview['total_errors']}")
    click.echo("")

    # Pass rate trend (last 10 runs max for brevity).
    click.echo("Pass rate trend (recent):")
    recent = trend[-10:]
    for t in recent:
        bar = "#" * int(t["pass_rate"] // 5)
        click.echo(f"  {t['run_id'][:15]}: {bar} {t['pass_rate']}% ({t['total']} cases)")
    click.echo("")

    # Top failures.
    if top:
        click.echo(f"Top failures:")
        for item in top:
            click.echo(f"  {item['case_id']}: {item['failures']} failures")
        click.echo("")

    # Duration trend (recent).
    click.echo("Duration trend (recent):")
    for d in dur[-5:]:
        click.echo(f"  {d['run_id'][:15]}: {d['total_duration_ms']}ms "
                   f"({d['avg_per_case_ms']}ms/case)")
    click.echo("")

    # ---- HTML report (optional) ----
    if output_html:
        try:
            from testmind.core.analyze_html import render_analysis_html
        except ImportError:
            click.echo("HTML report feature not available (install from source).", err=True)
            return

        results_dir = config.project_dir / "testmind" / "results" / "analysis"
        results_dir.mkdir(parents=True, exist_ok=True)
        html_path = results_dir / "analysis.html"
        html_path.write_text(
            render_analysis_html(overview, trend, top, dur), encoding="utf-8"
        )
        click.echo(f"HTML analysis: {html_path}")


@main.group()
def perf():
    """Performance testing — benchmark HTTP endpoints."""


@perf.command("run")
@click.argument("url")
@click.option("--method", default="GET", help="HTTP method")
@click.option("--warmups", type=int, default=2, help="Warm-up rounds (excluded from stats)")
@click.option("--rounds", type=int, default=20, help="Measurement rounds")
@click.option("--max-avg", "max_avg_ms", type=float, default=None, help="Fail if avg > N ms")
@click.option("--baseline", is_flag=True, help="Save this run as the performance baseline")
@click.option("--compare", is_flag=True, help="Compare against stored baseline")
def perf_run(url, method, warmups, rounds, max_avg_ms, baseline, compare):
    """Run a performance benchmark against a URL."""
    from testmind.core.perf import (
        compare_to_baseline,
        load_baseline,
        run_perf_test,
        save_baseline,
    )

    click.echo(f"Benchmarking {method} {url} ({warmups} warm-ups + {rounds} rounds)...")
    result = run_perf_test(url, method=method, warmups=warmups, rounds=rounds,
                           max_avg_ms=max_avg_ms)

    s = result["stats"]
    click.echo(f"\n  Success: {result['success']}/{result['rounds']}  Errors: {result['errors']}")
    click.echo(f"  Min: {s['min_ms']}ms  Max: {s['max_ms']}ms  Avg: {s['avg_ms']}ms")
    click.echo(f"  p50: {s['median_ms (p50)']}ms  p90: {s['p90_ms']}ms  "
               f"p95: {s['p95_ms']}ms  p99: {s['p99_ms']}ms")
    click.echo(f"  StdDev: {s['stddev_ms']}ms")

    if "threshold_pass" in result:
        status = "PASS" if result["threshold_pass"] else "FAIL"
        click.echo(f"  Threshold (avg < {max_avg_ms}ms): {status}")

    if compare:
        try:
            config = load_project_config(".")
            baseline_data = load_baseline(config)
        except Exception:
            baseline_data = None
        if baseline_data:
            comp = compare_to_baseline(result, baseline_data)
            click.echo(f"\n  Baseline regression: {'YES' if comp['regression'] else 'NO'}")
            for k, v in comp["details"].items():
                click.echo(f"    {k}: {v['old']}ms -> {v['new']}ms ({v['delta_pct']:+.1f}%)" if v['delta_pct'] >= 0
                           else f"    {k}: {v['old']}ms -> {v['new']}ms ({v['delta_pct']:.1f}%)")

    if baseline:
        try:
            config = load_project_config(".")
            path = save_baseline(config, result)
            click.echo(f"\n  Baseline saved: {path}")
        except Exception:
            click.echo("  (no project directory — baseline not saved)")


@main.group()
def security():
    """Security testing — scan for common web vulnerabilities."""


@security.command("scan")
@click.argument("base_url")
@click.option("--path", default="/api/users", help="Endpoint path to scan")
@click.option("--param", "param_name", default="q", help="Query parameter to inject into")
@click.option("--sqli/--no-sqli", default=True, help="Include SQL injection tests")
@click.option("--xss/--no-xss", default=True, help="Include XSS tests")
@click.option("--traversal/--no-traversal", default=True, help="Include path traversal tests")
def security_scan(base_url, path, param_name, sqli, xss, traversal):
    """Run a quick security scan against an endpoint.

    Sends SQL injection, XSS, and path traversal payloads and reports
    any potential vulnerabilities found in the response.
    """
    from testmind.core.security import run_security_scan

    click.echo(f"Scanning {base_url}{path} ...")
    report = run_security_scan(
        base_url, path=path, param_name=param_name,
        include_sqli=sqli, include_xss=xss, include_path_traversal=traversal,
    )
    click.echo(f"\n  Payloads sent: {report['total_payloads']}")
    click.echo(f"  Vulnerabilities found: {report['vulnerabilities_found']}")
    if report["findings"]:
        click.echo(f"\n  Findings:")
        for f in report["findings"]:
            cat = f["category"].upper()
            click.echo(f"    [{cat}] {f['payload'][:60]}")
            click.echo(f"           {f['detail']}")
    else:
        click.echo("  No vulnerabilities detected.")


@main.group()
def crypto():
    """Manage encrypted secrets for project configurations."""


@crypto.command("gen-key")
def crypto_gen_key():
    """Generate a new Fernet master key.

    Print the key to stdout.  Persist it by exporting it as the
    TESTMIND_MASTER_KEY environment variable (e.g. in your CI secret
    store or ~/.bashrc).
    """
    from testmind.utils.crypto import generate_key, MASTER_KEY_ENV

    key = generate_key()
    click.echo(key)
    click.echo(f"# Set this as ${MASTER_KEY_ENV} in your environment.", err=True)


@crypto.command()
@click.argument("plaintext")
def encrypt(plaintext: str):
    """Encrypt PLAINTEXT and print the enc:<token> string.

    Requires TESTMIND_MASTER_KEY to be set in the environment.
    """
    from testmind.utils.crypto import encrypt as _encrypt, CryptoError

    try:
        click.echo(_encrypt(plaintext))
    except CryptoError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)


@crypto.command()
@click.argument("cipher_value")
def decrypt(cipher_value: str):
    """Decrypt an enc:<token> string back to plaintext.

    Requires TESTMIND_MASTER_KEY to be set in the environment.
    """
    from testmind.utils.crypto import decrypt as _decrypt, CryptoError

    try:
        click.echo(_decrypt(cipher_value))
    except CryptoError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)