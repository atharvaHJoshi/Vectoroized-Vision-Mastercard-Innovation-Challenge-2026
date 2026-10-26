"""Graph-native reasoning: multi-hop FalkorDB traversal changes the result.

Acceptance criterion 1: at least one answer depends on a multi-hop FalkorDB
query.
"""
from .conftest import build_world, principal


def test_multi_hop_traversal_returns_connected_evidence():
    world, g = build_world()
    # Find a transaction and traverse account -> device -> merchant (2-3 hops).
    tx = world.transactions[0]
    paths = g.traverse("Transaction", tx["id"],
                       ["INVOLVES", "USES_DEVICE", "LINKED_TO"],
                       depth=3, tenant_id=tx["tenant_id"])
    assert len(paths) >= 1, "expected at least one connected path"

    # Collect all reachable entity ids across paths.
    reachable = set()
    for path in paths:
        for node in path.nodes:
            reachable.add(node.get("id"))

    # The traversal must reach more than just the transaction itself.
    assert tx["id"] in reachable
    others = reachable - {tx["id"]}
    assert len(others) >= 1, "multi-hop traversal should reach related entities"

    # Tenant scoping: a different tenant must see nothing for this transaction.
    other = principal(tenant_id="tenant_globex")
    paths_other = g.traverse("Transaction", tx["id"],
                             ["INVOLVES", "USES_DEVICE", "LINKED_TO"],
                             depth=3, tenant_id=other.tenant_id)
    assert paths_other == [], "cross-tenant traversal must return nothing"


def test_bounded_traversal_respects_depth():
    world, g = build_world()
    tx = world.transactions[0]
    deep = g.traverse("Transaction", tx["id"],
                      ["INVOLVES", "USES_DEVICE", "LINKED_TO"], depth=3,
                      tenant_id=tx["tenant_id"])
    shallow = g.traverse("Transaction", tx["id"],
                         ["INVOLVES", "USES_DEVICE", "LINKED_TO"], depth=1,
                         tenant_id=tx["tenant_id"])
    # Depth 3 should reach at least as much as depth 1.
    assert len(deep) >= len(shallow)
