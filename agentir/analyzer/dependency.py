"""
Dependency analysis for AgentIR workflows.
Traces node control dependencies and calculates parallel execution stages.
"""

from typing import List, Set
import networkx as nx

from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class DependencyAnalyzer:
    """Analyzes execution dependencies and concurrent stages in a WorkflowGraph."""

    def __init__(self, graph: WorkflowGraph) -> None:
        self.graph = graph
        self.nx_graph = graph.to_networkx()

    def get_roots(self) -> Set[str]:
        """Return all nodes that have no incoming dependencies (roots)."""
        return {node for node in self.nx_graph.nodes() if self.nx_graph.in_degree(node) == 0}

    def get_dependencies(self, node_id: str) -> Set[str]:
        """Return the set of all direct and transitive predecessor dependencies for a node."""
        if node_id not in self.nx_graph:
            return set()
        return nx.ancestors(self.nx_graph, node_id)

    def get_dependents(self, node_id: str) -> Set[str]:
        """Return the set of all direct and transitive successor dependents for a node."""
        if node_id not in self.nx_graph:
            return set()
        return nx.descendants(self.nx_graph, node_id)

    def is_independent(self, node_a: str, node_b: str) -> bool:
        """Check if two nodes are independent (neither depends on the other)."""
        if node_a not in self.nx_graph or node_b not in self.nx_graph:
            return True
        return (
            node_b not in nx.ancestors(self.nx_graph, node_a)
            and node_b not in nx.descendants(self.nx_graph, node_a)
        )

    def _get_dag_copy(self) -> nx.DiGraph:
        """
        Return a DAG copy of the workflow graph.
        Identifies cycles and breaks them at ConditionNode boundaries (representing loop checks)
        or default fallback edges to allow scheduling computations.
        """
        g = self.nx_graph.copy()
        # Keep breaking cycles until none remain
        while not nx.is_directed_acyclic_graph(g):
            try:
                # Find one cycle
                cycle = nx.find_cycle(g, orientation="original")
                # Look for an edge starting from a ConditionNode in the cycle
                removed = False
                for u, v, _ in cycle:
                    node_data = self.graph.nodes.get(u)
                    if node_data and getattr(node_data, "type", None) == NodeType.CONDITION:
                        g.remove_edge(u, v)
                        removed = True
                        break
                # If no ConditionNode is in the cycle, break the first edge in the cycle
                if not removed and cycle:
                    u, v, _ = cycle[0]
                    g.remove_edge(u, v)
            except nx.NetworkXNoCycle:
                break
        return g

    def get_execution_layers(self) -> List[List[str]]:
        """
        Compute execution layers (stages) for concurrent node execution.
        Loops are resolved/broken at condition boundaries.
        Returns a list of stages, where each stage is a list of node IDs that can run in parallel.
        """
        dag = self._get_dag_copy()
        layers: List[List[str]] = []
        
        while dag.number_of_nodes() > 0:
            roots = [node for node in dag.nodes() if dag.in_degree(node) == 0]
            if not roots:
                # Fallback to prevent infinite loop in case cycle-breaking failed
                break
            layers.append(roots)
            dag.remove_nodes_from(roots)
            
        return layers
