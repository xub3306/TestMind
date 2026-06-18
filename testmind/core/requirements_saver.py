"""Requirements saver – persist business requirements as JSON + Markdown.

The JSON file (``business-requirements.json``) is the machine-readable
single source of truth that downstream tools consume.  The Markdown file
(``business-requirements.md``) is a human-readable derivative that makes
it easy for stakeholders to review and approve the extracted requirements.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testmind.config.settings import load_project_config
from testmind.models.project import (
    BusinessFlow,
    BusinessRequirements,
    BusinessRule,
    ModuleInfo,
    RequirementsSource,
)


class RequirementsSaveResult:
    """Result of saving requirements – includes both file paths."""

    def __init__(
        self,
        requirements_path: str,
        markdown_path: str,
        modules_count: int,
        flows_count: int,
    ) -> None:
        self.requirements_path = requirements_path
        self.markdown_path = markdown_path
        self.modules_count = modules_count
        self.flows_count = flows_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirements_path": self.requirements_path,
            "markdown_path": self.markdown_path,
            "modules_count": self.modules_count,
            "flows_count": self.flows_count,
        }


class RequirementsSaver:
    """Persist a :class:`BusinessRequirements` model as JSON + Markdown."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
                    asyncio.run,
                    self.save_async(requirements_data, source_info, project_name),
                )
                return future.result()
        return asyncio.run(self.save_async(requirements_data, source_info, project_name))

    async def save_async(
        self,
        requirements_data: dict[str, Any],
        source_info: dict[str, Any],
        project_name: str | None = None,
    ) -> RequirementsSaveResult:
        """Save requirements as JSON and generate a companion Markdown file."""
        project_dir = self._resolve_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"Project not found: {project_name}")

        req_dir = project_dir / "testmind" / "requirements"
        req_dir.mkdir(parents=True, exist_ok=True)

        modules_data = requirements_data.get("modules", [])
        flows_count = sum(len(m.get("flows", [])) for m in modules_data)

        source = RequirementsSource(
            type=source_info.get("type", "manual"),
            device=source_info.get("device"),
            platform=source_info.get("platform"),
            app_package=source_info.get("app_package"),
            explored_at=datetime.now(timezone.utc).isoformat(),
            path=source_info.get("path"),
        )

        # Build Pydantic model from raw dicts so validation catches errors early.
        modules: list[ModuleInfo] = []
        for m in modules_data:
            flows = [BusinessFlow(**f) for f in m.get("flows", [])]
            modules.append(ModuleInfo(
                id=m.get("id", ""),
                name=m.get("name", ""),
                description=m.get("description", ""),
                flows=flows,
                pages=m.get("pages"),
            ))

        rules_data = requirements_data.get("business_rules")
        business_rules: list[BusinessRule] | None = None
        if rules_data:
            business_rules = [BusinessRule(**r) for r in rules_data]

        req_model = BusinessRequirements(
            format="testmind-requirements-1.0",
            project=requirements_data.get("project", project_name or ""),
            source=source,
            modules=modules,
            business_rules=business_rules,
        )

        # ---- Save JSON ----
        req_path = req_dir / "business-requirements.json"
        req_path.write_text(
            json.dumps(req_model.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ---- Generate & save Markdown ----
        md_content = _generate_markdown(req_model)
        md_path = req_dir / "business-requirements.md"
        md_path.write_text(md_content, encoding="utf-8")

        return RequirementsSaveResult(
            requirements_path=str(req_path),
            markdown_path=str(md_path),
            modules_count=len(modules),
            flows_count=flows_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_project_dir(self, project_name: str | None = None) -> Path | None:
        if project_name:
            try:
                cfg = load_project_config(project_name)
                return cfg.project_dir
            except (FileNotFoundError, Exception):
                pass
        return None


# ======================================================================
# Markdown generation – pure function, easy to unit-test
# ======================================================================


def _generate_markdown(req: BusinessRequirements) -> str:
    """Convert a :class:`BusinessRequirements` model to human-readable Markdown.

    The output follows a structured template:

    1. Title & source metadata
    2. Overview statistics
    3. Per-module sections with flows (steps table, error flows table)
    4. Per-module pages (if present)
    5. Cross-cutting business rules table
    """
    lines: list[str] = []

    # ---- Title & meta ----
    lines.append(f"# 业务需求文档 — {req.project}")
    lines.append("")
    source_parts: list[str] = []
    if req.source.type:
        source_parts.append(f"来源：{req.source.type}")
    if req.source.path:
        source_parts.append(f"路径：{req.source.path}")
    if req.source.explored_at:
        source_parts.append(f"提取时间：{req.source.explored_at}")
    if source_parts:
        lines.append("> " + " | ".join(source_parts))
    lines.append(f"> 格式版本：{req.format}")
    lines.append("")

    # ---- Overview ----
    total_flows = sum(len(m.flows) for m in req.modules)
    total_pages = sum(len(m.pages) for m in req.modules if m.pages)
    rules_count = len(req.business_rules) if req.business_rules else 0

    lines.append("## 概览")
    lines.append("")
    lines.append(f"- 模块数：{len(req.modules)}")
    lines.append(f"- 业务流数：{total_flows}")
    if total_pages:
        lines.append(f"- 页面数：{total_pages}")
    if rules_count:
        lines.append(f"- 业务规则数：{rules_count}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ---- Modules ----
    for module in req.modules:
        lines.append(f"## 模块：{module.name}（{module.id}）")
        if module.description:
            lines.append("")
            lines.append(f"> {module.description}")
        lines.append("")

        # -- Flows --
        if module.flows:
            lines.append("### 业务流")
            lines.append("")
            for flow in module.flows:
                lines.append(f"#### {flow.id}：{flow.name}")
                if flow.description:
                    lines.append("")
                    lines.append(flow.description)
                lines.append("")

                # Preconditions
                if flow.preconditions:
                    lines.append("**前置条件**：")
                    for pc in flow.preconditions:
                        lines.append(f"- {pc}")
                    lines.append("")

                # Steps table
                if flow.steps:
                    lines.append("**流程步骤**：")
                    lines.append("")
                    lines.append("| # | 页面 | 操作 | 输入 |")
                    lines.append("|---|------|------|------|")
                    for idx, step in enumerate(flow.steps, 1):
                        input_str = " — "
                        if step.input:
                            input_str = ", ".join(f"{k}: {v}" for k, v in step.input.items())
                        lines.append(f"| {idx} | {step.screen} | {step.action} | {input_str} |")
                    lines.append("")

                # Postconditions
                if flow.postconditions:
                    lines.append("**后置条件**：")
                    for pc in flow.postconditions:
                        lines.append(f"- {pc}")
                    lines.append("")

                # Error flows
                if flow.error_flows:
                    lines.append("**异常流程**：")
                    lines.append("")
                    lines.append("| 异常场景 | 预期行为 |")
                    lines.append("|---------|---------|")
                    for ef in flow.error_flows:
                        lines.append(f"| {ef.name} | {ef.expected} |")
                    lines.append("")

        # -- Pages --
        if module.pages:
            lines.append("### 页面")
            lines.append("")
            lines.append("| 页面ID | 名称 | 关键元素 | 入口 |")
            lines.append("|--------|------|----------|------|")
            for page in module.pages:
                elements = "、".join(page.elements) if page.elements else "—"
                entries = "、".join(page.entry_points) if page.entry_points else "—"
                lines.append(f"| {page.id} | {page.name} | {elements} | {entries} |")
            lines.append("")

    # ---- Business rules (outside modules = cross-cutting) ----
    if req.business_rules:
        lines.append("---")
        lines.append("")
        lines.append("## 业务规则")
        lines.append("")
        lines.append("| 规则ID | 描述 | 适用场景 |")
        lines.append("|--------|------|---------|")
        for rule in req.business_rules:
            applies = "、".join(rule.applies_to) if rule.applies_to else "—"
            lines.append(f"| {rule.id} | {rule.description} | {applies} |")
        lines.append("")

    return "\n".join(lines)