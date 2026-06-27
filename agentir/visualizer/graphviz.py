"""
Visualizer framework for AgentIR.
Provides Graphviz DOT script generation, diagram rendering, and Mermaid.js diagram generation.
"""

from typing import Any
import graphviz

from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class GraphvizVisualizer:
    """Exports and renders WorkflowGraphs using Graphviz and Mermaid.js styling rules."""

    def __init__(self, graph: WorkflowGraph) -> None:
        self.graph = graph

    def to_dot(self) -> str:
        """Generate the raw DOT syntax representation of the graph."""
        dot = graphviz.Digraph(comment="AgentIR Workflow")
        self._populate_digraph(dot)
        return dot.source

    def render(self, output_path: str, format: str = "png") -> str:
        """
        Render the graph to a file and return the output path.
        Saves clean compiled images/files (removes raw temporary dot files).
        """
        dot = graphviz.Digraph(comment="AgentIR Workflow", format=format)
        self._populate_digraph(dot)
        # Render and cleanup source file
        rendered_path = dot.render(output_path, cleanup=True)
        return rendered_path

    def to_mermaid(self) -> str:
        """Generate the Mermaid.js flowchart syntax representation of the graph."""
        lines = ["graph TD"]

        # 1. Define nodes with custom shapes
        for node_id, node in self.graph.nodes.items():
            name = node.name
            if node.type == NodeType.START:
                lines.append(f'    {node_id}(["{name}"])')
            elif node.type == NodeType.END:
                lines.append(f'    {node_id}(["{name}"])')
            elif node.type == NodeType.CONDITION:
                lines.append(f'    {node_id}{{"{name}"}}')
            else:
                lines.append(f'    {node_id}["{name}"]')

        # 2. Define edges
        for edge in self.graph.edges:
            label = edge.source_port or ""
            if edge.condition:
                label += f" ({edge.condition})"
            label = label.strip()

            if label:
                lines.append(f'    {edge.source} -->|"{label}"| {edge.target}')
            else:
                lines.append(f'    {edge.source} --> {edge.target}')

        # 3. Apply CSS styles matching the modern design palette
        for node_id, node in self.graph.nodes.items():
            if node.type == NodeType.START:
                lines.append(f"    style {node_id} fill:#e2e8f0,stroke:#64748b,stroke-width:2px")
            elif node.type == NodeType.END:
                lines.append(f"    style {node_id} fill:#cbd5e1,stroke:#475569,stroke-width:2px")
            elif node.type == NodeType.LLM:
                lines.append(f"    style {node_id} fill:#f3e8ff,stroke:#7e22ce,stroke-width:2px")
            elif node.type == NodeType.TOOL:
                lines.append(f"    style {node_id} fill:#ccfbf1,stroke:#0f766e,stroke-width:2px")
            elif node.type == NodeType.CONDITION:
                lines.append(f"    style {node_id} fill:#fef3c7,stroke:#d97706,stroke-width:2px")
            else:
                lines.append(f"    style {node_id} fill:#f1f5f9,stroke:#94a3b8,stroke-width:2px")

        return "\n".join(lines)

    def _populate_digraph(self, dot: graphviz.Digraph) -> None:
        """Populate a graphviz Digraph instance with styled nodes and edges from the workflow."""
        dot.attr(rankdir="TB", size="8,5")
        dot.attr("node", fontname="Arial", fontsize="10", penwidth="1.5")
        dot.attr("edge", fontname="Arial", fontsize="9", color="#404040", arrowhead="vee")

        for node_id, node in self.graph.nodes.items():
            if node.type == NodeType.START:
                dot.node(
                    node_id,
                    label=node.name,
                    shape="box",
                    style="filled,rounded",
                    fillcolor="#e2e8f0",
                    color="#64748b"
                )
            elif node.type == NodeType.END:
                dot.node(
                    node_id,
                    label=node.name,
                    shape="box",
                    style="filled,rounded",
                    fillcolor="#cbd5e1",
                    color="#475569"
                )
            elif node.type == NodeType.LLM:
                lbl = f"{node.name}\n[LLM: {getattr(node, 'model', 'LLM')}]"
                dot.node(
                    node_id,
                    label=lbl,
                    shape="box",
                    style="filled,rounded",
                    fillcolor="#f3e8ff",
                    color="#7e22ce"
                )
            elif node.type == NodeType.TOOL:
                lbl = f"{node.name}\n[Tool: {getattr(node, 'tool_name', 'tool')}]"
                dot.node(
                    node_id,
                    label=lbl,
                    shape="box",
                    style="filled,rounded",
                    fillcolor="#ccfbf1",
                    color="#0f766e"
                )
            elif node.type == NodeType.CONDITION:
                lbl = f"{node.name}\n<{node.condition_expr}>"
                dot.node(
                    node_id,
                    label=lbl,
                    shape="diamond",
                    style="filled",
                    fillcolor="#fef3c7",
                    color="#d97706"
                )
            else:
                dot.node(
                    node_id,
                    label=node.name,
                    shape="box",
                    style="filled,rounded",
                    fillcolor="#f1f5f9",
                    color="#94a3b8"
                )

        for edge in self.graph.edges:
            label = edge.source_port or ""
            if edge.condition:
                label += f"\n({edge.condition})"
            dot.edge(edge.source, edge.target, label=label.strip())
