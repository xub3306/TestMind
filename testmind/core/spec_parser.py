from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testmind.config.settings import load_project_config
from testmind.models.project import ApiSpec, BodyInfo, EndpointInfo, ParamInfo, SchemaInfo, SpecSource


class ParseResult:
    def __init__(
        self,
        endpoints_count: int,
        api_spec_path: str,
        format: str,
        endpoints: list[dict[str, Any]] | None = None,
    ) -> None:
        self.endpoints_count = endpoints_count
        self.api_spec_path = api_spec_path
        self.format = format
        self.endpoints = endpoints or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoints_count": self.endpoints_count,
            "api_spec_path": self.api_spec_path,
            "format": self.format,
            "endpoints": self.endpoints,
        }


class SaveResult:
    def __init__(self, api_spec_path: str, endpoints_count: int) -> None:
        self.api_spec_path = api_spec_path
        self.endpoints_count = endpoints_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_spec_path": self.api_spec_path,
            "endpoints_count": self.endpoints_count,
        }


class SpecParser:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def parse(self, spec_path: str, project_name: str | None = None) -> ParseResult:
        """Synchronous wrapper for :meth:`parse_async`."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.parse_async(spec_path, project_name))
                return future.result()
        return asyncio.run(self.parse_async(spec_path, project_name))

    async def parse_async(
        self, spec_path: str, project_name: str | None = None
    ) -> ParseResult:
        spec_file = Path(spec_path)
        if not spec_file.is_absolute():
            project_dir = self._resolve_project_dir(project_name)
            if project_dir:
                spec_file = project_dir / "testmind" / spec_path

        if not spec_file.is_file():
            raise FileNotFoundError(f"Spec file not found: {spec_file}")

        raw = spec_file.read_text(encoding="utf-8")
        spec_data = self._load_spec(raw, spec_file)

        spec_format = self._detect_format(spec_data)
        raw_endpoints = self._extract_endpoints(spec_data)

        # Build ApiSpec with properly typed EndpointInfo objects
        endpoint_infos: list[EndpointInfo] = []
        for ep in raw_endpoints:
            endpoint_infos.append(EndpointInfo(
                path=ep["path"],
                method=ep["method"],
                summary=ep.get("summary", ""),
                parameters=ep.get("parameters"),
                request_body=ep.get("request_body"),
                responses=ep.get("responses"),
                security=ep.get("security"),
            ))

        api_spec = ApiSpec(
            source=SpecSource(
                type=spec_format,
                path=str(spec_path),
                extracted_at=datetime.now(timezone.utc).isoformat(),
            ),
            endpoints=endpoint_infos,
        )

        specs_dir = spec_file.parent
        api_spec_path = specs_dir / "api-spec.json"
        # Use by_alias=True so JSON keys use OpenAPI-style names ("in", "schema")
        api_spec_path.write_text(
            json.dumps(api_spec.model_dump(by_alias=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Flatten model objects to plain dicts so ParseResult.to_dict() is JSON-serializable
        json_endpoints = json.loads(json.dumps(
            [ep.model_dump(by_alias=True) for ep in endpoint_infos],
            ensure_ascii=False,
        ))

        return ParseResult(
            endpoints_count=len(endpoint_infos),
            api_spec_path=str(api_spec_path),
            format=spec_format,
            endpoints=json_endpoints,
        )

    def _load_spec(self, raw: str, spec_file: Path) -> dict[str, Any]:
        if spec_file.suffix in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
        return self._resolve_refs(data, data)

    def _resolve_refs(self, obj: Any, root: dict[str, Any]) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj:
                return self._follow_ref(obj["$ref"], root)
            return {k: self._resolve_refs(v, root) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_refs(item, root) for item in obj]
        return obj

    def _follow_ref(self, ref: str, root: dict[str, Any]) -> Any:
        parts = ref.lstrip("#/").split("/")
        current: Any = root
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, {})
            else:
                return {}
        return self._resolve_refs(current, root)

    def _detect_format(self, spec_data: dict[str, Any]) -> str:
        if spec_data.get("openapi", "").startswith("3"):
            return "openapi_3.0"
        if spec_data.get("swagger", "").startswith("2"):
            return "swagger_2.0"
        if "openapi" in spec_data:
            return "openapi"
        if "swagger" in spec_data:
            return "swagger"
        return "unknown"

    def _extract_endpoints(self, spec_data: dict[str, Any]) -> list[dict[str, Any]]:
        endpoints: list[dict[str, Any]] = []
        paths = spec_data.get("paths", {})

        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method.lower() not in (
                    "get", "post", "put", "patch", "delete", "head", "options",
                ):
                    continue
                if not isinstance(details, dict):
                    continue

                parameters = self._extract_parameters(details)
                request_body = self._extract_request_body(details)
                responses = self._extract_responses(details)
                security = self._normalize_security(details.get("security"))

                endpoints.append({
                    "path": path,
                    "method": method.upper(),
                    "summary": details.get("summary", ""),
                    "parameters": parameters if parameters else None,
                    "request_body": request_body,
                    "responses": responses if responses else None,
                    "security": security,
                })

        return endpoints

    def _extract_parameters(self, details: dict[str, Any]) -> list[ParamInfo] | None:
        """Extract parameters from an endpoint definition.

        Returns a list of :class:`ParamInfo` objects, or ``None`` if
        there are no parameters.
        """
        params = details.get("parameters", [])
        if not params:
            return None
        result: list[ParamInfo] = []
        for p in params:
            if not isinstance(p, dict):
                continue
            result.append(ParamInfo(
                name=p.get("name", ""),
                location=p.get("in", "query"),
                required=p.get("required", False),
                schema_=p.get("schema", {}),
                description=p.get("description", ""),
            ))
        return result or None

    def _extract_request_body(self, details: dict[str, Any]) -> BodyInfo | None:
        """Extract request body definition from an endpoint.

        Returns a :class:`BodyInfo` object, or ``None`` if there is no
        request body.
        """
        rb = details.get("requestBody")
        if not rb or not isinstance(rb, dict):
            return None
        content = rb.get("content", {})
        for content_type, media in content.items():
            return BodyInfo(
                content_type=content_type,
                required=rb.get("required", False),
                schema_=media.get("schema", {}),
            )
        return None

    def _extract_responses(self, details: dict[str, Any]) -> dict[str, SchemaInfo] | None:
        """Extract response schemas from an endpoint.

        Returns a dict mapping status code strings to :class:`SchemaInfo`
        objects, or ``None`` if there are no responses.
        """
        responses = details.get("responses", {})
        if not responses:
            return None
        result: dict[str, SchemaInfo] = {}
        for code, resp in responses.items():
            if not isinstance(resp, dict):
                continue
            result[code] = SchemaInfo(
                description=resp.get("description", ""),
                schema_=resp.get("schema", {}),
            )
        return result or None

    @staticmethod
    def _normalize_security(
        security: list[dict[str, list[str]]] | None,
    ) -> list[str] | None:
        """Normalize OpenAPI security entries to a flat list of scheme names.

        OpenAPI defines security as ``[{"bearerAuth": []}]``, but
        ``EndpointInfo.security`` expects ``["bearerAuth"]``.
        """
        if security is None:
            return None
        names: list[str] = []
        for entry in security:
            if isinstance(entry, dict):
                names.extend(entry.keys())
            elif isinstance(entry, str):
                names.append(entry)
        return names if names else None

    def _resolve_project_dir(self, project_name: str | None = None) -> Path | None:
        if project_name:
            try:
                cfg = load_project_config(project_name)
                return cfg.project_dir
            except (FileNotFoundError, Exception):
                pass
        return None


class SpecSaver:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def save(
        self,
        endpoints: list[dict[str, Any]],
        source_info: dict[str, Any],
        project_name: str | None = None,
    ) -> SaveResult:
        """Synchronous wrapper for :meth:`save_async`."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.save_async(endpoints, source_info, project_name))
                return future.result()
        return asyncio.run(self.save_async(endpoints, source_info, project_name))

    async def save_async(
        self,
        endpoints: list[dict[str, Any]],
        source_info: dict[str, Any],
        project_name: str | None = None,
    ) -> SaveResult:
        project_dir = self._resolve_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"Project not found: {project_name}")

        specs_dir = project_dir / "testmind" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)

        api_spec = ApiSpec(
            source=SpecSource(
                type=source_info.get("type", "manual"),
                path=source_info.get("path"),
                url=source_info.get("url"),
                extracted_at=datetime.now(timezone.utc).isoformat(),
            ),
            endpoints=[EndpointInfo(**ep) if isinstance(ep, dict) else ep for ep in endpoints],
        )

        api_spec_path = specs_dir / "api-spec.json"
        api_spec_path.write_text(
            json.dumps(api_spec.model_dump(by_alias=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return SaveResult(
            api_spec_path=str(api_spec_path),
            endpoints_count=len(endpoints),
        )

    def _resolve_project_dir(self, project_name: str | None = None) -> Path | None:
        if project_name:
            try:
                cfg = load_project_config(project_name)
                return cfg.project_dir
            except (FileNotFoundError, Exception):
                pass
        return None
