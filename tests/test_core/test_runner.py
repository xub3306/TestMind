"""Tests for core modules: runner, assertion, variable, spec_parser, etc."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from testmind.core.runner import (
    EXIT_ALL_PASS,
    EXIT_CONFIG_ERROR,
    EXIT_HAS_ERROR,
    EXIT_HAS_FAIL,
    EXIT_MCP_SERVER_FAIL,
    Runner,
    _generate_run_id,
    validate_single_case,
)
from testmind.core.assertion import (
    assert_response,
    _compare,
    _check_type,
    _resolve_jsonpath_value,
)
from testmind.core.variable import (
    replace_variables,
    build_variable_context,
    extract_variables,
)
from testmind.core.spec_fetcher import SpecFetcher, SpecFetchResult, FetchResult
from testmind.core.spec_parser import SpecParser, SpecSaver, ParseResult
from testmind.core.requirements_saver import RequirementsSaver
from testmind.config.settings import ProjectConfig


# ---------------------------------------------------------------------------
# Runner unit tests
# ---------------------------------------------------------------------------


class TestExitCodes:
    """Verify exit code constants."""

    def test_exit_code_values(self):
        assert EXIT_ALL_PASS == 0
        assert EXIT_HAS_FAIL == 1
        assert EXIT_HAS_ERROR == 2
        assert EXIT_CONFIG_ERROR == 10
        assert EXIT_MCP_SERVER_FAIL == 20


class TestRunId:
    """Verify run_id generation format: {YYYYMMDD}_{HHMMSS}_{random4}."""

    def test_format(self):
        run_id = _generate_run_id()
        parts = run_id.split("_")
        assert len(parts) == 3, f"Expected 3 parts, got {parts}"
        # First part: date YYYYMMDD (8 digits)
        assert len(parts[0]) == 8
        # Second part: time HHMMSS (6 digits)
        assert len(parts[1]) == 6
        # Third part: random 4 chars
        assert len(parts[2]) == 4

    def test_unique(self):
        ids = {_generate_run_id() for _ in range(10)}
        assert len(ids) == 10  # All unique


class TestValidateSingleCase:
    """Test validate_single_case function."""

    def test_valid_case(self):
        case_json = {
            "id": "TC-API-USERS-001",
            "name": "Get users",
            "type": "api",
            "priority": "P1",
            "request": {"method": "GET", "path": "/api/users"},
            "expect": {"status": 200},
        }
        result = validate_single_case(case_json)
        assert result.valid, f"Expected valid, got errors: {result.errors}"

    def test_missing_required_fields(self):
        case_json = {"name": "Missing ID"}
        result = validate_single_case(case_json)
        assert not result.valid
        assert len(result.errors) > 0

    def test_to_dict(self):
        case_json = {
            "id": "TC-API-USERS-001",
            "name": "Get users",
            "type": "api",
            "priority": "P1",
            "request": {"method": "GET", "path": "/api/users"},
            "expect": {"status": 200},
        }
        result = validate_single_case(case_json)
        d = result.to_dict()
        assert "case_id" in d
        assert "valid" in d
        assert "errors" in d


# ---------------------------------------------------------------------------
# Assertion tests
# ---------------------------------------------------------------------------


class TestAssertion:
    """Test assertion engine."""

    def test_status_code_pass(self):
        from testmind.models.testcase import ExpectDef
        response = {"status_code": 200, "headers": {}, "body": {}}
        results = assert_response(None, response, {"status": 200})
        assert len(results) == 1
        assert results[0].passed
        assert results[0].type == "status_code"

    def test_status_code_fail(self):
        response = {"status_code": 404, "headers": {}, "body": {}}
        results = assert_response(None, response, {"status": 200})
        assert len(results) == 1
        assert not results[0].passed

    def test_jsonpath_assertion(self):
        from testmind.models.testcase import AssertionDef
        case_mock = None
        response = {"status_code": 200, "headers": {}, "body": {"data": {"id": 42}}}
        assertions = [
            AssertionDef(type="jsonpath", path="$.data.id", operator="eq", expected=42),
        ]
        results = assert_response(case_mock, response, {"status": 200, "assertions": [a.model_dump() for a in assertions]})
        assert any(r.passed for r in results if r.type == "jsonpath")

    def test_compare_operators(self):
        assert _compare(10, "eq", 10) is True
        assert _compare(10, "ne", 20) is True
        assert _compare(11, "gt", 10) is True
        assert _compare(10, "gte", 10) is True
        assert _compare(9, "lt", 10) is True
        assert _compare(10, "lte", 10) is True
        assert _compare("hello world", "contains", "world") is True

    def test_check_type(self):
        assert _check_type(42, "int") is True
        assert _check_type("hello", "str") is True
        assert _check_type(3.14, "float") is True
        assert _check_type(True, "bool") is True
        assert _check_type([1, 2], "list") is True
        assert _check_type({"a": 1}, "dict") is True
        assert _check_type(None, "null") is True


# ---------------------------------------------------------------------------
# Variable tests
# ---------------------------------------------------------------------------


class TestVariables:
    """Test variable replacement and context building."""

    def test_replace_string(self):
        ctx = {"base_url": "https://api.example.com", "user_id": "123"}
        result = replace_variables("{{base_url}}/users/{{user_id}}", ctx)
        assert result == "https://api.example.com/users/123"

    def test_builtin_timestamp(self):
        result = replace_variables("ts={{timestamp}}", {})
        assert result.startswith("ts=")
        assert len(result) > 3

    def test_builtin_uuid(self):
        result = replace_variables("id={{uuid}}", {})
        assert len(result) > 10

    def test_builtin_random_int(self):
        result = replace_variables("n={{random_int}}", {})
        assert result.startswith("n=")
        n_val = int(result.split("=")[1])
        assert 10000 <= n_val <= 99999

    def test_builtin_random_string(self):
        result = replace_variables("s={{random_string}}", {})
        assert len(result) > 2

    def test_builtin_random_email(self):
        result = replace_variables("e={{random_email}}", {})
        assert "@" in result

    def test_nested_dict_replacement(self):
        ctx = {"token": "abc123"}
        data = {"headers": {"Authorization": "Bearer {{token}}"}, "body": {"token": "{{token}}"}}
        result = replace_variables(data, ctx)
        assert result["headers"]["Authorization"] == "Bearer abc123"
        assert result["body"]["token"] == "abc123"

    def test_build_variable_context_priority(self):
        # CLI > env > project > case
        ctx = build_variable_context(
            cli_vars={"key": "cli"},
            env_vars={"key": "env"},
            project_vars={"key": "project"},
            case_vars={"key": "case"},
        )
        assert ctx["key"] == "cli"

    def test_build_variable_context_fallback(self):
        ctx = build_variable_context(
            env_vars={"key": "env"},
            project_vars={"key2": "project"},
        )
        assert ctx["key"] == "env"
        assert ctx["key2"] == "project"

    def test_extract_variables_jsonpath(self):
        response = {"body": {"data": {"id": 42}}, "headers": {}}
        extract_defs = {"user_id": {"type": "jsonpath", "path": "$.data.id"}}
        result = extract_variables(response, extract_defs)
        assert result["user_id"] == "42"

    def test_extract_variables_header(self):
        response = {"headers": {"X-Request-Id": "req-123"}}
        extract_defs = {"req_id": {"type": "header", "name": "X-Request-Id"}}
        result = extract_variables(response, extract_defs)
        assert result["req_id"] == "req-123"

    def test_extract_variables_status_code(self):
        response = {"status_code": 200}
        extract_defs = {"status": {"type": "status_code"}}
        result = extract_variables(response, extract_defs)
        assert result["status"] == "200"


# ---------------------------------------------------------------------------
# SpecFetcher tests
# ---------------------------------------------------------------------------


class TestSpecFetcher:
    """Test SpecFetcher discovery pattern definitions."""

    def test_discovery_paths_exist(self):
        from testmind.core.spec_fetcher import DISCOVERY_PATHS_MVP
        assert len(DISCOVERY_PATHS_MVP) > 0
        assert "/v3/api-docs" in DISCOVERY_PATHS_MVP
        assert "/swagger.json" in DISCOVERY_PATHS_MVP

    def test_fetcher_init(self):
        fetcher = SpecFetcher(config=None)
        assert fetcher.config is None

    def test_detect_format_json(self):
        fetcher = SpecFetcher(config=None)
        import httpx
        resp_mock = MagicMock(spec=httpx.Response)
        resp_mock.headers = {"content-type": "application/json"}
        fmt = fetcher._detect_format("https://example.com/spec.json", resp_mock)
        assert fmt == "json"

    def test_detect_format_yaml(self):
        fetcher = SpecFetcher(config=None)
        import httpx
        resp_mock = MagicMock(spec=httpx.Response)
        resp_mock.headers = {"content-type": "application/x-yaml"}
        fmt = fetcher._detect_format("https://example.com/spec.yaml", resp_mock)
        assert fmt == "yaml"


# ---------------------------------------------------------------------------
# SpecParser tests
# ---------------------------------------------------------------------------


class TestSpecParser:
    """Test spec parsing with OpenAPI 3.0 spec."""

    def test_parse_openapi3(self, tmp_path):
        spec_data = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0"},
            "paths": {
                "/users": {
                    "get": {
                        "summary": "List users",
                        "parameters": [
                            {"name": "page", "in": "query", "required": False, "schema": {"type": "integer"}},
                        ],
                        "responses": {"200": {"description": "Success"}},
                    },
                    "post": {
                        "summary": "Create user",
                        "requestBody": {
                            "content": {"application/json": {"schema": {"type": "object"}}},
                            "required": True,
                        },
                        "responses": {"201": {"description": "Created"}},
                    },
                },
            },
        }
        spec_file = tmp_path / "openapi.json"
        spec_file.write_text(json.dumps(spec_data), encoding="utf-8")

        parser = SpecParser(config=None)
        result = parser.parse(str(spec_file))
        assert result.endpoints_count == 2
        assert result.format == "openapi_3.0"
        # Check that endpoints are properly structured
        for ep in result.endpoints:
            assert ep["path"] in ("/users",)
            assert ep["method"] in ("GET", "POST")


# ---------------------------------------------------------------------------
# Runner Runner.get_exit_code tests
# ---------------------------------------------------------------------------


class TestRunnerGetExitCode:
    """Test Runner.get_exit_code."""

    def _make_config(self, tmp_path):
        """Create a minimal ProjectConfig for testing."""
        project_dir = tmp_path / "test_project"
        tm_dir = project_dir / "testmind"
        tm_dir.mkdir(parents=True, exist_ok=True)
        cases_dir = tm_dir / "cases"
        cases_dir.mkdir(parents=True, exist_ok=True)
        envs_dir = tm_dir / "envs"
        envs_dir.mkdir(parents=True, exist_ok=True)

        config_data = {
            "name": "test_project",
            "type": "api",
            "base_url": "http://localhost:8080",
            "default_env": "dev",
        }
        config_file = tm_dir / "project.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        env_data = {"name": "dev", "base_url": "http://localhost:8080"}
        env_file = envs_dir / "dev.json"
        env_file.write_text(json.dumps(env_data), encoding="utf-8")

        return project_dir

    def test_all_pass(self, tmp_path):
        from testmind.models.result import CaseResult
        config = ProjectConfig(name="test", base_url="http://localhost")
        runner = Runner(config)
        results = [
            CaseResult(case_id="TC-001", run_id="r1", env="dev", status="pass"),
            CaseResult(case_id="TC-002", run_id="r1", env="dev", status="pass"),
        ]
        assert runner.get_exit_code(results) == EXIT_ALL_PASS

    def test_has_fail(self, tmp_path):
        from testmind.models.result import CaseResult
        config = ProjectConfig(name="test", base_url="http://localhost")
        runner = Runner(config)
        results = [
            CaseResult(case_id="TC-001", run_id="r1", env="dev", status="pass"),
            CaseResult(case_id="TC-002", run_id="r1", env="dev", status="fail"),
        ]
        assert runner.get_exit_code(results) == EXIT_HAS_FAIL

    def test_has_error(self, tmp_path):
        from testmind.models.result import CaseResult
        config = ProjectConfig(name="test", base_url="http://localhost")
        runner = Runner(config)
        results = [
            CaseResult(case_id="TC-001", run_id="r1", env="dev", status="error"),
        ]
        assert runner.get_exit_code(results) == EXIT_HAS_ERROR