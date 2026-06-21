from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ASSERTION_OPERATORS = ["eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains", "type", "regex", "in"]

ASSERTION_TYPES = ["jsonpath", "response_time", "header", "status_code", "json_schema"]

AUTH_TYPES = ["none", "bearer", "basic", "api_key"]

PROJECT_TYPES = ["api", "web", "mobile"]

PRIORITY_LEVELS = ["P0", "P1", "P2", "P3"]

PROJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "base_url"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "type": {"type": "string", "enum": PROJECT_TYPES},
        "base_url": {"type": "string", "format": "uri"},
        "auth": {
            "type": "object",
            "required": ["type"],
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": AUTH_TYPES},
                "token_env": {"type": "string"},
                "username_env": {"type": "string"},
                "password_env": {"type": "string"},
                "key_env": {"type": "string"},
                "header_name": {"type": "string"},
            },
        },
        "default_env": {"type": "string"},
        "specs": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "timeout": {"type": "integer", "minimum": 0},
        "retry": {"type": "integer", "minimum": 0},
        "variables": {"type": "object"},
        "proxy": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "http": {"type": ["string", "null"]},
                "https": {"type": ["string", "null"]},
                "no_proxy": {"type": "array", "items": {"type": "string"}},
            },
        },
        "verify_ssl": {"type": "boolean"},
        "setup": {"type": "array", "items": {"type": "string"}},
        "teardown": {"type": "array", "items": {"type": "string"}},
        "devices": {"type": "object"},
    },
}

ENV_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name"],
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "base_url": {"type": ["string", "null"]},
        "variables": {"type": "object"},
        "auth": {
            "type": "object",
            "required": ["type"],
            "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": AUTH_TYPES},
                "token_env": {"type": "string"},
                "username_env": {"type": "string"},
                "password_env": {"type": "string"},
                "key_env": {"type": "string"},
                "header_name": {"type": "string"},
            },
        },
    },
}

TESTCASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "name", "type", "priority", "request", "expect"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1, "pattern": r"^TC-[A-Z]+-[A-Z0-9]+-\d+$"},
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string", "enum": ["api", "web", "mobile"]},
        "priority": {"type": "string", "enum": PRIORITY_LEVELS},
        "tags": {"type": "array", "items": {"type": "string"}},
        "disabled": {"type": "boolean"},
        "environments": {"type": "array", "items": {"type": "string"}},
        "skip_if": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["condition", "reason"],
                "additionalProperties": False,
                "properties": {
                    "condition": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "request": {
            "type": "object",
            "required": ["method", "path"],
            "additionalProperties": False,
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]},
                "path": {"type": "string"},
                "headers": {"type": "object"},
                "params": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "object"},
                        "body": {"type": "object"},
                        "form": {"type": "object"},
                    },
                },
            },
        },
        "expect": {
            "type": "object",
            "required": ["status"],
            "additionalProperties": False,
            "properties": {
                "status": {"type": "integer", "minimum": 100, "maximum": 599},
                "body": {"type": "object"},
                "assertions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["type", "operator", "expected"],
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string", "enum": ASSERTION_TYPES},
                            "path": {"type": "string"},
                            "operator": {"type": "string", "enum": ASSERTION_OPERATORS},
                            "expected": {},
                            "name": {"type": "string"},
                        },
                    },
                },
            },
        },
        "data_driven": {
            "type": "object",
            "required": ["parameters"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "parameters": {"type": "array", "items": {"type": "object"}, "minItems": 1},
                "parameterized_fields": {"type": "array", "items": {"type": "string"}},
            },
        },
        "extract": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "required": ["type"],
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string", "enum": ["jsonpath", "header", "regex", "status_code"]},
                    "path": {"type": "string"},
                    "name": {"type": "string"},
                    "pattern": {"type": "string"},
                },
            },
        },
        "hooks": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "before": {"type": "array", "items": {"type": "string"}},
                "after": {"type": "array", "items": {"type": "string"}},
            },
        },
        "depends": {"type": "array", "items": {"type": "string"}},
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "author": {"type": "string"},
                "version": {"type": "integer", "minimum": 1},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "changelog": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["version", "date", "author", "message"],
                        "additionalProperties": False,
                        "properties": {
                            "version": {"type": "integer"},
                            "date": {"type": "string"},
                            "author": {"type": "string"},
                            "message": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}

SUITE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "cases": {"type": "array", "items": {"type": "string"}},
        "case_dirs": {"type": "array", "items": {"type": "string"}},
        "setup": {"type": "array", "items": {"type": "string"}},
        "teardown": {"type": "array", "items": {"type": "string"}},
        "workers": {"type": ["integer", "null"], "minimum": 1},
        "retry": {"type": ["integer", "null"], "minimum": 0},
        "fail_fast": {"type": ["integer", "null"], "minimum": 0},
    },
}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_json(data: dict[str, Any], schema: dict[str, Any]) -> ValidationResult:
    import jsonschema

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    if not errors:
        return ValidationResult(valid=True)

    formatted: list[str] = []
    for err in errors:
        path = ".".join(str(p) for p in err.absolute_path) if err.absolute_path else "(root)"
        formatted.append(f"{path}: {err.message}")

    return ValidationResult(valid=False, errors=formatted)
