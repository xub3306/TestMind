from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from testmind.models.project import DevicesConfig


class ProxyConfig(BaseModel):
    """HTTP/HTTPS proxy configuration.

    Attributes:
        http: HTTP proxy URL (e.g. ``http://proxy.example.com:8080``).
        https: HTTPS proxy URL.
        no_proxy: Hostnames that should bypass the proxy.
    """

    http: str | None = None
    https: str | None = None
    no_proxy: list[str] = Field(default_factory=list)


class AuthConfig(BaseModel):
    """Authentication configuration using environment variable references.

    Sensitive values (tokens, passwords) are stored as *environment
    variable names*, not the actual secrets.  The runner resolves them
    at execution time.

    Attributes:
        type: Auth mechanism – ``bearer``, ``basic``, ``api_key``,
            ``oauth2``, or ``none``.
        token_env: Env var name holding the bearer token.
        username_env: Env var name holding the basic-auth username.
        password_env: Env var name holding the basic-auth password.
        key_env: Env var name holding the API key.
        header_name: Header name for ``api_key`` auth (default ``X-API-Key``).
    """

    type: str
    token_env: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    key_env: str | None = None
    header_name: str | None = None


class ProjectConfig(BaseModel):
    """Top-level project configuration (``project.json``).

    Attributes:
        name: Project name.
        description: Free-text project description.
        type: Project type – ``api``, ``web``, or ``mobile``.
        base_url: Default base URL for API calls.
        auth: Default authentication configuration.
        default_env: Environment name to use when ``--env`` is omitted.
        specs: List of spec file paths relative to the project root.
        tags: Default tags for all cases in this project.
        timeout: Global request timeout in seconds.
        retry: Default retry count for failed cases.
        variables: Project-level variables (lowest priority).
        proxy: Proxy configuration.
        verify_ssl: Whether to verify SSL certificates.
        setup: Global setup hook names (run before all cases).
        teardown: Global teardown hook names (run after all cases).
        devices: Device configuration for mobile projects.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    type: Literal["api", "web", "mobile"] = "api"
    base_url: str = ""
    auth: AuthConfig | None = None
    default_env: str = "dev"
    specs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    timeout: int = 30
    retry: int = 0
    variables: dict[str, Any] = Field(default_factory=dict)
    proxy: ProxyConfig | None = None
    verify_ssl: bool = True
    setup: list[str] = Field(default_factory=list)
    teardown: list[str] = Field(default_factory=list)
    devices: DevicesConfig | None = None

    _project_dir: Path | None = PrivateAttr(default=None)

    @property
    def project_dir(self) -> Path | None:
        """Resolved filesystem path to the project root directory."""
        return self._project_dir

    @project_dir.setter
    def project_dir(self, value: Path | None) -> None:
        self._project_dir = value

    def get_env_config(self, env_name: str) -> EnvConfig:
        if self._project_dir is None:
            raise ValueError("project_dir is not set; cannot load env config")

        env_file = self._project_dir / "testmind" / "envs" / f"{env_name}.json"
        if not env_file.is_file():
            raise FileNotFoundError(f"Environment config not found: {env_file}")

        with open(env_file, encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("name", env_name)
        return EnvConfig.model_validate(data)


class EnvConfig(BaseModel):
    """Per-environment configuration that overrides project defaults.

    Attributes:
        name: Environment name (e.g. ``dev``, ``staging``, ``prod``).
        base_url: Override for the project ``base_url``.
        variables: Environment-specific variables.
        auth: Override for the project ``auth``.
    """

    name: str
    base_url: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    auth: AuthConfig | None = None


def _find_project_dir(start: Path) -> Path | None:
    current = start.resolve()
    while True:
        candidate = current / "testmind" / "project.json"
        if candidate.is_file():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_project_config(project_path: str = ".") -> ProjectConfig:
    start = Path(project_path).resolve()
    project_dir = _find_project_dir(start)
    if project_dir is None:
        raise FileNotFoundError(
            f"No testmind/project.json found in {start} or any parent directory"
        )

    config_file = project_dir / "testmind" / "project.json"
    with open(config_file, encoding="utf-8") as f:
        data = json.load(f)

    config = ProjectConfig.model_validate(data)
    config.project_dir = project_dir
    return config
