"""
Duplicate Tool Elimination pass for AgentIR.
Identifies identical tool calls (same tool and arguments) and merges them,
rewriting downstream data-flow variables and edges.
"""

import json
from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class DuplicateToolsOptimizer:
    """Merges duplicate tool invocations with identical arguments."""

    def optimize(self, graph: WorkflowGraph) -> WorkflowGraph:
        """
        Scan the graph for ToolNodes that share the same tool_name and static arguments.
        Merge duplicates into a single canonical node, mapping outputs and rewriting downstream inputs.
        """
        # Create a deep copy of the nodes and edges
        opt_graph = WorkflowGraph(
            nodes={nid: node.model_copy(deep=True) for nid, node in graph.nodes.items()},
            edges=[edge.model_copy(deep=True) for edge in graph.edges]
        )

        def serialize_args(args) -> str:
            return json.dumps(args, sort_keys=True)

        # Group ToolNode IDs by (tool_name, args_json)
        groups = {}
        for node_id, node in opt_graph.nodes.items():
            if getattr(node, "type", None) == NodeType.TOOL:
                key = (node.tool_name, serialize_args(node.args))
                groups.setdefault(key, []).append(node_id)

        for (tool_name, args_json), node_ids in groups.items():
            if len(node_ids) <= 1:
                continue

            # Deterministically sort IDs and pick the first one as canonical
            sorted_ids = sorted(node_ids)
            canonical_id = sorted_ids[0]
            canonical_node = opt_graph.nodes[canonical_id]

            for dup_id in sorted_ids[1:]:
                dup_node = opt_graph.nodes[dup_id]

                # Create output variable mapping (position-based)
                output_map = {}
                for i, dup_out in enumerate(dup_node.outputs):
                    if i < len(canonical_node.outputs):
                        output_map[dup_out] = canonical_node.outputs[i]

                # Update downstream node inputs with the mapped canonical variables
                for other_node in opt_graph.nodes.values():
                    if other_node.inputs:
                        other_node.inputs = [
                            output_map.get(inp, inp) for inp in other_node.inputs
                        ]

                # Redirect edges of duplicate node to target the canonical node
                new_edges = []
                for edge in opt_graph.edges:
                    src = edge.source
                    tgt = edge.target

                    if src == dup_id:
                        src = canonical_id
                    if tgt == dup_id:
                        tgt = canonical_id

                    # Avoid creating self-loops
                    if src != tgt:
                        new_edge = Edge(
                            source=src,
                            target=tgt,
                            source_port=edge.source_port,
                            target_port=edge.target_port,
                            condition=edge.condition,
                            metadata=edge.metadata.copy()
                        )
                        if new_edge not in new_edges:
                            new_edges.append(new_edge)

                opt_graph.edges = new_edges
                # Remove duplicate node from graph definitions
                if dup_id in opt_graph.nodes:
                    del opt_graph.nodes[dup_id]

        return opt_graph
