from testmind.models.result import CaseResult, AssertionResult


def test_case_result_creation():
    cr = CaseResult(
        case_id="TC-API-USER-001",
        run_id="run-001",
        env="dev",
        status="pass",
    )
    assert cr.case_id == "TC-API-USER-001"
    assert cr.status == "pass"


def test_assertion_result():
    ar = AssertionResult(
        type="status_code",
        expected=200,
        actual=200,
        passed=True,
    )
    assert ar.passed is True