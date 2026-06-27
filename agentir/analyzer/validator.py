"""
Validation framework for AgentIR workflows.
Checks for cycle correctness, reachability, dangling inputs/outputs, and structural rules.
"""

from typing import List, Optional
import networkx as nx
from pydantic import BaseModel, Field

from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class ValidationIssue(BaseModel):
    """Represents a single structural or semantic issue identified during graph validation."""
    severity: str = Field(..., description="'error' or 'warning'")
    code: str = Field(..., description="Unique validation error code identifier")
    message: str = Field(..., description="Details regarding the validation issue")
    node_id: Optional[str] = Field(None, description="The ID of the node associated with this issue")


class WorkflowValidator:
    """Validator class to evaluate WorkflowGraph schemas for errors and optimizations."""

    def __init__(self, graph: WorkflowGraph) -> None:
        self.graph = graph
        self.nx_graph = graph.to_networkx()

    def validate(self) -> List[ValidationIssue]:
        """Execute all checks. Returns a list of validation issues found."""
        issues: List[ValidationIssue] = []
        self._check_dangling_edges(issues)
        
        # Reachability and cycles rely on node references being valid
        # We only run them if there are no dangling edge errors
        has_dangling = any(issue.code == "DANGLING_EDGE" for issue in issues)
        if not has_dangling:
            self._check_reachability(issues)
            self._check_cycles(issues)
            self._check_data_flow(issues)

        return issues

    def _check_dangling_edges(self, issues: List[ValidationIssue]) -> None:
        """Check for edges pointing to or originating from non-existent nodes."""
        for edge in self.graph.edges:
            if edge.source not in self.graph.nodes:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DANGLING_EDGE",
                        message=f"Edge source node '{edge.source}' does not exist.",
                        node_id=edge.source
                    )
                )
            if edge.target not in self.graph.nodes:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="DANGLING_EDGE",
                        message=f"Edge target node '{edge.target}' does not exist.",
                        node_id=edge.target
                    )
                )

    def _check_reachability(self, issues: List[ValidationIssue]) -> None:
        """Verify node connectivity relative to StartNode and EndNode boundaries."""
        start_nodes = [
            nid for nid, node in self.graph.nodes.items()
            if getattr(node, "type", None) == NodeType.START
        ]
        end_nodes = [
            nid for nid, node in self.graph.nodes.items()
            if getattr(node, "type", None) == NodeType.END
        ]

        # 1. Start Node validation
        if not start_nodes:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="MISSING_START_NODE",
                    message="Workflow is missing a StartNode."
                )
            )
        elif len(start_nodes) > 1:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    code="MULTIPLE_START_NODES",
                    message=f"Workflow contains multiple start nodes: {start_nodes}."
                )
            )

        # 2. End Node validation
        if not end_nodes:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="MISSING_END_NODE",
                    message="Workflow is missing an EndNode."
                )
            )

        # 3. Path reachability
        g = self.nx_graph

        if start_nodes:
            for node_id in g.nodes():
                reachable = False
                for start in start_nodes:
                    if start == node_id or nx.has_path(g, start, node_id):
                        reachable = True
                        break
                if not reachable:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="UNREACHABLE_NODE",
                            message=f"Node '{node_id}' is unreachable from any StartNode.",
                            node_id=node_id
                        )
                    )

        if end_nodes:
            for node_id in g.nodes():
                can_exit = False
                for end in end_nodes:
                    if end == node_id or nx.has_path(g, node_id, end):
                        can_exit = True
                        break
                if not can_exit:
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="DEAD_END_NODE",
                            message=f"Node '{node_id}' cannot reach any EndNode (dead end).",
                            node_id=node_id
                        )
                    )

    def _check_cycles(self, issues: List[ValidationIssue]) -> None:
        """
        Validate cycle control logic.
        Cycles are permitted if and only if they include a ConditionNode (loop exit boundary).
        """
        g = self.nx_graph
        try:
            cycles = list(nx.simple_cycles(g))
            for cycle in cycles:
                has_condition = False
                for node_id in cycle:
                    node_data = self.graph.nodes.get(node_id)
                    if node_data and getattr(node_data, "type", None) == NodeType.CONDITION:
                        has_condition = True
                        break
                if not has_condition:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            code="INFINITE_LOOP",
                            message=f"Infinite cycle detected (no ConditionNode to break path): {cycle}.",
                        )
                    )
        except Exception:
            pass

    def _check_data_flow(self, issues: List[ValidationIssue]) -> None:
        """
        Validate data variables.
        Warns if a node expects an input variable that is not produced by any ancestor node.
        """
        g = self.nx_graph

        for node_id, node in self.graph.nodes.items():
            # If the node has inputs, trace if any ancestor outputs them
            if not node.inputs:
                continue

            ancestors = nx.ancestors(g, node_id)
            # Find outputs of all ancestor nodes
            ancestor_outputs = set()
            for ancestor_id in ancestors:
                ancestor_node = self.graph.nodes.get(ancestor_id)
                if ancestor_node:
                    ancestor_outputs.update(ancestor_node.outputs)

            for val_in in node.inputs:
                if val_in not in ancestor_outputs:
                    # Input is not resolved by ancestors
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            code="MISSING_INPUT",
                            message=f"Input '{val_in}' expected by node '{node_id}' is not produced by any ancestor.",
                            node_id=node_id
                        )
                    )
