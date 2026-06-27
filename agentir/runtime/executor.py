"""
Executor framework for AgentIR.
Provides an asynchronous, activation-driven event loop capable of executing
workflow graphs concurrently with state propagation, conditional routing, and error retries.
"""

import asyncio
from typing import Any, Callable, Dict, Optional
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class WorkflowExecutor:
    """Asynchronous engine that executes optimized AgentIR workflows."""

    def __init__(
        self,
        graph: WorkflowGraph,
        registry: Dict[str, Callable[[Dict[str, Any]], Any]]
    ) -> None:
        """
        Initialize the executor.
        - graph: The WorkflowGraph to run.
        - registry: Map of node ID or NodeType string to an async callable.
        """
        self.graph = graph
        self.registry = registry

    async def _execute_node_with_retry(self, node_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a node's registered callback, applying retry limits and exponential backoff."""
        node = self.graph.nodes[node_id]
        callback = self.registry.get(node_id)
        if not callback:
            # Fallback to type-level callback
            callback = self.registry.get(node.type.value)

        if not callback:
            # If no callback is registered, return empty state updates
            return {}

        retry_count = node.metadata.get("retry_count", 0)
        delay = node.metadata.get("retry_delay", 0.05)

        last_exc: Optional[Exception] = None
        for attempt in range(retry_count + 1):
            try:
                # Create a node-specific state copy to prevent side effects on global state
                node_state = state.copy()
                
                # Apply input truncation limit if annotated by the compiler
                trunc_limit = node.metadata.get("input_truncation_limit")
                if trunc_limit:
                    for var in node.inputs:
                        if var in node_state and isinstance(node_state[var], str) and len(node_state[var]) > trunc_limit:
                            node_state[var] = node_state[var][:trunc_limit] + "... [truncated to save tokens]"
                
                # Inject node metadata so callbacks can access compiler properties (like max_output_tokens)
                node_state["_metadata"] = node.metadata

                # Execute callback
                if asyncio.iscoroutinefunction(callback):
                    updates = await callback(node_state)
                else:
                    updates = callback(node_state)
                return updates or {}
            except Exception as e:
                last_exc = e
                if attempt < retry_count:
                    # Exponential backoff
                    await asyncio.sleep(delay * (2 ** attempt))

        if last_exc is not None:
            raise last_exc
        else:
            raise RuntimeError(f"Node '{node_id}' failed execution without catching an exception.")

    async def execute(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the workflow graph starting from StartNode.
        Maintains runtime state and schedules independent nodes concurrently.
        """
        state = initial_state.copy()

        # Find StartNode
        start_nodes = [
            nid for nid, node in self.graph.nodes.items()
            if getattr(node, "type", None) == NodeType.START
        ]
        if not start_nodes:
            raise ValueError("Workflow graph has no StartNode.")

        nx_graph = self.graph.to_networkx()
        in_degrees = {node_id: nx_graph.in_degree(node_id) for node_id in nx_graph.nodes()}
        triggers = {node_id: 0 for node_id in nx_graph.nodes()}
        
        active = set(start_nodes)

        while active:
            nodes_to_run = list(active)
            active.clear()

            # Execute all currently ready nodes in parallel
            tasks = [self._execute_node_with_retry(nid, state) for nid in nodes_to_run]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for nid, res in zip(nodes_to_run, results):
                if isinstance(res, BaseException):
                    raise res

                # Merge node outputs into the global state
                state.update(res)

                node = self.graph.nodes[nid]
                
                # Reset triggers for MergeNode so it can run again if looped
                if node.type == NodeType.MERGE:
                    triggers[nid] = 0

                if node.type == NodeType.CONDITION:
                    # A ConditionNode uses its return or state value to route control flow
                    outcome = res.get("branch") or state.get(node.condition_expr)
                    if not outcome:
                        # Default fallback to the first defined branch outcome
                        outcome = list(node.branches.keys())[0]

                    target = node.branches.get(outcome)

                    if target:
                        triggers[target] += 1
                        target_node = self.graph.nodes.get(target)
                        is_merge = target_node and target_node.type == NodeType.MERGE
                        
                        # Merge nodes wait for all predecessors. Other nodes execute immediately.
                        if (triggers[target] >= in_degrees[target]) if is_merge else True:
                            active.add(target)
                else:
                    # Standard node: propagate activation trigger to all direct successors
                    successors = self.graph.get_successors(nid)
                    for succ in successors:
                        triggers[succ] += 1
                        succ_node = self.graph.nodes.get(succ)
                        is_merge = succ_node and succ_node.type == NodeType.MERGE
                        
                        # Merge nodes wait for all predecessors. Other nodes execute immediately.
                        if (triggers[succ] >= in_degrees[succ]) if is_merge else True:
                            active.add(succ)

        return state
