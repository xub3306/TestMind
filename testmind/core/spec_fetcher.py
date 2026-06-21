from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from testmind.config.settings import load_project_config

DISCOVERY_PATHS_MVP = [
    "/v3/api-docs",
    "/v2/api-docs",
    "/swagger.json",
    "/openapi.json",
    "/swagger.yaml",
]

DISCOVERY_PATHS_EXTENDED = [
    "/v3/api-docs/swagger.json",
    "/swagger-resources",
    "/api-docs",
    "/docs",
    "/.well-known/openapi",
    "/openapi.yaml",
]


class SpecFetchResult:
    def __init__(self, found: list[dict[str, Any]], base_url: str) -> None:
        self.found = found
        self.base_url = base_url

    def to_dict(self) -> dict[str, Any]:
        return {"found": self.found, "base_url": self.base_url}


class FetchResult:
    def __init__(
        self,
        file_path: str,
        format: str,
        size_bytes: int,
        url: str,
    ) -> None:
        self.file_path = file_path
        self.format = format
        self.size_bytes = size_bytes
        self.url = url

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "url": self.url,
        }


class SpecFetcher:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def discover(self, base_url: str, project_name: str | None = None) -> SpecFetchResult:
        """Synchronous wrapper for :meth:`discover_async`."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.discover_async(base_url, project_name))
                return future.result()
        return asyncio.run(self.discover_async(base_url, project_name))

    async def discover_async(self, base_url: str, project_name: str | None = None) -> SpecFetchResult:
        """Discover API spec URLs from *base_url*.

        Args:
            base_url: The base URL to probe for spec endpoints.
            project_name: Optional project name (used to resolve config).
        """
        base_url = base_url.rstrip("/")
        found: list[dict[str, Any]] = []

        # trust_env=False avoids silently inheriting OS-level proxy
        # settings (e.g. IE/Edge on Windows), which can reroute
        # localhost traffic and produce misleading 502 responses.
        # Mirrors the same fix applied in runner._send_request.
        async with httpx.AsyncClient(timeout=10, verify=False, trust_env=False) as client:
            tasks = [
                self._probe_url(client, base_url + path)
                for path in DISCOVERY_PATHS_MVP
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, dict):
                    found.append(result)

        return SpecFetchResult(found=found, base_url=base_url)

    async def _probe_url(
        self, client: httpx.AsyncClient, url: str
    ) -> dict[str, Any] | None:
        try:
            resp = await client.head(url, follow_redirects=True)
            if resp.status_code == 200:
                fmt = self._detect_format(url, resp)
                return {"url": url, "format": fmt, "status": resp.status_code}
            if resp.status_code == 405:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    fmt = self._detect_format(url, resp)
                    return {"url": url, "format": fmt, "status": resp.status_code}
        except httpx.HTTPError:
            pass
        return None

    def fetch(
        self,
        url: str,
        project_name: str | None = None,
        save_path: str | None = None,
    ) -> FetchResult:
        """Synchronous wrapper for :meth:`fetch_async`."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.fetch_async(url, project_name, save_path))
                return future.result()
        return asyncio.run(self.fetch_async(url, project_name, save_path))

    async def fetch_async(
        self,
        url: str,
        project_name: str | None = None,
        save_path: str | None = None,
    ) -> FetchResult:
        # trust_env=False — see discover_async for rationale.
        async with httpx.AsyncClient(timeout=30, verify=False, trust_env=False) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()

        content = resp.text
        fmt = self._detect_format(url, resp)

        target_dir = self._resolve_specs_dir(project_name)
        if save_path:
            target_file = Path(save_path)
            if not target_file.is_absolute():
                target_file = target_dir / target_file
        else:
            filename = self._derive_filename(url, fmt)
            target_file = target_dir / filename

        target_file.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "yaml" and target_file.suffix == ".json":
            import yaml
            data = yaml.safe_load(content)
            target_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            target_file.write_text(content, encoding="utf-8")

        size = target_file.stat().st_size
        return FetchResult(
            file_path=str(target_file),
            format=fmt,
            size_bytes=size,
            url=url,
        )

    def _detect_format(self, url: str, response: httpx.Response) -> str:
        if url.endswith(".yaml") or url.endswith(".yml"):
            return "yaml"
        if url.endswith(".json"):
            return "json"
        content_type = response.headers.get("content-type", "")
        if "yaml" in content_type:
            return "yaml"
        if "json" in content_type:
            return "json"
        if "html" in content_type:
            return "html"
        if "markdown" in content_type or "text/plain" in content_type:
            return "markdown"
        try:
            json.loads(response.text)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass
        return "unknown"

    def _derive_filename(self, url: str, fmt: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = Path(parsed.path)
        if path.name:
            return path.name
        ext = ".json" if fmt == "json" else ".yaml" if fmt == "yaml" else ".txt"
        return f"spec{ext}"

    def _resolve_specs_dir(self, project_name: str | None = None) -> Path:
        if project_name:
            try:
                cfg = load_project_config(project_name)
                if cfg.project_dir:
                    return cfg.project_dir / "testmind" / "specs"
            except (FileNotFoundError, Exception):
                pass
        return Path("testmind") / "specs"
