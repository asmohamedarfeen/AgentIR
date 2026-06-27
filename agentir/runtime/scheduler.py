"""
Scheduler definitions for AgentIR.
Partitions the workflow graph into sequential, parallelized execution stages.
"""

from typing import List
from pydantic import BaseModel, Field

from agentir.ir.graph import WorkflowGraph
from agentir.analyzer.dependency import DependencyAnalyzer


class ExecutionStage(BaseModel):
    """A single stage of execution containing node IDs that can run in parallel."""
    stage_index: int = Field(..., description="The sequence order of this execution stage")
    node_ids: List[str] = Field(..., description="The IDs of the nodes to execute in parallel")


class ExecutionPlan(BaseModel):
    """An ordered list of stages representing the complete static execution schedule."""
    stages: List[ExecutionStage] = Field(default_factory=list, description="Ordered execution stages")


class WorkflowScheduler:
    """Schedules workflow graphs into execution stages based on dependency analysis."""

    def create_plan(self, graph: WorkflowGraph) -> ExecutionPlan:
        """
        Partition the graph into stages where each stage runs independent nodes in parallel.
        Loops are broken during scheduling to define static sequence boundaries.
        """
        analyzer = DependencyAnalyzer(graph)
        layers = analyzer.get_execution_layers()
        
        stages = []
        for idx, layer in enumerate(layers):
            stages.append(
                ExecutionStage(
                    stage_index=idx,
                    node_ids=layer
                )
            )
            
        return ExecutionPlan(stages=stages)
