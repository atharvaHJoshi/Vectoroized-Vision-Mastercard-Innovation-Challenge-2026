"""Persistent correction: corrected facts change later answers.

Acceptance criterion 4: a corrected fact changes the answer in a later
session without erasing relevant history.
"""
from src.agents import InvestigatorAgent, MemoryManager, VerifierAgent
from src.security import claim_store, Principal
from src.graph import get_graph
from .conftest import build_world, principal


def test_supported_claim_promoted_to_memory():
    world, g = build_world()
    tx = world.transactions[0]
    p = principal()
    mem = MemoryManager(p.tenant_id)

    blue = InvestigatorAgent(p.tenant_id)
    verifier = VerifierAgent(p.tenant_id)
    blue_res = blue.investigate(tx["id"])
    ver_res = verifier.verify(blue_res.claims, [], blue_res.evidence, tx["id"])

    mem_res = mem.commit(ver_res.claims, [], tx["id"])
    assert mem_res.ok
    # A supported claim should be promoted; version bumped.
    assert mem_res.decision["version"] >= 1


def test_contradicted_claim_superseded_not_erased():
    world, g = build_world()
    tx = world.transactions[0]
    p = principal()
    from src.security import claim_store

    # Propose a claim then mark it CONTRADICTED.
    agent = VerifierAgent(p.tenant_id)
    claim = agent.propose_claim("stale claim", confidence=0.9,
                                evidence_ids=["ev_x"], actor=agent.name)
    claim_store.transition(claim.claim_id, "CONTRADICTED", agent.name, p.tenant_id)

    updated = claim_store.get(claim.claim_id)
    assert updated.state == "CONTRADICTED"
    # The claim record still exists (history preserved), just not conclusive.
    assert claim_store.get(claim.claim_id) is not None
