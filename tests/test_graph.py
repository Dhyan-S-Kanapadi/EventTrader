from eventtrader.orchestration.graph import build_status_graph


def test_graph_runs_only_deterministic_health_node():
    graph = build_status_graph()
    assert list(graph.stream({}, stream_mode="updates")) == [
        {
            "health_status": {
                "status": "ok",
                "trading_mode": "PAPER",
                "live_trading_enabled": False,
            },
        }
    ]
    assert (
        graph.invoke({})
        == graph.invoke({})
        == {
            "status": "ok",
            "trading_mode": "PAPER",
            "live_trading_enabled": False,
        }
    )
    assert {(edge.source, edge.target) for edge in graph.get_graph().edges} == {
        ("__start__", "health_status"),
        ("health_status", "__end__"),
    }
