import pytest
import os
import tempfile
import graphviz

from agentir.ir.node import StartNode, EndNode, LLMNode, ToolNode, ConditionNode
from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph
from agentir.visualizer.graphviz import GraphvizVisualizer


def _build_test_graph() -> WorkflowGraph:
    """Helper to construct a standard styled graph for visualizer tests."""
    graph = WorkflowGraph()
    start = StartNode(id="start", name="Start")
    llm = LLMNode(id="llm", name="LLM Node", model="gpt-4", prompt_template="Prompt")
    cond = ConditionNode(id="cond", name="Router", condition_expr="check")
    tool = ToolNode(id="tool", name="Search Tool", tool_name="google")
    end = EndNode(id="end", name="End")

    for n in [start, llm, cond, tool, end]:
        graph.add_node(n)

    graph.add_edge(Edge(source="start", target="llm"))
    graph.add_edge(Edge(source="llm", target="cond"))
    graph.add_edge(Edge(source="cond", target="tool", source_port="yes"))
    graph.add_edge(Edge(source="cond", target="end", source_port="no"))
    graph.add_edge(Edge(source="tool", target="end"))

    return graph


def test_visualizer_to_dot():
    """Verify raw DOT generation outputs correctly styled properties."""
    graph = _build_test_graph()
    visualizer = GraphvizVisualizer(graph)
    dot_str = visualizer.to_dot()

    # Verify nodes are formatted in DOT syntax
    assert "start" in dot_str
    assert "llm" in dot_str
    assert "cond" in dot_str
    assert "tool" in dot_str
    assert "end" in dot_str

    # Verify custom styles and labels are output
    assert "doublecircle" not in dot_str  # verifying custom box shapes
    assert "diamond" in dot_str           # condition node
    assert "yes" in dot_str               # port labels
    assert "no" in dot_str


def test_visualizer_to_mermaid():
    """Verify Mermaid.js syntax generator outputs properly formatted flowchart rules."""
    graph = _build_test_graph()
    visualizer = GraphvizVisualizer(graph)
    mermaid_str = visualizer.to_mermaid()

    # Flowchart rules
    assert "graph TD" in mermaid_str
    assert 'start(["Start"])' in mermaid_str or 'start(["Start Node"])' in mermaid_str
    assert 'cond{"Router"}' in mermaid_str
    assert 'llm["LLM Node"]' in mermaid_str

    # Edge lines with ports
    assert 'cond -->|"yes"| tool' in mermaid_str
    assert 'cond -->|"no"| end' in mermaid_str

    # CSS styles
    assert "style start fill:#e2e8f0" in mermaid_str
    assert "style llm fill:#f3e8ff" in mermaid_str
    assert "style cond fill:#fef3c7" in mermaid_str


def test_visualizer_render_write():
    """Verify that render calls correctly compile the DOT source."""
    graph = _build_test_graph()
    visualizer = GraphvizVisualizer(graph)

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = os.path.join(tmp_dir, "test_workflow")
        
        try:
            # Attempt to render the graph (writes the .dot and calls dot compiler)
            rendered = visualizer.render(output_path, format="png")
            # If system 'dot' binary is installed, check if file exists
            assert os.path.exists(rendered)
        except (graphviz.backend.ExecutableNotFound, FileNotFoundError):
            # If the system 'dot' binary is not installed, it writes the DOT source file
            # and then raises ExecutableNotFound. We check that the source file is created.
            dot_src_file = f"{output_path}"
            assert os.path.exists(dot_src_file) or os.path.exists(f"{output_path}.gv")
