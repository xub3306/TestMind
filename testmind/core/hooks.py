from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


def load_hook(hook_name: str, context: dict[str, Any]) -> dict[str, Any]:
    project_dir = context.get("project_dir")
    if not project_dir:
        raise ValueError("project_dir not found in context")

    hooks_dir = Path(project_dir) / "testmind" / "hooks"
    hook_file = hooks_dir / f"{hook_name}.py"

    if not hook_file.is_file():
        raise FileNotFoundError(f"Hook not found: {hook_file}")

    module_name = f"testmind_hook_{hook_name}"
    spec = importlib.util.spec_from_file_location(module_name, hook_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load hook module: {hook_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        raise AttributeError(f"Hook {hook_name} has no 'run' function")

    return module.run(context)


async def load_hook_async(hook_name: str, context: dict[str, Any]) -> dict[str, Any]:
    project_dir = context.get("project_dir")
    if not project_dir:
        raise ValueError("project_dir not found in context")

    hooks_dir = Path(project_dir) / "testmind" / "hooks"
    hook_file = hooks_dir / f"{hook_name}.py"

    if not hook_file.is_file():
        raise FileNotFoundError(f"Hook not found: {hook_file}")

    module_name = f"testmind_hook_{hook_name}"
    spec = importlib.util.spec_from_file_location(module_name, hook_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load hook module: {hook_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        raise AttributeError(f"Hook {hook_name} has no 'run' function")

    import asyncio
    result = module.run(context)
    if asyncio.iscoroutine(result):
        result = await result
    return result


def execute_hooks(
    hook_names: list[str],
    context: dict[str, Any],
    hook_type: str = "before",
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in hook_names:
        try:
            result = load_hook(name, context)
            if isinstance(result, dict):
                context.setdefault("variables", {}).update(result)
            results.append({"hook": name, "status": "success", "result": result})
        except Exception as e:
            results.append({"hook": name, "status": "error", "error": str(e)})
            if hook_type == "before":
                raise
    return results


async def execute_hooks_async(
    hook_names: list[str],
    context: dict[str, Any],
    hook_type: str = "before",
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in hook_names:
        try:
            result = await load_hook_async(name, context)
            if isinstance(result, dict):
                context.setdefault("variables", {}).update(result)
            results.append({"hook": name, "status": "success", "result": result})
        except Exception as e:
            results.append({"hook": name, "status": "error", "error": str(e)})
            if hook_type == "before":
                raise
    return results
