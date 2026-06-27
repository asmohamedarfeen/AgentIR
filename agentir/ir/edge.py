"""
Edge definitions for the AgentIR workflow graph.
Defines connection lines between nodes, optionally detailing ports and conditions.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class Edge(BaseModel):
    """Represents a directed link connecting a source node to a target node in the workflow graph."""
    source: str = Field(..., description="ID of the originating node")
    target: str = Field(..., description="ID of the destination node")
    source_port: Optional[str] = Field(
        None,
        description="Optional port on the source node this edge originates from (e.g. branch names)"
    )
    target_port: Optional[str] = Field(
        None,
        description="Optional port on the target node this edge enters"
    )
    condition: Optional[str] = Field(
        None,
        description="Logic, expression or rule that must be met to traverse this edge"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional configuration properties or compiler pass info for the edge"
    )

    def __hash__(self) -> int:
        # Implementing hashing to facilitate NetworkX/set interactions if needed
        return hash((self.source, self.target, self.source_port, self.target_port))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Edge):
            return False
        return (
            self.source == other.source
            and self.target == other.target
            and self.source_port == other.source_port
            and self.target_port == other.target_port
        )
