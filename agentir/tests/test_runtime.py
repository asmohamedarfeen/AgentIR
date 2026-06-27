import pytest
import asyncio
from typing import Dict, Any

from agentir.ir.node import StartNode, EndNode, LLMNode, ToolNode, ConditionNode
from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph
from agentir.runtime.scheduler import WorkflowScheduler
from agentir.runtime.executor import WorkflowExecutor


def test_scheduler_stage_planning():
    """Verify that WorkflowScheduler groups concurrent stages correctly."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    t1 = ToolNode(id="t1", name="Tool 1", tool_name="t1")
    t2 = ToolNode(id="t2", name="Tool 2", tool_name="t2")
    end = EndNode(id="end", name="End")

    for n in [start, t1, t2, end]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="t1"))
    graph.add_edge(Edge(source="start", target="t2"))
    graph.add_edge(Edge(source="t1", target="end"))
    graph.add_edge(Edge(source="t2", target="end"))

    scheduler = WorkflowScheduler()
    plan = scheduler.create_plan(graph)

    assert len(plan.stages) == 3
    assert plan.stages[0].node_ids == ["start"]
    assert set(plan.stages[1].node_ids) == {"t1", "t2"}
    assert plan.stages[2].node_ids == ["end"]


@pytest.mark.asyncio
async def test_executor_sequential_flow():
    """Verify that WorkflowExecutor runs sequential nodes and merges state changes."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    n1 = ToolNode(id="n1", name="N1", tool_name="t1")
    n2 = ToolNode(id="n2", name="N2", tool_name="t2")
    end = EndNode(id="end", name="End")

    for n in [start, n1, n2, end]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="n1"))
    graph.add_edge(Edge(source="n1", target="n2"))
    graph.add_edge(Edge(source="n2", target="end"))

    # Register callbacks
    async def run_n1(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"x": state.get("input", 0) + 10}

    async def run_n2(state: Dict[str, Any]) -> Dict[str, Any]:
        return {"y": state.get("x", 0) * 2}

    registry = {
        "n1": run_n1,
        "n2": run_n2
    }

    executor = WorkflowExecutor(graph, registry)
    final_state = await executor.execute({"input": 5})

    assert final_state["x"] == 15
    assert final_state["y"] == 30


@pytest.mark.asyncio
async def test_executor_parallel_flow():
    """Verify that independent branches are executed concurrently in parallel."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    n1 = ToolNode(id="n1", name="N1", tool_name="t1")
    n2 = ToolNode(id="n2", name="N2", tool_name="t2")
    end = EndNode(id="end", name="End")

    for n in [start, n1, n2, end]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="n1"))
    graph.add_edge(Edge(source="start", target="n2"))
    graph.add_edge(Edge(source="n1", target="end"))
    graph.add_edge(Edge(source="n2", target="end"))

    # Tracks if execution overlapped (concurrency check)
    running_count = 0
    max_concurrency = 0

    async def run_n1(state: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal running_count, max_concurrency
        running_count += 1
        max_concurrency = max(max_concurrency, running_count)
        await asyncio.sleep(0.05)
        running_count -= 1
        return {"a": 1}

    async def run_n2(state: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal running_count, max_concurrency
        running_count += 1
        max_concurrency = max(max_concurrency, running_count)
        await asyncio.sleep(0.05)
        running_count -= 1
        return {"b": 2}

    registry = {
        "n1": run_n1,
        "n2": run_n2
    }

    executor = WorkflowExecutor(graph, registry)
    final_state = await executor.execute({})

    # Verify both outputs were merged
    assert final_state.get("a") == 1
    assert final_state.get("b") == 2
    # Verify they ran concurrently (max_concurrency should be 2)
    assert max_concurrency == 2


@pytest.mark.asyncio
async def test_executor_conditional_loop():
    """Verify that conditional routing cycles are resolved dynamically."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    counter = ToolNode(id="counter", name="Counter", tool_name="counter")
    router = ConditionNode(id="router", name="Router", condition_expr="route_val", branches={"loop": "counter", "exit": "end"})
    end = EndNode(id="end", name="End")

    for n in [start, counter, router, end]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="counter"))
    graph.add_edge(Edge(source="counter", target="router"))
    graph.add_edge(Edge(source="router", target="counter", source_port="loop"))
    graph.add_edge(Edge(source="router", target="end", source_port="exit"))

    async def run_counter(state: Dict[str, Any]) -> Dict[str, Any]:
        current = state.get("count", 0)
        return {"count": current + 1}

    async def run_router(state: Dict[str, Any]) -> Dict[str, Any]:
        count = state.get("count", 0)
        branch = "loop" if count < 3 else "exit"
        return {"branch": branch}

    registry = {
        "counter": run_counter,
        "router": run_router
    }

    executor = WorkflowExecutor(graph, registry)
    final_state = await executor.execute({"count": 0})

    assert final_state["count"] == 3


@pytest.mark.asyncio
async def test_executor_error_retry():
    """Verify node exception retries and backoff logic."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    tool = ToolNode(id="tool", name="Flaky Tool", tool_name="flaky")
    end = EndNode(id="end", name="End")

    # Configure metadata to retry up to 2 times
    tool.metadata["retry_count"] = 2
    tool.metadata["retry_delay"] = 0.01

    for n in [start, tool, end]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="tool"))
    graph.add_edge(Edge(source="tool", target="end"))

    attempts = 0

    async def run_flaky(state: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("Failure simulation")
        return {"success": True}

    registry = {
        "tool": run_flaky
    }

    # 1. Test successful run with retries
    executor = WorkflowExecutor(graph, registry)
    final_state = await executor.execute({})
    assert final_state["success"] is True
    assert attempts == 3

    # 2. Test failure run when retry limits are exceeded
    attempts = 0
    tool.metadata["retry_count"] = 1  # only allow 1 retry (2 attempts total)
    with pytest.raises(ValueError):
        await executor.execute({})
