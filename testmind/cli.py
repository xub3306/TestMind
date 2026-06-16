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
        status_icon = {"pass": "✓", "fail": "✗", "error": "!", "skipped": "○"}.get(r.status, "?")
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


@main.command()
@click.argument("base_url")
def discover_spec(base_url: str):
    """Discover API specification URLs from a base URL."""
    from testmind.core.spec_fetcher import SpecFetcher

    try:
        config = load_project_config()
    except FileNotFoundError as e:
        click.echo(f"Configuration error: {e}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    fetcher = SpecFetcher(config)
    found = fetcher.discover(base_url)
    for item in found:
        click.echo(f"  {item.url} ({item.format})")


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
        status = "✓" if r["valid"] else f"✗ {r['errors']}"
        click.echo(f"  {r['case_id']}: {status}")


@main.command()
@click.argument("ids")
def approve(ids: str):
    """Approve pending test cases by IDs (comma-separated)."""
    from testmind.core.runner import approve_cases

    try:
        config = load_project_config()
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