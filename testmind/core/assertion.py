from __future__ import annotations

import importlib.util
import re
import sys
import time
from pathlib import Path
from typing import Any

from testmind.models import AssertionDef, AssertionResult


def assert_response(
    case_id_or_none: Any,
    response: dict[str, Any],
    expect: Any,
    project_dir: str | None = None,
) -> list[AssertionResult]:
    results: list[AssertionResult] = []

    if hasattr(expect, "model_dump"):
        expect_dict = expect.model_dump(exclude_none=True)
    elif isinstance(expect, dict):
        expect_dict = expect
    else:
        expect_dict = {}

    status = expect_dict.get("status")
    if status is not None:
        results.append(_assert_status_code(response, status))

    body_expect = expect_dict.get("body")
    if body_expect and isinstance(body_expect, dict):
        results.extend(_assert_body(response.get("body", {}), body_expect))

    assertions = expect_dict.get("assertions") or []
    for assertion_def in assertions:
        if isinstance(assertion_def, dict):
            ad = AssertionDef(**assertion_def)
        else:
            ad = assertion_def
        results.append(_assert_single(ad, response, project_dir))

    return results


def _assert_status_code(response: dict[str, Any], expected: int) -> AssertionResult:
    actual = response.get("status_code", 0)
    passed = actual == expected
    return AssertionResult(
        type="status_code",
        operator="eq",
        expected=expected,
        actual=actual,
        passed=passed,
        message="" if passed else f"Expected status {expected}, got {actual}",
    )


def _assert_body(body: Any, expectations: dict[str, Any]) -> list[AssertionResult]:
    results: list[AssertionResult] = []
    for path, expected in expectations.items():
        actual = _resolve_path(body, path)
        expected_str = str(expected)

        type_match = re.match(r"^\{\{type:(\w+)\}\}$", expected_str)
        if type_match:
            type_name = type_match.group(1)
            passed = _check_type(actual, type_name)
            results.append(AssertionResult(
                type="jsonpath",
                path=f"$.{path}",
                operator="type",
                expected=f"type:{type_name}",
                actual=type(actual).__name__ if actual is not None else "None",
                passed=passed,
                message="" if passed else f"Expected type {type_name}, got {type(actual).__name__}",
            ))
        else:
            passed = actual == expected
            results.append(AssertionResult(
                type="jsonpath",
                path=f"$.{path}",
                operator="eq",
                expected=expected,
                actual=actual,
                passed=passed,
                message="" if passed else f"Expected {expected!r}, got {actual!r} at {path}",
            ))
    return results


def _assert_single(
    assertion: AssertionDef,
    response: dict[str, Any],
    project_dir: str | None = None,
) -> AssertionResult:
    atype = assertion.type

    if atype == "status_code":
        return _assert_status_code(response, assertion.expected)
    elif atype == "jsonpath":
        return _assert_jsonpath(assertion, response)
    elif atype == "header":
        return _assert_header(assertion, response)
    elif atype == "response_time":
        return _assert_response_time(assertion, response)
    elif atype == "json_schema":
        return _assert_json_schema(assertion, response)
    elif atype == "body_contains":
        return _assert_body_contains(assertion, response)
    elif atype == "custom":
        return _assert_custom(assertion, response, project_dir)
    else:
        return AssertionResult(
            type=atype,
            operator=assertion.operator,
            expected=assertion.expected,
            actual=None,
            passed=False,
            message=f"Unknown assertion type: {atype}",
        )


def _assert_jsonpath(assertion: AssertionDef, response: dict[str, Any]) -> AssertionResult:
    path = assertion.path or ""
    body = response.get("body", {})
    actual = _resolve_jsonpath_value(body, path)
    expected = assertion.expected
    operator = assertion.operator or "eq"

    passed = _compare(actual, operator, expected)
    message = "" if passed else f"jsonpath {path}: {_fmt_op(operator, expected, actual)}"

    return AssertionResult(
        type="jsonpath",
        path=path,
        operator=operator,
        expected=expected,
        actual=actual,
        passed=passed,
        message=message,
    )


def _assert_header(assertion: AssertionDef, response: dict[str, Any]) -> AssertionResult:
    path = assertion.path or ""
    headers = response.get("headers", {})
    actual = headers.get(path, "")
    expected = assertion.expected
    operator = assertion.operator or "eq"

    if operator == "contains":
        passed = expected in str(actual)
    else:
        passed = str(actual) == str(expected)

    message = "" if passed else f"header {path}: expected {expected!r}, got {actual!r}"

    return AssertionResult(
        type="header",
        path=path,
        operator=operator,
        expected=expected,
        actual=actual,
        passed=passed,
        message=message,
    )


def _assert_response_time(assertion: AssertionDef, response: dict[str, Any]) -> AssertionResult:
    actual = response.get("duration_ms", 0)
    expected = assertion.expected
    operator = assertion.operator or "lt"

    passed = _compare(actual, operator, expected)
    message = "" if passed else f"response_time: {_fmt_op(operator, expected, actual)}ms"

    return AssertionResult(
        type="response_time",
        operator=operator,
        expected=expected,
        actual=actual,
        passed=passed,
        message=message,
    )


def _assert_json_schema(assertion: AssertionDef, response: dict[str, Any]) -> AssertionResult:
    try:
        import jsonschema
    except ImportError:
        return AssertionResult(
            type="json_schema",
            operator="match",
            expected=assertion.expected,
            actual=None,
            passed=False,
            message="jsonschema package not installed",
        )

    body = response.get("body", {})
    schema = assertion.expected if isinstance(assertion.expected, dict) else {}
    try:
        jsonschema.validate(body, schema)
        return AssertionResult(
            type="json_schema",
            operator="match",
            expected="<schema>",
            actual="<body>",
            passed=True,
            message="",
        )
    except jsonschema.ValidationError as e:
        return AssertionResult(
            type="json_schema",
            operator="match",
            expected="<schema>",
            actual="<body>",
            passed=False,
            message=str(e.message),
        )


def _assert_body_contains(assertion: AssertionDef, response: dict[str, Any]) -> AssertionResult:
    body = response.get("body", {})
    body_str = str(body)
    expected = str(assertion.expected)
    passed = expected in body_str

    return AssertionResult(
        type="body_contains",
        operator="contains",
        expected=expected,
        actual="<body>",
        passed=passed,
        message="" if passed else f"Body does not contain {expected!r}",
    )


def _assert_custom(
    assertion: AssertionDef,
    response: dict[str, Any],
    project_dir: str | None = None,
) -> AssertionResult:
    name = assertion.name
    if not name or not project_dir:
        return AssertionResult(
            type="custom",
            operator=assertion.operator,
            expected=assertion.expected,
            actual=None,
            passed=False,
            message="Custom assertion requires 'name' and project_dir",
        )

    hook_file = Path(project_dir) / "testmind" / "hooks" / f"assert_{name}.py"
    if not hook_file.is_file():
        return AssertionResult(
            type="custom",
            operator=assertion.operator,
            expected=assertion.expected,
            actual=None,
            passed=False,
            message=f"Custom assertion file not found: assert_{name}.py",
        )

    try:
        module_name = f"testmind_assert_{name}"
        spec = importlib.util.spec_from_file_location(module_name, hook_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module: {hook_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, "assert_"):
            raise AttributeError(f"assert_{name}.py has no 'assert_' function")

        expected_dict = {
            "path": assertion.path,
            "expected": assertion.expected,
            "operator": assertion.operator,
        }
        if isinstance(assertion.expected, dict):
            expected_dict.update(assertion.expected)

        result = module.assert_(response, expected_dict)
        return AssertionResult(
            type="custom",
            operator=assertion.operator,
            expected=assertion.expected,
            actual=result.get("actual"),
            passed=result.get("passed", False),
            message=result.get("message", ""),
        )
    except Exception as e:
        return AssertionResult(
            type="custom",
            operator=assertion.operator,
            expected=assertion.expected,
            actual=None,
            passed=False,
            message=f"Custom assertion error: {e}",
        )


def _resolve_path(obj: Any, path: str) -> Any:
    parts = path.replace(".", "/").split("/")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


def _resolve_jsonpath_value(body: Any, path: str) -> Any:
    try:
        from jsonpath_ng import parse as jp_parse
        matches = jp_parse(path).find(body)
        if matches:
            return matches[0].value
        return None
    except ImportError:
        clean = path.lstrip("$").lstrip(".")
        return _resolve_path(body, clean)


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    try:
        if operator == "eq":
            return actual == expected
        elif operator in ("ne", "neq"):
            return actual != expected
        elif operator == "gt":
            return float(actual) > float(expected)
        elif operator == "gte":
            return float(actual) >= float(expected)
        elif operator == "lt":
            return float(actual) < float(expected)
        elif operator == "lte":
            return float(actual) <= float(expected)
        elif operator == "contains":
            return expected in str(actual)
        elif operator == "not_contains":
            return expected not in str(actual)
        elif operator == "type":
            return _check_type(actual, str(expected))
        elif operator == "regex":
            return bool(re.search(str(expected), str(actual)))
        elif operator == "in":
            return actual in expected
        else:
            return False
    except (TypeError, ValueError):
        return False


def _check_type(value: Any, type_name: str) -> bool:
    type_map = {
        "int": int,
        "str": str,
        "string": str,
        "float": float,
        "bool": bool,
        "list": list,
        "array": list,
        "dict": dict,
        "object": dict,
        "None": type(None),
        "null": type(None),
    }
    expected_type = type_map.get(type_name)
    if expected_type is None:
        return False
    if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
        return True
    return isinstance(value, expected_type)


def _fmt_op(operator: str, expected: Any, actual: Any) -> str:
    op_names = {
        "eq": "==", "ne": "!=", "neq": "!=", "gt": ">",
        "gte": ">=", "lt": "<", "lte": "<=",
        "contains": "contains", "not_contains": "not contains",
        "type": "is type", "regex": "matches", "in": "in",
    }
    op_str = op_names.get(operator, operator)
    return f"{actual!r} {op_str} {expected!r}"
