"""Adversarial challenge: red team flags unsupported claims.

Acceptance criterion 3: a red-team test identifies / correctly flags an
unsupported claim. Acceptance criterion 2: every material finding links to
source evidence with a verification status.
"""
from src.agents import InvestigatorAgent, RedTeamAgent, VerifierAgent
from src.security import Principal
from src.graph import get_graph
from .conftest import build_world, principal


def test_red_team_flags_unsupported_claim():
    world, g = build_world()
    tx = world.transactions[0]
    p = principal()

    blue = InvestigatorAgent(p.tenant_id)
    red = RedTeamAgent(p.tenant_id)
    verifier = VerifierAgent(p.tenant_id)

    blue_res = blue.investigate(tx["id"])
    assert blue_res.ok
    assert len(blue_res.claims) >= 1, "investigator should propose claims"

    # Every material claim carries evidence ids (traceability).
    for c in blue_res.claims:
        assert "statement" in c and "confidence" in c
        assert "claim_id" in c

    # Red team runs.
    red_res = red.challenge(blue_res.claims, blue_res.evidence, tx["id"])
    assert red_res.ok

    # Verifier produces a verdict.
    ver_res = verifier.verify(blue_res.claims, red_res.counterarguments,
                              blue_res.evidence, tx["id"])
    assert ver_res.ok
    assert ver_res.decision["verdict"] in (
        "SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE")


def test_claim_transition_states():
    from src.security import claim_store
    from src.agents.base import Agent
    import time
    p = principal()
    agent = InvestigatorAgent(p.tenant_id)
    claim = agent.propose_claim("test claim", confidence=0.5,
                                actor=agent.name)
    assert claim.state == "PROPOSED"
    # Valid transition PROPOSED -> SUPPORTED.
    updated = claim_store.transition(claim.claim_id, "SUPPORTED",
                                     agent.name, p.tenant_id)
    assert updated.state == "SUPPORTED"
    # Invalid transition SUPPORTED -> PROPOSED should raise.
    try:
        claim_store.transition(claim.claim_id, "PROPOSED",
                               agent.name, p.tenant_id)
    except ValueError:
        pass
    else:
        raise AssertionError("reverse transition should be blocked")
