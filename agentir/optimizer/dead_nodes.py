"""
Dead Node Elimination (DCE) pass for AgentIR.
Removes unreachable nodes and nodes whose outputs are never consumed downstream.
"""

import networkx as nx
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType
from agentir.ir.edge import Edge


class DeadNodesOptimizer:
    """Removes unused and unreachable nodes from a WorkflowGraph."""

    def optimize(self, graph: WorkflowGraph) -> WorkflowGraph:
        """
        Optimize the graph by removing:
        1. Nodes that are unreachable from any StartNode.
        2. Nodes (except Start/End) whose produced outputs are never consumed by any active downstream node.
        Runs iteratively until no more nodes are removed.
        """
        # Create a copy of the graph to avoid mutating the input
        opt_graph = WorkflowGraph(
            nodes=graph.nodes.copy(),
            edges=graph.edges.copy()
        )

        changed = True
        while changed:
            changed = False
            nx_graph = opt_graph.to_networkx()

            # 1. Unreachable node elimination
            start_nodes = [
                nid for nid, node in opt_graph.nodes.items()
                if getattr(node, "type", None) == NodeType.START
            ]
            if start_nodes:
                unreachable = []
                for node_id in list(opt_graph.nodes.keys()):
                    reachable = False
                    for start in start_nodes:
                        if start == node_id or nx.has_path(nx_graph, start, node_id):
                            reachable = True
                            break
                    if not reachable:
                        unreachable.append(node_id)
                
                if unreachable:
                    for node_id in unreachable:
                        opt_graph.remove_node(node_id)
                    changed = True
                    continue

            # Update NetworkX graph after potential reachability removals
            nx_graph = opt_graph.to_networkx()

            # 2. Unused output elimination (DCE)
            dead_nodes = []
            for node_id, node in opt_graph.nodes.items():
                # Skip Start and End nodes, they are structural boundaries
                if getattr(node, "type", None) in (NodeType.START, NodeType.END):
                    continue

                # If the node has outputs, check if they are consumed downstream
                if node.outputs:
                    descendants = nx.descendants(nx_graph, node_id)
                    consumed = False
                    for desc_id in descendants:
                        desc_node = opt_graph.nodes.get(desc_id)
                        if desc_node and desc_node.inputs:
                            # Check if any input of downstream node consumes our output
                            if any(out_var in desc_node.inputs for out_var in node.outputs):
                                consumed = True
                                break
                    if not consumed:
                        dead_nodes.append(node_id)

            if dead_nodes:
                # Eliminate one dead node at a time and rebuild graph to prevent stale queries
                node_id = dead_nodes[0]
                predecessors = list(nx_graph.predecessors(node_id))
                successors = list(nx_graph.successors(node_id))
                for pred in predecessors:
                    for succ in successors:
                        if pred != succ:
                            try:
                                opt_graph.add_edge(Edge(source=pred, target=succ))
                            except ValueError:
                                pass
                opt_graph.remove_node(node_id)
                changed = True

        return opt_graph
