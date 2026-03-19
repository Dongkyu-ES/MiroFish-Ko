import pytest

from backend.shims.local_zep.zep_cloud import InternalServerError
from backend.shims.local_zep.zep_cloud._adapter import LocalGraphAdapter


def test_local_graph_adapter_raises_explicit_unavailable_error():
    adapter = LocalGraphAdapter(base_url="http://127.0.0.1:1", timeout_seconds=1)

    with pytest.raises(InternalServerError, match="Parity engine is unavailable"):
        adapter.create_graph(graph_id="graph_01", name="name", description="desc")
