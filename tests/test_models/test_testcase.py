from testmind.models.testcase import RequestDef, ExpectDef, TestCase


def test_testcase_creation():
    tc = TestCase(
        id="TC-API-USER-001",
        name="create user",
        request=RequestDef(method="POST", path="/users"),
        expect=ExpectDef(status=201),
    )
    assert tc.id == "TC-API-USER-001"
    assert tc.request.method == "POST"


def test_compute_fingerprint():
    tc = TestCase(
        id="TC-API-USER-001",
        name="create user",
        request=RequestDef(method="POST", path="/users"),
        expect=ExpectDef(status=201),
    )
    fp = tc.compute_fingerprint()
    assert isinstance(fp, str)
    assert len(fp) == 64