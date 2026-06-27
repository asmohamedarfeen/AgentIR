import pytest

from agentir.ir.node import StartNode, EndNode, LLMNode, ToolNode, ConditionNode
from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph
from agentir.analyzer.dependency import DependencyAnalyzer
from agentir.analyzer.validator import WorkflowValidator


def test_dependency_analyzer_dag():
    """Verify roots, ancestors, descendants, and scheduling layers in a DAG."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    tool1 = ToolNode(id="t1", name="Tool 1", tool_name="t1")
    tool2 = ToolNode(id="t2", name="Tool 2", tool_name="t2")
    llm = LLMNode(id="llm", name="LLM", model="gpt-4", prompt_template="...")
    end = EndNode(id="end", name="End")

    for n in [start, tool1, tool2, llm, end]:
        graph.add_node(n)

    # start -> t1 -> llm -> end
    # start -> t2 -> llm
    graph.add_edge(Edge(source="start", target="t1"))
    graph.add_edge(Edge(source="start", target="t2"))
    graph.add_edge(Edge(source="t1", target="llm"))
    graph.add_edge(Edge(source="t2", target="llm"))
    graph.add_edge(Edge(source="llm", target="end"))

    analyzer = DependencyAnalyzer(graph)

    assert analyzer.get_roots() == {"start"}
    assert analyzer.get_dependencies("llm") == {"start", "t1", "t2"}
    assert analyzer.get_dependents("start") == {"t1", "t2", "llm", "end"}
    assert analyzer.is_independent("t1", "t2")
    assert not analyzer.is_independent("start", "t1")

    # Execution layers:
    # Layer 0: start
    # Layer 1: t1, t2
    # Layer 2: llm
    # Layer 3: end
    layers = analyzer.get_execution_layers()
    assert layers[0] == ["start"]
    assert set(layers[1]) == {"t1", "t2"}
    assert layers[2] == ["llm"]
    assert layers[3] == ["end"]


def test_dependency_analyzer_with_loop():
    """Verify that cycles are successfully broken at ConditionNode boundaries during leveling."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    llm = LLMNode(id="llm", name="LLM", model="gpt-4", prompt_template="...")
    cond = ConditionNode(id="cond", name="Branch", condition_expr="x == 1")
    end = EndNode(id="end", name="End")

    for n in [start, llm, cond, end]:
        graph.add_node(n)

    # start -> llm -> cond -> end
    #                 cond -> llm (loop back)
    graph.add_edge(Edge(source="start", target="llm"))
    graph.add_edge(Edge(source="llm", target="cond"))
    graph.add_edge(Edge(source="cond", target="end", source_port="done"))
    graph.add_edge(Edge(source="cond", target="llm", source_port="retry"))

    analyzer = DependencyAnalyzer(graph)
    # Without loop breaking, nx.is_directed_acyclic_graph would raise an error.
    # The analyzer should successfully break it at `cond -> llm`.
    layers = analyzer.get_execution_layers()
    assert len(layers) > 0
    # Topological order should be start -> llm -> cond -> end
    assert layers[0] == ["start"]
    assert layers[1] == ["llm"]
    assert layers[2] == ["cond"]
    assert layers[3] == ["end"]


def test_validator_missing_boundaries():
    """Verify validation flags missing start/end nodes."""
    graph = WorkflowGraph()
    tool = ToolNode(id="t1", name="Tool 1", tool_name="t1")
    graph.add_node(tool)

    validator = WorkflowValidator(graph)
    issues = validator.validate()
    codes = {issue.code for issue in issues}
    assert "MISSING_START_NODE" in codes
    assert "MISSING_END_NODE" in codes


def test_validator_reachability():
    """Verify validation detects unreachable and dead-end nodes."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    end = EndNode(id="end", name="End")
    orphan = ToolNode(id="orphan", name="Orphan", tool_name="t")

    for n in [start, end, orphan]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="end"))

    validator = WorkflowValidator(graph)
    issues = validator.validate()
    codes = {issue.code for issue in issues}
    assert "UNREACHABLE_NODE" in codes
    assert "DEAD_END_NODE" in codes

    unreachable_node_ids = {issue.node_id for issue in issues if issue.code == "UNREACHABLE_NODE"}
    assert "orphan" in unreachable_node_ids


def test_validator_cycles():
    """Verify infinite loop detection vs valid conditional loops."""
    # 1. Infinite cycle (no ConditionNode)
    graph_inf = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    n1 = ToolNode(id="n1", name="N1", tool_name="t1")
    n2 = ToolNode(id="n2", name="N2", tool_name="t2")
    end = EndNode(id="end", name="End")

    for n in [start, n1, n2, end]:
        graph_inf.add_node(n)

    graph_inf.add_edge(Edge(source="start", target="n1"))
    graph_inf.add_edge(Edge(source="n1", target="n2"))
    graph_inf.add_edge(Edge(source="n2", target="n1"))  # Cycle
    graph_inf.add_edge(Edge(source="n2", target="end"))

    validator_inf = WorkflowValidator(graph_inf)
    issues_inf = validator_inf.validate()
    codes_inf = {issue.code for issue in issues_inf}
    assert "INFINITE_LOOP" in codes_inf

    # 2. Valid conditional cycle
    graph_valid = WorkflowGraph()
    start_v = StartNode(id="start_v", name="Start")
    n1_v = ToolNode(id="n1_v", name="N1", tool_name="t1")
    cond = ConditionNode(id="cond", name="Cond", condition_expr="retry")
    end_v = EndNode(id="end_v", name="End")

    for n in [start_v, n1_v, cond, end_v]:
        graph_valid.add_node(n)

    graph_valid.add_edge(Edge(source="start_v", target="n1_v"))
    graph_valid.add_edge(Edge(source="n1_v", target="cond"))
    graph_valid.add_edge(Edge(source="cond", target="n1_v", source_port="yes"))
    graph_valid.add_edge(Edge(source="cond", target="end_v", source_port="no"))

    validator_valid = WorkflowValidator(graph_valid)
    issues_valid = validator_valid.validate()
    codes_valid = {issue.code for issue in issues_valid}
    assert "INFINITE_LOOP" not in codes_valid


def test_validator_data_flow():
    """Verify validation detects missing input parameters."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start", outputs=["query"])
    llm = LLMNode(id="llm", name="LLM", model="gpt-4", prompt_template="Prompt", inputs=["query", "missing_var"], outputs=["result"])
    end = EndNode(id="end", name="End", inputs=["result"])

    for n in [start, llm, end]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="llm"))
    graph.add_edge(Edge(source="llm", target="end"))

    validator = WorkflowValidator(graph)
    issues = validator.validate()
    codes = {issue.code for issue in issues}
    assert "MISSING_INPUT" in codes

    missing_input_issues = [issue for issue in issues if issue.code == "MISSING_INPUT"]
    assert len(missing_input_issues) == 1
    assert missing_input_issues[0].node_id == "llm"
    assert "missing_var" in missing_input_issues[0].message
