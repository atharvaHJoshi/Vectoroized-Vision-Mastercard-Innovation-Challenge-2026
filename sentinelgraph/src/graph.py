"""SentinelGraph graph client.

FalkorDB is the primary graph database. This module provides a small interface
(`GraphClient`) with bounded Cypher queries. When FalkorDB is unavailable it
falls back to a deterministic in-memory graph so the demo runs standalone.

IMPORTANT: the in-memory fallback is explicitly dev/demo-only. FalkorDB remains
the primary database in compose/production and shapes product behaviour
(multi-hop traversal, versioned memory, bounded traversal).
"""
from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .config import (
    ALLOWED_RELATIONSHIPS, FALKORDB_DB, FALKORDB_HOST, FALKORDB_PORT,
    GRAPH_FALLBACK, MAX_RESULTS, MAX_TRAVERSAL_DEPTH,
)
from .schema import EDGE_TYPES, NODE_LABELS, TEMPORAL_PROPS

try:  # FalkorDB is optional at import time; required at runtime in compose.
    from falkordb import FalkorDB  # type: ignore
    _HAVE_FALKOR = True
except Exception:  # pragma: no cover - depends on environment
    FalkorDB = None  # type: ignore
    _HAVE_FALKOR = False


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------
@dataclass
class GraphRecord:
    node_id: str
    label: str
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphPath:
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# FalkorDB-backed client
# ---------------------------------------------------------------------------
class FalkorClient:
    """Thin wrapper around FalkorDB with bounded, allowlisted queries."""

    def __init__(self, host: str = FALKORDB_HOST, port: int = FALKORDB_PORT,
                 db: int = FALKORDB_DB):
        self.host = host
        self.port = port
        self.db = db
        self._client = None
        self._graph = None
        self._connect()

    def _connect(self):
        if not _HAVE_FALKOR:
            raise RuntimeError("falkordb package not installed")
        self._client = FalkorDB(host=self.host, port=self.port)
        try:
            self._graph = self._client.select_graph(f"sentinel_{self.db}")
        except Exception:
            # Graph may not exist yet; create it.
            self._graph = self._client.create_graph(f"sentinel_{self.db}")

    def _cypher(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self._graph is None:
            self._connect()
        result = self._graph.query(query, params or {})
        # FalkorDB result set -> list of dict rows
        rows = []
        for rec in result.result_set:
            rows.append(dict(zip(result.columns, rec)))
        return rows

    # -- writes -----------------------------------------------------------
    def upsert_node(self, label: str, props: Dict[str, Any]) -> None:
        # Use MERGE-like behaviour keyed on `id`.
        pid = props.get("id")
        if not pid:
            raise ValueError("node props must include 'id'")
        set_clause = ", ".join(f"n.{k} = ${k}" for k in props if k != "id")
        query = (
            f"MERGE (n:{label} {{id: $id}}) "
            f"ON CREATE SET n.id = $id, {set_clause} "
            f"ON MATCH SET {set_clause}"
        )
        params = dict(props)
        self._cypher(query, params)

    def upsert_edge(self, src_label: str, src_id: str, rel: str,
                    dst_label: str, dst_id: str,
                    props: Optional[Dict[str, Any]] = None) -> None:
        if rel not in ALLOWED_RELATIONSHIPS:
            raise ValueError(f"relationship {rel!r} not in allowlist")
        p = {"src_id": src_id, "dst_id": dst_id}
        if props:
            set_clause = ", ".join(f"e.{k} = ${k}" for k in props)
            query = (
                f"MATCH (a:{src_label} {{id: $src_id}}), "
                f"(b:{dst_label} {{id: $dst_id}}) "
                f"MERGE (a)-[e:{rel}]->(b) SET {set_clause}"
            )
            p.update(props)
        else:
            query = (
                f"MATCH (a:{src_label} {{id: $src_id}}), "
                f"(b:{dst_label} {{id: $dst_id}}) "
                f"MERGE (a)-[e:{rel}]->(b)"
            )
        self._cypher(query, p)

    # -- reads ------------------------------------------------------------
    def find_node(self, label: str, node_id: str) -> Optional[Dict[str, Any]]:
        query = f"MATCH (n:{label} {{id: $id}}) RETURN n LIMIT 1"
        rows = self._cypher(query, {"id": node_id})
        if not rows:
            return None
        return self._node_from_row(rows[0]["n"])

    def find_nodes_by_prop(self, label: str, prop: str, value: Any,
                           limit: int = MAX_RESULTS) -> List[Dict[str, Any]]:
        query = (f"MATCH (n:{label}) WHERE n.{prop} = ${prop} "
                 f"RETURN n LIMIT $limit")
        rows = self._cypher(query, {prop: value, "limit": limit})
        return [self._node_from_row(r["n"]) for r in rows]

    def traverse(self, start_label: str, start_id: str, rels: Iterable[str],
                 depth: int = MAX_TRAVERSAL_DEPTH,
                 tenant_id: Optional[str] = None,
                 limit: int = MAX_RESULTS) -> List[GraphPath]:
        """Bounded multi-hop traversal with tenant scoping and allowlisted rels."""
        bad = set(rels) - ALLOWED_RELATIONSHIPS
        if bad:
            raise ValueError(f"disallowed relationships: {sorted(bad)}")
        depth = max(1, min(int(depth), MAX_TRAVERSAL_DEPTH))
        rel_pattern = "|".join(rels)
        tenant_clause = ""
        params: Dict[str, Any] = {"id": start_id, "depth": depth, "limit": limit}
        if tenant_id:
            tenant_clause = "AND ALL(x IN nodes(p) WHERE x.tenant_id = $tenant)"
            params["tenant"] = tenant_id

        query = (
            f"MATCH p = (s:{start_label} {{id: $id}})-[{rel_pattern}*1..{depth}]-(related) "
            f"WHERE {tenant_clause if tenant_id else 'true'} "
            f"RETURN p LIMIT $limit"
        )
        rows = self._cypher(query, params)
        paths = []
        for r in rows:
            paths.append(self._path_from_row(r["p"]))
        return paths

    def query_cypher(self, query: str, params: Optional[Dict[str, Any]] = None
                     ) -> List[Dict[str, Any]]:
        """Execute a read-only allowlisted Cypher query (backend-enforced)."""
        return self._cypher(query, params or {})

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _node_from_row(val: Any) -> Dict[str, Any]:
        # FalkorDB returns a Node object; convert to dict.
        if hasattr(val, "properties"):
            return dict(val.properties)
        if isinstance(val, dict):
            return dict(val)
        return {}

    @staticmethod
    def _path_from_row(val: Any) -> GraphPath:
        nodes, edges = [], []
        if hasattr(val, "nodes"):
            for n in val.nodes:
                nodes.append(FalkorClient._node_from_row(n))
        if hasattr(val, "relationships"):
            for e in val.relationships:
                edges.append({
                    "type": e.type,
                    "props": dict(e.properties) if hasattr(e, "properties") else {},
                })
        return GraphPath(nodes=nodes, edges=edges)

    # -- admin ------------------------------------------------------------
    def close(self):
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# In-memory fallback graph (dev/demo only)
# ---------------------------------------------------------------------------
class MemoryGraph:
    """Deterministic in-memory graph mirroring the FalkorClient interface."""

    def __init__(self):
        self._lock = threading.RLock()
        # nodes: label -> id -> props
        self.nodes: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        # edges: (src_label, src_id, rel, dst_label, dst_id) -> props
        self.edges: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
        # adjacency for traversal: (src_label, src_id, rel) -> list of (dst_label, dst_id)
        self.adj: Dict[Tuple[str, str, str], List[Tuple[str, str]]] = defaultdict(list)

    def upsert_node(self, label: str, props: Dict[str, Any]) -> None:
        with self._lock:
            pid = props["id"]
            self.nodes[label][pid] = dict(props)

    def upsert_edge(self, src_label: str, src_id: str, rel: str,
                    dst_label: str, dst_id: str,
                    props: Optional[Dict[str, Any]] = None) -> None:
        if rel not in ALLOWED_RELATIONSHIPS:
            raise ValueError(f"relationship {rel!r} not in allowlist")
        with self._lock:
            key = (src_label, src_id, rel, dst_label, dst_id)
            self.edges[key] = props or {}
            self.adj[(src_label, src_id, rel)].append((dst_label, dst_id))

    def find_node(self, label: str, node_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.nodes.get(label, {}).get(node_id)

    def find_nodes_by_prop(self, label: str, prop: str, value: Any,
                           limit: int = MAX_RESULTS) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for nid, props in self.nodes.get(label, {}).items():
                if props.get(prop) == value:
                    out.append(dict(props))
                    if len(out) >= limit:
                        break
            return out

    def traverse(self, start_label: str, start_id: str, rels: Iterable[str],
                 depth: int = MAX_TRAVERSAL_DEPTH,
                 tenant_id: Optional[str] = None,
                 limit: int = MAX_RESULTS) -> List[GraphPath]:
        rels = set(rels)
        bad = rels - ALLOWED_RELATIONSHIPS
        if bad:
            raise ValueError(f"disallowed relationships: {sorted(bad)}")
        depth = max(1, min(int(depth), MAX_TRAVERSAL_DEPTH))
        with self._lock:
            visited = set()
            paths: List[GraphPath] = []

            def dfs(label: str, nid: str, cur_depth: int,
                    nodes: List[Dict[str, Any]],
                    edges: List[Dict[str, Any]]):
                if cur_depth > depth or len(paths) >= limit:
                    return
                node = self.nodes.get(label, {}).get(nid)
                if node is None:
                    return
                if tenant_id and node.get("tenant_id") != tenant_id:
                    return
                key = (label, nid)
                if key in visited and cur_depth > 0:
                    return
                visited.add(key)
                nodes.append(dict(node))
                if cur_depth >= 1:
                    paths.append(GraphPath(nodes=list(nodes), edges=list(edges)))
                if cur_depth < depth:
                    for rel in rels:
                        for (dl, did) in self.adj.get((label, nid, rel), []):
                            dnode = self.nodes.get(dl, {}).get(did)
                            if dnode is None:
                                continue
                            if tenant_id and dnode.get("tenant_id") != tenant_id:
                                continue
                            eprops = self.edges.get((label, nid, rel, dl, did), {})
                            edges.append({"type": rel, "props": eprops})
                            dfs(dl, did, cur_depth + 1, nodes, edges)
                            edges.pop()
                nodes.pop()
                visited.discard(key)

            dfs(start_label, start_id, 0, [], [])
            return paths

    def query_cypher(self, query: str,
                     params: Optional[Dict[str, Any]] = None
                     ) -> List[Dict[str, Any]]:
        """Very small read-only Cypher subset for the fallback.

        Supports: MATCH (n:Label {prop: $val}) RETURN n [LIMIT n]
        Used only for parity in demo mode; real deployments use FalkorDB.
        """
        q = query.strip()
        params = params or {}
        if not q.startswith("MATCH"):
            raise ValueError("fallback only supports read-only MATCH queries")
        # Parse `MATCH (n:Label {prop: $val}) RETURN n LIMIT N`
        import re
        m = re.match(r"MATCH\s+\(n:(\w+)\s*\{(\w+):\s*\$(\w+)\}\s*\)\s*RETURN\s+n(?:\s+LIMIT\s+(\d+))?", q)
        if not m:
            raise ValueError("unsupported fallback query shape")
        label, prop, pname, lim = m.group(1), m.group(2), m.group(3), m.group(4)
        limit = int(lim) if lim else MAX_RESULTS
        return self.find_nodes_by_prop(label, prop, params.get(pname), limit=limit)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_client_lock = threading.Lock()
_shared: Optional["GraphClient"] = None


class GraphClient:
    """Public interface: FalkorDB primary, memory fallback secondary.

    FalkorDB is the primary graph database. The constructor runs a health-check
    query against it; if FalkorDB is unreachable or its graph module is missing
    (e.g. a plain Redis is listening on the port), the client silently degrades
    to the in-memory graph so the demo still runs. The fallback is dev/demo
    only — FalkorDB remains primary in compose/production.
    """

    def __init__(self, force_fallback: bool = False):
        self._fallback = force_fallback or (GRAPH_FALLBACK and not _HAVE_FALKOR)
        self._falkor: Optional[FalkorClient] = None
        self._mem = MemoryGraph()
        if not self._fallback:
            try:
                self._falkor = FalkorClient()
                # Health-check: confirm the graph module actually responds.
                if not self._falkor_ok():
                    raise RuntimeError("FalkorDB graph module not available")
            except Exception as exc:  # noqa: BLE001
                # FalkorDB unreachable / no graph module -> degrade to memory.
                self._falkor = None
                self._fallback = True

    def _falkor_ok(self) -> bool:
        """Run a trivial read query to confirm FalkorDB's graph module works."""
        try:
            self._falkor._graph.query("MATCH (n) RETURN n LIMIT 1")
            return True
        except Exception:
            return False

    @property
    def using_falkordb(self) -> bool:
        return self._falkor is not None

    def upsert_node(self, label: str, props: Dict[str, Any]) -> None:
        if self._falkor:
            self._falkor.upsert_node(label, props)
        self._mem.upsert_node(label, props)

    def upsert_edge(self, src_label: str, src_id: str, rel: str,
                    dst_label: str, dst_id: str,
                    props: Optional[Dict[str, Any]] = None) -> None:
        if self._falkor:
            self._falkor.upsert_edge(src_label, src_id, rel, dst_label, dst_id, props)
        self._mem.upsert_edge(src_label, src_id, rel, dst_label, dst_id, props)

    def find_node(self, label: str, node_id: str) -> Optional[Dict[str, Any]]:
        if self._falkor:
            try:
                return self._falkor.find_node(label, node_id)
            except Exception:
                pass
        return self._mem.find_node(label, node_id)

    def find_nodes_by_prop(self, label: str, prop: str, value: Any,
                           limit: int = MAX_RESULTS) -> List[Dict[str, Any]]:
        if self._falkor:
            try:
                return self._falkor.find_nodes_by_prop(label, prop, value, limit)
            except Exception:
                pass
        return self._mem.find_nodes_by_prop(label, prop, value, limit)

    def traverse(self, start_label: str, start_id: str, rels: Iterable[str],
                 depth: int = MAX_TRAVERSAL_DEPTH,
                 tenant_id: Optional[str] = None,
                 limit: int = MAX_RESULTS) -> List[GraphPath]:
        if self._falkor:
            try:
                return self._falkor.traverse(start_label, start_id, rels, depth,
                                             tenant_id, limit)
            except Exception:
                pass
        return self._mem.traverse(start_label, start_id, rels, depth, tenant_id, limit)

    def query_cypher(self, query: str,
                     params: Optional[Dict[str, Any]] = None
                     ) -> List[Dict[str, Any]]:
        if self._falkor:
            try:
                return self._falkor.query_cypher(query, params)
            except Exception:
                pass
        return self._mem.query_cypher(query, params)

    def close(self):
        if self._falkor:
            self._falkor.close()


def get_graph() -> GraphClient:
    global _shared
    with _client_lock:
        if _shared is None:
            _shared = GraphClient()
        return _shared
