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