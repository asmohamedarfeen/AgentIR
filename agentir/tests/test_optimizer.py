import pytest

from agentir.ir.node import StartNode, EndNode, LLMNode, ToolNode
from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph

from agentir.optimizer.dead_nodes import DeadNodesOptimizer
from agentir.optimizer.duplicate_tools import DuplicateToolsOptimizer
from agentir.optimizer.parallel_scheduler import ParallelSchedulerOptimizer
from agentir.optimizer.cache_optimizer import CacheOptimizer
from agentir.optimizer.cost_estimator import CostEstimator


def test_dead_nodes_optimizer():
    """Verify dead nodes optimizer removes unreachable and unused nodes."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    active_tool = ToolNode(
        id="active_tool", name="Search", tool_name="search", outputs=["query_res"]
    )
    llm = LLMNode(
        id="llm", name="LLM", model="gpt-4", prompt_template="Prompt",
        inputs=["query_res"], outputs=["answer"]
    )
    unused_tool = ToolNode(
        id="unused_tool", name="Weather", tool_name="weather", outputs=["weather_res"]
    )
    orphan = ToolNode(
        id="orphan", name="Orphan", tool_name="search"
    )
    end = EndNode(id="end", name="End", inputs=["answer"])

    for n in [start, active_tool, llm, unused_tool, orphan, end]:
        graph.add_node(n)

    # start -> active_tool -> llm -> end
    # start -> unused_tool (outputs never read by any downstream node)
    # orphan has no edges (unreachable)
    graph.add_edge(Edge(source="start", target="active_tool"))
    graph.add_edge(Edge(source="active_tool", target="llm"))
    graph.add_edge(Edge(source="llm", target="end"))
    graph.add_edge(Edge(source="start", target="unused_tool"))

    optimizer = DeadNodesOptimizer()
    optimized = optimizer.optimize(graph)

    # Active path preserved
    assert "start" in optimized.nodes
    assert "active_tool" in optimized.nodes
    assert "llm" in optimized.nodes
    assert "end" in optimized.nodes

    # Dead nodes eliminated
    assert "orphan" not in optimized.nodes
    assert "unused_tool" not in optimized.nodes


def test_duplicate_tools_optimizer():
    """Verify that duplicate tools optimizer merges identical tool calls."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    tool1 = ToolNode(
        id="t1", name="Google 1", tool_name="google", args={"query": "test"}, outputs=["res1"]
    )
    tool2 = ToolNode(
        id="t2", name="Google 2", tool_name="google", args={"query": "test"}, outputs=["res2"]
    )
    llm = LLMNode(
        id="llm", name="LLM", model="gpt-4", prompt_template="...", inputs=["res2"], outputs=["ans"]
    )
    end = EndNode(id="end", name="End", inputs=["ans"])

    for n in [start, tool1, tool2, llm, end]:
        graph.add_node(n)

    # start -> t1 -> t2 -> llm -> end
    graph.add_edge(Edge(source="start", target="t1"))
    graph.add_edge(Edge(source="t1", target="t2"))
    graph.add_edge(Edge(source="t2", target="llm"))
    graph.add_edge(Edge(source="llm", target="end"))

    optimizer = DuplicateToolsOptimizer()
    optimized = optimizer.optimize(graph)

    # Duplicate t2 should be merged into t1
    assert "t1" in optimized.nodes
    assert "t2" not in optimized.nodes

    # Downstream inputs should be rewritten (llm now takes res1 instead of res2)
    llm_node = optimized.nodes["llm"]
    assert "res1" in llm_node.inputs
    assert "res2" not in llm_node.inputs

    # Edges should connect start -> t1 -> llm
    successors_start = {edge.target for edge in optimized.edges if edge.source == "start"}
    successors_t1 = {edge.target for edge in optimized.edges if edge.source == "t1"}
    
    assert successors_start == {"t1"}
    assert successors_t1 == {"llm"}


def test_parallel_scheduler_optimizer():
    """Verify parallel scheduler optimizer reschedules independent sequential steps."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    llm1 = LLMNode(
        id="llm1", name="LLM 1", model="gpt-4", prompt_template="...", outputs=["res1"]
    )
    llm2 = LLMNode(
        id="llm2", name="LLM 2", model="gpt-4", prompt_template="...", outputs=["res2"]
    )
    end = EndNode(id="end", name="End", inputs=["res1", "res2"])

    for n in [start, llm1, llm2, end]:
        graph.add_node(n)

    # Setup sequential chain control flow: start -> llm1 -> llm2 -> end
    # Note: llm2 has no data dependency on llm1 (its inputs are empty)
    graph.add_edge(Edge(source="start", target="llm1"))
    graph.add_edge(Edge(source="llm1", target="llm2"))
    graph.add_edge(Edge(source="llm2", target="end"))

    optimizer = ParallelSchedulerOptimizer()
    optimized = optimizer.optimize(graph)

    # Edge llm1 -> llm2 should be bypassed/removed
    edge_u_v = [e for e in optimized.edges if e.source == "llm1" and e.target == "llm2"]
    assert len(edge_u_v) == 0

    # New layout: start -> llm1 -> end AND start -> llm2 -> end
    successors_start = {e.target for e in optimized.edges if e.source == "start"}
    successors_llm1 = {e.target for e in optimized.edges if e.source == "llm1"}
    successors_llm2 = {e.target for e in optimized.edges if e.source == "llm2"}

    assert successors_start == {"llm1", "llm2"}
    assert successors_llm1 == {"end"}
    assert successors_llm2 == {"end"}


def test_cache_optimizer():
    """Verify cache optimizer populates metadata flags and hash-based keys."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    llm = LLMNode(id="llm", name="LLM", model="gpt-4", prompt_template="Prompt")
    tool = ToolNode(id="tool", name="Search", tool_name="google", args={"q": "weather"})
    end = EndNode(id="end", name="End")

    for n in [start, llm, tool, end]:
        graph.add_node(n)

    optimizer = CacheOptimizer()
    optimized = optimizer.optimize(graph)

    # Cache attributes should be set in node metadata
    assert optimized.nodes["llm"].metadata["cache_enabled"] is True
    assert "cache_key" in optimized.nodes["llm"].metadata

    assert optimized.nodes["tool"].metadata["cache_enabled"] is True
    assert "cache_key" in optimized.nodes["tool"].metadata


def test_cost_estimator():
    """Verify serial vs parallel (critical path) cost estimation calculations."""
    # Scenario 1: Sequential Path
    # Start -> LLM1 (1.5s) -> LLM2 (1.5s) -> End
    graph_seq = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    llm1 = LLMNode(id="llm1", name="L1", model="gpt-4", prompt_template="...")
    llm2 = LLMNode(id="llm2", name="L2", model="gpt-4", prompt_template="...")
    end = EndNode(id="end", name="End")

    for n in [start, llm1, llm2, end]:
        graph_seq.add_node(n)

    graph_seq.add_edge(Edge(source="start", target="llm1"))
    graph_seq.add_edge(Edge(source="llm1", target="llm2"))
    graph_seq.add_edge(Edge(source="llm2", target="end"))

    estimator = CostEstimator()
    report_seq = estimator.estimate(graph_seq)
    
    assert report_seq.llm_calls_count == 2
    assert report_seq.estimated_cost_usd == 0.03  # 0.015 * 2
    assert report_seq.serial_latency_seconds == 3.0  # 1.5 + 1.5
    assert report_seq.critical_path_latency_seconds == 3.0  # Sequential longest path is 3.0

    # Scenario 2: Parallel Path
    # Start -> LLM1 -> End
    # Start -> LLM2 -> End
    graph_par = WorkflowGraph()
    for n in [start, llm1, llm2, end]:
        graph_par.add_node(n)

    graph_par.add_edge(Edge(source="start", target="llm1"))
    graph_par.add_edge(Edge(source="start", target="llm2"))
    graph_par.add_edge(Edge(source="llm1", target="end"))
    graph_par.add_edge(Edge(source="llm2", target="end"))

    report_par = estimator.estimate(graph_par)
    assert report_par.serial_latency_seconds == 3.0  # sum of runtimes is still 3.0s
    assert report_par.critical_path_latency_seconds == 1.5  # Parallel execution of both drops to 1.5s


def test_token_optimizer():
    """Verify that TokenOptimizer correctly applies token reduction and caching annotations."""
    from agentir.optimizer.token_optimizer import TokenOptimizer
    
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    router = LLMNode(
        id="router", name="Router Agent", model="gpt-4", prompt_template="Route...",
        inputs=["query"], outputs=["route_decision"]
    )
    researcher = LLMNode(
        id="researcher", name="Research Agent", model="gpt-4", prompt_template="Summarize...",
        inputs=["document_text"], outputs=["notes"],
        system_instruction="Same prompt instruction"
    )
    coder = LLMNode(
        id="coder", name="Coder Agent", model="gpt-4", prompt_template="Write code...",
        inputs=["query"], outputs=["code"],
        system_instruction="Same prompt instruction"
    )
    end = EndNode(id="end", name="End")

    for n in [start, router, researcher, coder, end]:
        graph.add_node(n)

    optimizer = TokenOptimizer()
    optimized = optimizer.optimize(graph)

    # 1. Classification cap applied (router capped to 64 output tokens)
    assert optimized.nodes["router"].metadata["max_output_tokens"] == 64

    # 2. Input truncation limit applied (researcher consumes large document_text)
    assert optimized.nodes["researcher"].metadata["input_truncation_limit"] == 1500

    # 3. Context caching enabled (researcher and coder share identical system instruction)
    assert optimized.nodes["researcher"].metadata["context_cache_enabled"] is True
    assert optimized.nodes["coder"].metadata["context_cache_enabled"] is True
