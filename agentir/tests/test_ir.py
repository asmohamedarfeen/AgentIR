import pytest
from pydantic import ValidationError, TypeAdapter

from agentir.ir.node import (
    NodeType,
    StartNode,
    EndNode,
    LLMNode,
    ToolNode,
    ConditionNode,
    AnyNode,
)
from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph


def test_node_deserialization():
    """Verify that polymorphic deserialization of nodes works correctly."""
    # StartNode
    start_data = {
        "id": "start_1",
        "type": "start",
        "name": "Start Node",
    }
    adapter = TypeAdapter(AnyNode)
    node = adapter.validate_python(start_data)
    assert isinstance(node, StartNode)
    assert node.type == NodeType.START

    # LLMNode
    llm_data = {
        "id": "llm_1",
        "type": "llm",
        "name": "Summarizer",
        "model": "gpt-4",
        "prompt_template": "Summarize: {text}",
        "temperature": 0.2,
    }
    node = adapter.validate_python(llm_data)
    assert isinstance(node, LLMNode)
    assert node.model == "gpt-4"
    assert node.temperature == 0.2

    # ToolNode
    tool_data = {
        "id": "tool_1",
        "type": "tool",
        "name": "Google Search",
        "tool_name": "google_search",
        "args": {"query": "test"},
    }
    node = adapter.validate_python(tool_data)
    assert isinstance(node, ToolNode)
    assert node.tool_name == "google_search"
    assert node.args["query"] == "test"

    # Invalid node type should fail validation
    invalid_data = {
        "id": "invalid_1",
        "type": "unknown",
        "name": "Unknown Node",
    }
    with pytest.raises(ValidationError):
        adapter.validate_python(invalid_data)


def test_edge_equality_and_hash():
    """Test Edge comparison and hashing logic."""
    edge1 = Edge(source="a", target="b", source_port="yes")
    edge2 = Edge(source="a", target="b", source_port="yes")
    edge3 = Edge(source="a", target="b", source_port="no")

    assert edge1 == edge2
    assert edge1 != edge3
    assert hash(edge1) == hash(edge2)
    assert hash(edge1) != hash(edge3)


def test_workflow_graph_operations():
    """Verify nodes and edges can be managed in WorkflowGraph."""
    graph = WorkflowGraph()

    start = StartNode(id="start", name="Start")
    tool = ToolNode(id="search", name="Search", tool_name="search_tool")
    end = EndNode(id="end", name="End")

    # Add nodes
    graph.add_node(start)
    graph.add_node(tool)
    graph.add_node(end)

    assert "start" in graph.nodes
    assert "search" in graph.nodes
    assert "end" in graph.nodes

    # Add edges
    edge1 = Edge(source="start", target="search")
    edge2 = Edge(source="search", target="end")

    graph.add_edge(edge1)
    graph.add_edge(edge2)

    assert len(graph.edges) == 2
    assert graph.get_successors("start") == ["search"]
    assert graph.get_predecessors("end") == ["search"]

    # Trying to add edge to missing node should raise error
    with pytest.raises(ValueError):
        graph.add_edge(Edge(source="start", target="missing_node"))

    # Remove node and check cleanup of associated edges
    graph.remove_node("search")
    assert "search" not in graph.nodes
    assert len(graph.edges) == 0  # Edges referencing 'search' should be removed


def test_graph_validation():
    """Verify structural validation checks."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    graph.add_node(start)

    # Edge referencing a non-existent target node
    edge = Edge(source="start", target="dangling_node")
    graph.edges.append(edge)  # Bypass add_edge validation to simulate direct addition/load

    errors = graph.validate_graph()
    assert len(errors) == 1
    assert "dangling_node" in errors[0]


def test_networkx_conversion():
    """Test export and import compatibility with NetworkX."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    llm = LLMNode(id="llm", name="LLM", model="gpt-4", prompt_template="Prompt")
    
    graph.add_node(start)
    graph.add_node(llm)
    graph.add_edge(Edge(source="start", target="llm", source_port="out"))

    # Convert to NetworkX
    nx_graph = graph.to_networkx()
    assert nx_graph.has_node("start")
    assert nx_graph.has_node("llm")
    assert nx_graph.has_edge("start", "llm")
    assert nx_graph.edges["start", "llm"]["source_port"] == "out"

    # Convert back to WorkflowGraph
    reconstructed = WorkflowGraph.from_networkx(nx_graph)
    assert "start" in reconstructed.nodes
    assert "llm" in reconstructed.nodes
    assert len(reconstructed.edges) == 1
    assert reconstructed.edges[0].source == "start"
    assert reconstructed.edges[0].target == "llm"
    assert reconstructed.edges[0].source_port == "out"
