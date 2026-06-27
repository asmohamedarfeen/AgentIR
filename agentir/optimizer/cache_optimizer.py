"""
Cache Optimizer pass for AgentIR.
Identifies expensive operations (LLM inferences, tool calls) and annotates them
with caching metadata configurations to prevent redundant runtime executions.
"""

import json
import hashlib
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class CacheOptimizer:
    """Instruments workflow nodes with caching properties to avoid redundant runs."""

    def optimize(self, graph: WorkflowGraph) -> WorkflowGraph:
        """
        Scan all nodes in the graph:
        1. Enable caching for LLMNodes and ToolNodes by setting 'cache_enabled' in metadata.
        2. Compute deterministic cache keys for redundant tool or LLM tasks based on their inputs.
        """
        opt_graph = WorkflowGraph(
            nodes={nid: node.model_copy(deep=True) for nid, node in graph.nodes.items()},
            edges=[edge.model_copy(deep=True) for edge in graph.edges]
        )

        def serialize_args(args) -> str:
            return json.dumps(args, sort_keys=True)

        for node in opt_graph.nodes.values():
            if node.type == NodeType.LLM:
                # LLM caching
                node.metadata["cache_enabled"] = True
                # Generate a hash representing the model and prompt configuration
                payload = f"llm:{node.model}:{node.prompt_template}:{node.system_instruction or ''}:{node.temperature}"
                payload_hash = hashlib.md5(payload.encode("utf-8")).hexdigest()
                node.metadata["cache_key"] = f"llm_cache:{node.id}:{payload_hash}"

            elif node.type == NodeType.TOOL:
                # Tool caching
                node.metadata["cache_enabled"] = True
                # Generate a hash representing the tool call payload
                serialized_args = serialize_args(node.args)
                payload = f"tool:{node.tool_name}:{serialized_args}"
                payload_hash = hashlib.md5(payload.encode("utf-8")).hexdigest()
                node.metadata["cache_key"] = f"tool_cache:{node.tool_name}:{payload_hash}"

        return opt_graph
