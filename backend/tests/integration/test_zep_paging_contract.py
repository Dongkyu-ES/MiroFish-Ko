from __future__ import annotations

import types

from backend.app.utils.zep_paging import fetch_all_nodes


def test_fetch_all_nodes_returns_full_graph_without_default_truncation():
    def make_node(index: int):
        return types.SimpleNamespace(uuid_=f"node-{index:04d}")

    pages = [
        [make_node(index) for index in range(start, start + 100)]
        for start in range(0, 2500, 100)
    ]

    class NodeNamespace:
        def __init__(self):
            self.calls: list[str | None] = []

        def get_by_graph_id(self, graph_id: str, limit: int = 100, uuid_cursor: str | None = None):
            self.calls.append(uuid_cursor)
            page_index = len(self.calls) - 1
            if page_index >= len(pages):
                return []
            return pages[page_index]

    node_namespace = NodeNamespace()
    client = types.SimpleNamespace(graph=types.SimpleNamespace(node=node_namespace))

    nodes = fetch_all_nodes(client, "graph-01", page_size=100)

    assert len(nodes) == 2500
    assert node_namespace.calls[0] is None
    assert node_namespace.calls[-1] == "node-2499"
