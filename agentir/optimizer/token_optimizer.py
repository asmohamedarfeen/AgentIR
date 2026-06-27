"""
Token and Context Optimization pass for AgentIR.
Provides static analyses and annotations to reduce input/output token consumption.
"""

from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class TokenOptimizer:
    """Optimizes LLM node properties and metadata to minimize token footprint."""

    def optimize(self, graph: WorkflowGraph) -> WorkflowGraph:
        """
        Optimize the graph's nodes for token efficiency:
        - Annotates classification/routing agents with small max_output_tokens.
        - Configures text-heavy inputs for automatic truncation.
        - Enables context caching for nodes sharing identical system instructions.
        """
        opt_graph = WorkflowGraph(
            nodes=graph.nodes.copy(),
            edges=graph.edges.copy()
        )

        system_instructions_seen = {}

        for node_id, node in opt_graph.nodes.items():
            if node.type != NodeType.LLM:
                continue

            # 1. Dynamic Output Token Capping
            # If the node's name suggests classification, routing, or simple decision-making,
            # cap its output tokens to prevent verbose conversational responses.
            name_lower = node.name.lower()
            if any(term in name_lower for term in ["route", "decide", "orchestrate", "classify", "judge", "filter"]):
                node.metadata["max_output_tokens"] = 64
                node.metadata["token_optimization_applied"] = True
            else:
                # Default output cap for general agent tasks
                node.metadata["max_output_tokens"] = 512

            # 2. Input Truncation Rules
            # If the node consumes large textual inputs (e.g. search results, documentation),
            # annotate it with an input character limit.
            if any(term in "".join(node.inputs).lower() for term in ["results", "notes", "report", "content", "document", "text"]):
                node.metadata["input_truncation_limit"] = 1500  # Truncate text variables to 1500 chars (approx. 350 tokens)
                node.metadata["token_optimization_applied"] = True

            # 3. Context Caching Detection
            # If a node uses system instructions, track it. If multiple nodes use the same
            # instruction prompt, they can share a context cache.
            sys_instr = getattr(node, "system_instruction", None)
            if sys_instr:
                if sys_instr in system_instructions_seen:
                    # Mark both nodes as cacheable
                    node.metadata["context_cache_enabled"] = True
                    opt_graph.nodes[system_instructions_seen[sys_instr]].metadata["context_cache_enabled"] = True
                else:
                    system_instructions_seen[sys_instr] = node_id

        return opt_graph
