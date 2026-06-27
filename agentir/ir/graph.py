"""
WorkflowGraph definitions for AgentIR.
Manages nodes and edges, offering NetworkX integration and basic structure verification.
"""

from typing import Dict, List, Optional
import networkx as nx
from pydantic import BaseModel, Field

from agentir.ir.edge import Edge
from agentir.ir.node import AnyNode


class WorkflowGraph(BaseModel):
    """Represents a full agentic workflow graph composed of nodes and edges."""
    nodes: Dict[str, AnyNode] = Field(
        default_factory=dict,
        description="Map of unique node ID to the corresponding Node object"
    )
    edges: List[Edge] = Field(
        default_factory=list,
        description="List of directed edges connecting the nodes"
    )

    def add_node(self, node: AnyNode) -> None:
        """Add or update a node in the graph."""
        self.nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        """Remove a node by its ID and clean up any associated edges."""
        if node_id in self.nodes:
            del self.nodes[node_id]
        # Remove any edges connected to this node
        self.edges = [
            edge for edge in self.edges
            if edge.source != node_id and edge.target != node_id
        ]

    def add_edge(self, edge: Edge) -> None:
        """Add a connection between nodes. Raises ValueError if either node is missing."""
        if edge.source not in self.nodes:
            raise ValueError(f"Source node '{edge.source}' does not exist in the graph.")
        if edge.target not in self.nodes:
            raise ValueError(f"Target node '{edge.target}' does not exist in the graph.")
        if edge not in self.edges:
            self.edges.append(edge)

    def remove_edge(self, source: str, target: str, source_port: Optional[str] = None) -> None:
        """Remove an edge matching source, target, and optional source_port."""
        self.edges = [
            e for e in self.edges
            if not (
                e.source == source
                and e.target == target
                and (source_port is None or e.source_port == source_port)
            )
        ]

    def to_networkx(self) -> nx.DiGraph:
        """Convert the workflow graph into a NetworkX DiGraph for analysis/traversal."""
        g = nx.DiGraph()
        for node_id, node in self.nodes.items():
            g.add_node(node_id, data=node)
        for edge in self.edges:
            g.add_edge(
                edge.source,
                edge.target,
                source_port=edge.source_port,
                target_port=edge.target_port,
                condition=edge.condition,
                data=edge
            )
        return g

    @classmethod
    def from_networkx(cls, g: nx.DiGraph) -> "WorkflowGraph":
        """Reconstruct a WorkflowGraph from a NetworkX DiGraph."""
        nodes = {}
        edges = []
        for node_id, data in g.nodes(data=True):
            if "data" in data and isinstance(data["data"], BaseModel):
                nodes[node_id] = data["data"]
            else:
                # Fallback to reconstructing from dict attributes if stored raw
                pass
        
        for u, v, data in g.edges(data=True):
            if "data" in data and isinstance(data["data"], Edge):
                edges.append(data["data"])
            else:
                edges.append(
                    Edge(
                        source=u,
                        target=v,
                        source_port=data.get("source_port"),
                        target_port=data.get("target_port"),
                        condition=data.get("condition"),
                    )
                )
        return cls(nodes=nodes, edges=edges)

    def get_successors(self, node_id: str) -> List[str]:
        """Get the node IDs of all direct successors of a given node."""
        return [edge.target for edge in self.edges if edge.source == node_id]

    def get_predecessors(self, node_id: str) -> List[str]:
        """Get the node IDs of all direct predecessors of a given node."""
        return [edge.source for edge in self.edges if edge.target == node_id]

    def validate_graph(self) -> List[str]:
        """Run structural validation checks. Returns a list of error messages (empty if valid)."""
        errors = []
        # Check for dangling edges
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Dangling edge: source node '{edge.source}' does not exist.")
            if edge.target not in self.nodes:
                errors.append(f"Dangling edge: target node '{edge.target}' does not exist.")
        return errors
