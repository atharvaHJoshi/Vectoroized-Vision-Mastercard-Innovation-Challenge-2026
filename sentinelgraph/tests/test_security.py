"""Permission enforcement: cross-tenant access denied by the backend.

Acceptance criterion 6: an automated cross-tenant access test is denied.
"""
from src.security import authorizer, Principal


def test_cross_tenant_denied():
    owner = Principal(id="a", name="a", tenant_id="tenant_acme",
                      roles={"investigator"}, cross_tenant=False)
    try:
        authorizer.enforce_tenant(owner, "tenant_globex")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-tenant read must be denied")


def test_same_tenant_allowed():
    owner = Principal(id="a", name="a", tenant_id="tenant_acme",
                      roles={"investigator"}, cross_tenant=False)
    # Should not raise.
    authorizer.enforce_tenant(owner, "tenant_acme")


def test_audit_cross_tenant_allowed():
    auditor = Principal(id="audit", name="audit", tenant_id="tenant_system",
                        roles={"auditor"}, cross_tenant=True)
    authorizer.enforce_tenant(auditor, "tenant_globex")
    authorizer.enforce_tenant(auditor, "tenant_acme")


def test_redaction_preserves_pseudonym():
    from src.security import authorizer as auth
    props = {"id": "acc_1", "account_number": "ACCT-000001", "name": "Victim",
             "sensitivity": "restricted"}
    p = Principal(id="a", name="a", tenant_id="tenant_acme",
                  roles={"investigator"}, cross_tenant=False)
    redacted = auth.redact_props(p, "Account", props)
    assert redacted["id"] == "acc_1"  # stable id preserved
    assert redacted["account_number"] != "ACCT-000001"  # sensitive redacted
    assert redacted["account_number"].startswith("ps:")
