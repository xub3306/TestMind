"""TestMind project-level data models.

Defines structures for API specifications (``api-spec.json``), business
requirements (``business-requirements.json``), device configurations,
and related sub-models.  All models use Pydantic v2 and support full
JSON serialization/deserialization via ``model_dump()`` and
``model_validate()``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# API Specification models (specs/api-spec.json)
# ---------------------------------------------------------------------------


class ParamInfo(BaseModel):
    """A single API parameter (path, query, header, or cookie).

    Attributes:
        name: Parameter name.
        location: Where the parameter is passed (``path``, ``query``,
            ``header``, ``cookie``).  Accepts the OpenAPI key ``in``
            via the alias.
        required: Whether the parameter is mandatory.
        schema_: JSON Schema describing the parameter's type and
            constraints.  Stored under the JSON key ``schema``.
        description: Human-readable description.
    """

    name: str
    location: str = Field(default="query", alias="in")
    required: bool = False
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    description: str = ""

    model_config = ConfigDict(populate_by_name=True)


class BodyInfo(BaseModel):
    """Request body definition for an endpoint.

    Attributes:
        content_type: MIME type (e.g. ``application/json``).
        required: Whether the request body is mandatory.
        schema_: JSON Schema for the body payload.
    """

    content_type: str
    required: bool = False
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")

    model_config = ConfigDict(populate_by_name=True)


class SchemaInfo(BaseModel):
    """Response schema for a specific HTTP status code.

    Attributes:
        description: Human-readable description of the response.
        schema_: JSON Schema describing the response body.
    """

    description: str = ""
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")

    model_config = ConfigDict(populate_by_name=True)


class EndpointInfo(BaseModel):
    """A single API endpoint, as extracted from an OpenAPI/Swagger spec.

    Attributes:
        path: URL path, e.g. ``/api/users/{id}``.
        method: HTTP method (GET, POST, …).
        summary: Short human-readable description.
        parameters: List of accepted parameters.
        request_body: Request body definition (optional).
        responses: Mapping of status code strings to response schemas.
        security: List of security requirement names.
    """

    path: str
    method: str
    summary: str = ""
    parameters: list[ParamInfo] | None = None
    request_body: BodyInfo | None = None
    responses: dict[str, SchemaInfo] | None = None
    security: list[str] | None = None


class SpecSource(BaseModel):
    """Provenance information for an API specification.

    Attributes:
        type: Source type (e.g. ``swagger``, ``openapi_3.0``, ``manual``).
        path: Local file path, if applicable.
        url: Remote URL, if applicable.
        extracted_at: ISO-8601 timestamp of extraction.
    """

    type: str
    path: str | None = None
    url: str | None = None
    extracted_at: str = ""


class ApiSpec(BaseModel):
    """Root model for a standardised API specification file.

    Attributes:
        format: Specification format version (always
            ``testmind-spec-1.0``).
        source: Provenance information.
        endpoints: List of all API endpoints.
    """

    format: str = "testmind-spec-1.0"
    source: SpecSource
    endpoints: list[EndpointInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Business Requirements models (requirements/business-requirements.json)
# ---------------------------------------------------------------------------


class RequirementsSource(BaseModel):
    """Provenance information for a business requirements document.

    Attributes:
        type: Source type (e.g. ``manual``, ``emulator_android``).
        device: Device name used for exploration (for emulator sources).
        platform: Platform explored (``android``, ``ios``).
        app_package: App package identifier (for mobile sources).
        explored_at: ISO-8601 timestamp of exploration.
        path: Local file path, if applicable.
    """

    type: str
    device: str | None = None
    platform: str | None = None
    app_package: str | None = None
    explored_at: str | None = None
    path: str | None = None


class StepInfo(BaseModel):
    """A single user action step within a business flow.

    Attributes:
        screen: Screen / page name where the action occurs.
        action: Description of the action.
        input: Input data provided during the action.
    """

    screen: str
    action: str
    input: dict[str, Any] | None = None


class ErrorFlow(BaseModel):
    """An error / exception path within a business flow.

    Attributes:
        name: Name of the error condition.
        expected: Expected system response or behaviour.
    """

    name: str
    expected: str


class BusinessFlow(BaseModel):
    """A named sequence of user steps representing a business scenario.

    Attributes:
        id: Flow identifier (e.g. ``FLOW-USER-001``).
        name: Human-readable name.
        description: Longer description of the flow.
        steps: Ordered list of user steps.
        preconditions: Conditions that must hold before the flow.
        postconditions: Conditions that hold after a successful flow.
        error_flows: Alternative error / exception paths.
    """

    id: str
    name: str
    description: str = ""
    steps: list[StepInfo] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    error_flows: list[ErrorFlow] | None = None


class PageInfo(BaseModel):
    """A UI page and its interactive elements.

    Attributes:
        id: Page identifier (e.g. ``PAGE-USER-001``).
        name: Human-readable page name.
        elements: List of element descriptions.
        entry_points: Ways a user can navigate to this page.
    """

    id: str
    name: str
    elements: list[str] = Field(default_factory=list)
    entry_points: list[str] | None = None


class ModuleInfo(BaseModel):
    """A functional module containing flows, pages, and business rules.

    Attributes:
        id: Module identifier (e.g. ``MOD-USER``).
        name: Human-readable module name.
        description: Longer description of the module's scope.
        flows: Business flows within this module.
        pages: UI pages associated with this module.
    """

    id: str
    name: str
    description: str = ""
    flows: list[BusinessFlow] = Field(default_factory=list)
    pages: list[PageInfo] | None = None


class BusinessRule(BaseModel):
    """A business rule that constrains system behaviour.

    Attributes:
        id: Rule identifier (e.g. ``BR-001``).
        description: The rule statement.
        applies_to: List of areas / features this rule applies to.
    """

    id: str
    description: str
    applies_to: list[str] = Field(default_factory=list)


class BusinessRequirements(BaseModel):
    """Root model for a standardised business requirements file.

    Attributes:
        format: Requirements format version (always
            ``testmind-requirements-1.0``).
        project: Project identifier.
        source: Provenance information.
        modules: List of functional modules.
        business_rules: Cross-cutting business rules.
    """

    format: str = "testmind-requirements-1.0"
    project: str
    source: RequirementsSource
    modules: list[ModuleInfo] = Field(default_factory=list)
    business_rules: list[BusinessRule] | None = None


# ---------------------------------------------------------------------------
# Device Configuration models (project.json → devices)
# ---------------------------------------------------------------------------


class DeviceInfo(BaseModel):
    """A single emulator, simulator, or real device entry.

    Attributes:
        name: Device identifier (e.g. ``redroid_11``, ``pixel_8_real``).
        type: Device type – ``emulator``, ``simulator``, or ``real``.
        platform: Operating system platform (``android`` or ``ios``).
        version: OS version string (e.g. ``11``, ``17.0``).
        port: ADB / connection port (mainly for Android emulators).
        udid: Device UDID for real devices.
    """

    name: str
    type: Literal["emulator", "simulator", "real"]
    platform: str
    version: str | None = None
    port: int | None = None
    udid: str | None = None


class PlatformDevices(BaseModel):
    """Device pool for a specific platform (android / ios).

    Attributes:
        default: Name of the default device to use.
        available: List of available devices for this platform.
    """

    default: str
    available: list[DeviceInfo] = Field(default_factory=list)


class DevicesConfig(BaseModel):
    """Top-level device configuration for mobile projects.

    Attributes:
        android: Android device pool (optional, required for mobile).
        ios: iOS device pool (optional, required for mobile).
    """

    android: PlatformDevices | None = None
    ios: PlatformDevices | None = None
