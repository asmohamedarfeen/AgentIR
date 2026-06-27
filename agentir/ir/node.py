"""
Node definitions for the AgentIR workflow graph.
Defines base and specialized node types using Pydantic.
"""

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Supported types of workflow nodes in AgentIR."""
    START = "start"
    END = "end"
    LLM = "llm"
    TOOL = "tool"
    CONDITION = "condition"
    PARALLEL = "parallel"
    MERGE = "merge"


class Node(BaseModel):
    """Base Node class representing a block of execution in an AgentIR workflow."""
    id: str = Field(..., description="Unique identifier for the node")
    type: NodeType = Field(..., description="Type of the node (e.g., llm, tool)")
    name: str = Field(..., description="Human-readable name of the node")
    inputs: List[str] = Field(
        default_factory=list,
        description="Keys/variables this node expects as input"
    )
    outputs: List[str] = Field(
        default_factory=list,
        description="Keys/variables this node produces as output"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameters, debugging info, and compiler attributes"
    )


class StartNode(Node):
    """The entry point node of the agent workflow."""
    type: Literal[NodeType.START] = NodeType.START


class EndNode(Node):
    """The terminal node of the agent workflow."""
    type: Literal[NodeType.END] = NodeType.END


class LLMNode(Node):
    """A node that performs an inference call using a Language Model."""
    type: Literal[NodeType.LLM] = NodeType.LLM
    model: str = Field(..., description="The name/path of the LLM model to use")
    prompt_template: str = Field(..., description="Template structure for formatting user/system prompts")
    temperature: float = Field(0.7, description="Controls model generation randomness")
    system_instruction: Optional[str] = Field(None, description="System-level instructions for the model")


class ToolNode(Node):
    """A node that executes an external function or tool."""
    type: Literal[NodeType.TOOL] = NodeType.TOOL
    tool_name: str = Field(..., description="The name of the registered tool to call")
    args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Static arguments to pass to the tool"
    )


class ConditionNode(Node):
    """A control flow branching node that routes execution based on a condition."""
    type: Literal[NodeType.CONDITION] = NodeType.CONDITION
    condition_expr: str = Field(..., description="Python expression, key, or logic rule evaluating the route")
    branches: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of transition outcomes (e.g., 'success', 'fail') to expected target nodes or ports"
    )


class ParallelNode(Node):
    """A concurrency node that splits the workflow into parallel paths."""
    type: Literal[NodeType.PARALLEL] = NodeType.PARALLEL


class MergeNode(Node):
    """A join node that synchronizes and merges execution from parallel branches."""
    type: Literal[NodeType.MERGE] = NodeType.MERGE


# Discriminated union for polymorphic parsing based on 'type' field
AnyNode = Annotated[
    Union[
        StartNode,
        EndNode,
        LLMNode,
        ToolNode,
        ConditionNode,
        ParallelNode,
        MergeNode,
    ],
    Field(discriminator="type")
]
