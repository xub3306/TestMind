from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testmind.config.settings import load_project_config
from testmind.models.project import BusinessRequirements, RequirementsSource


class RequirementsSaveResult:
    def __init__(
        self,
        requirements_path: str,
        modules_count: int,
        flows_count: int,
    ) -> None:
        self.requirements_path = requirements_path
        self.modules_count = modules_count
        self.flows_count = flows_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirements_path": self.requirements_path,
            "modules_count": self.modules_count,
            "flows_count": self.flows_count,
        }


class RequirementsSaver:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def save(
        self,
        requirements_data: dict[str, Any],
        source_info: dict[str, Any],
        project_name: str | None = None,
    ) -> RequirementsSaveResult:
        """Synchronous wrapper for :meth:`save_async`."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run, self.save_async(requirements_data, source_info, project_name)
                )
                return future.result()
        return asyncio.run(self.save_async(requirements_data, source_info, project_name))

    async def save_async(
        self,
        requirements_data: dict[str, Any],
        source_info: dict[str, Any],
        project_name: str | None = None,
    ) -> RequirementsSaveResult:
        project_dir = self._resolve_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"Project not found: {project_name}")

        req_dir = project_dir / "testmind" / "requirements"
        req_dir.mkdir(parents=True, exist_ok=True)

        modules = requirements_data.get("modules", [])
        flows_count = sum(len(m.get("flows", [])) for m in modules)

        source = RequirementsSource(
            type=source_info.get("type", "manual"),
            device=source_info.get("device"),
            platform=source_info.get("platform"),
            app_package=source_info.get("app_package"),
            explored_at=datetime.now(timezone.utc).isoformat(),
            path=source_info.get("path"),
        )

        req_model = BusinessRequirements(
            format="testmind-requirements-1.0",
            project=requirements_data.get("project", project_name or ""),
            source=source,
            modules=modules,
            business_rules=requirements_data.get("business_rules"),
        )

        req_path = req_dir / "business-requirements.json"
        req_path.write_text(
            json.dumps(req_model.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return RequirementsSaveResult(
            requirements_path=str(req_path),
            modules_count=len(modules),
            flows_count=flows_count,
        )

    def _resolve_project_dir(self, project_name: str | None = None) -> Path | None:
        if project_name:
            try:
                cfg = load_project_config(project_name)
                return cfg.project_dir
            except (FileNotFoundError, Exception):
                pass
        return None
