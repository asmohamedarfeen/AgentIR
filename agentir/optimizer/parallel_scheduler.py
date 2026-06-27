"""
Parallel Scheduler Optimizer pass for AgentIR.
Identifies sequential execution control edges that have no actual data dependencies,
converting them into concurrent branches.
"""

from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class ParallelSchedulerOptimizer:
    """Decouples sequential control constraints when nodes are data-independent."""

    def optimize(self, graph: WorkflowGraph) -> WorkflowGraph:
        """
        Scan for sequential edges (U -> V) between computation nodes (LLM/Tool).
        If V does not consume any output variable produced by U, the sequential constraint
        is removed and rescheduled in parallel by connecting both to their respective
        common predecessors and successors.
        """
        opt_graph = WorkflowGraph(
            nodes={nid: node.model_copy(deep=True) for nid, node in graph.nodes.items()},
            edges=[edge.model_copy(deep=True) for edge in graph.edges]
        )

        nx_graph = opt_graph.to_networkx()

        # Identify candidate edges between computation nodes
        candidates = []
        for edge in opt_graph.edges:
            u = edge.source
            v = edge.target
            u_node = opt_graph.nodes.get(u)
            v_node = opt_graph.nodes.get(v)

            if u_node and v_node:
                # We target standard computation nodes (LLM and Tool)
                if (
                    u_node.type in (NodeType.LLM, NodeType.TOOL)
                    and v_node.type in (NodeType.LLM, NodeType.TOOL)
                ):
                    candidates.append((u, v, edge))

        for u, v, edge in candidates:
            u_node = opt_graph.nodes[u]
            v_node = opt_graph.nodes[v]

            # Determine if there's an active data dependency between U and V
            has_data_dep = any(out_var in v_node.inputs for out_var in u_node.outputs)

            if not has_data_dep:
                # Reschedule: remove U -> V control edge
                opt_graph.remove_edge(u, v, source_port=edge.source_port)

                # Connect U's predecessors to V (P -> V)
                predecessors = list(nx_graph.predecessors(u))
                for pred in predecessors:
                    try:
                        opt_graph.add_edge(Edge(source=pred, target=v))
                    except ValueError:
                        pass

                # Connect U to V's successors (U -> S)
                successors = list(nx_graph.successors(v))
                for succ in successors:
                    try:
                        opt_graph.add_edge(Edge(source=u, target=succ))
                    except ValueError:
                        pass

        return opt_graph
