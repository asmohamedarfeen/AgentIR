"""
LangGraph Parser for AgentIR.
Converts active LangGraph graphs (StateGraph/CompiledStateGraph)
or serialized JSON-like schemas into AgentIR WorkflowGraph definitions.
"""

from typing import Any, Dict, Union
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import (
    Node, StartNode, EndNode, LLMNode, ToolNode, ConditionNode, NodeType
)
from agentir.ir.edge import Edge


class LangGraphParser:
    """Parses LangGraph structures into optimized AgentIR WorkflowGraphs."""

    def parse(self, graph_obj: Any) -> WorkflowGraph:
        """
        Parse a graph input.
        - If graph_obj is a dict, validates and loads it as a serialized schema.
        - If graph_obj is a live LangGraph StateGraph/CompiledStateGraph, extracts its properties.
        """
        if isinstance(graph_obj, dict):
            # Parse from serialized representation
            return WorkflowGraph.model_validate(graph_obj)

        return self._parse_live_graph(graph_obj)

    def _parse_live_graph(self, graph_obj: Any) -> WorkflowGraph:
        """Extracts nodes, edges, and conditional branches from a live LangGraph object."""
        # Retrieve the underlying StateGraph builder
        builder = getattr(graph_obj, "builder", graph_obj)

        nodes = getattr(builder, "nodes", {})
        edges = getattr(builder, "edges", [])
        # branches in LangGraph map: source_node_name -> dict of branches
        branches = getattr(builder, "branches", {})

        ir_graph = WorkflowGraph()

        # 1. Map nodes
        # In LangGraph, START and END are special structural markers (usually __start__ and __end__)
        ir_graph.add_node(StartNode(id="__start__", name="Start"))
        ir_graph.add_node(EndNode(id="__end__", name="End"))

        for name, node_val in nodes.items():
            if name in ("__start__", "__end__"):
                continue

            node_type = self._determine_node_type(name, node_val)
            
            # Extract inputs/outputs if defined on callable or metadata
            inputs = self._get_node_attribute(node_val, "inputs", [])
            outputs = self._get_node_attribute(node_val, "outputs", [])

            if node_type == NodeType.LLM:
                ir_graph.add_node(
                    LLMNode(
                        id=name,
                        name=name,
                        model=self._get_node_attribute(node_val, "model", "default-llm"),
                        prompt_template=self._get_node_attribute(node_val, "prompt_template", "{text}"),
                        inputs=inputs,
                        outputs=outputs
                    )
                )
            elif node_type == NodeType.TOOL:
                ir_graph.add_node(
                    ToolNode(
                        id=name,
                        name=name,
                        tool_name=self._get_node_attribute(node_val, "tool_name", name),
                        args=self._get_node_attribute(node_val, "args", {}),
                        inputs=inputs,
                        outputs=outputs
                    )
                )
            else:
                ir_graph.add_node(
                    Node(
                        id=name,
                        type=node_type,
                        name=name,
                        inputs=inputs,
                        outputs=outputs
                    )
                )

        # 2. Map standard edges
        # edges is a set/list of tuples: (source, target)
        for src, tgt in edges:
            ir_graph.add_edge(Edge(source=src, target=tgt))
            if tgt == "__end__":
                src_node = ir_graph.nodes.get(src)
                if src_node and getattr(src_node, "outputs", None):
                    end_node = ir_graph.nodes.get("__end__")
                    if end_node:
                        for var in src_node.outputs:
                            if var not in end_node.inputs:
                                end_node.inputs.append(var)

        # 3. Map conditional branches
        # In LangGraph, a branch contains a path condition function and a path_map (outcome -> target)
        # We translate this into a ConditionNode that intercepts the flow from source to targets.
        for src, branch_dict in branches.items():
            for branch_key, branch_obj in branch_dict.items():
                path_func = getattr(branch_obj, "path", None)
                path_map = getattr(branch_obj, "path_map", {})

                # If no path_map, fallback to dictionary attributes if available
                if not path_map and isinstance(branch_obj, dict):
                    path_map = branch_obj.get("path_map", {})
                    path_func = branch_obj.get("path")

                if path_map:
                    condition_name = getattr(path_func, "__name__", str(path_func))
                    router_id = f"{src}_router"

                    # Add the ConditionNode
                    ir_graph.add_node(
                        ConditionNode(
                            id=router_id,
                            name=f"{src} router",
                            condition_expr=condition_name,
                            branches=path_map
                        )
                    )

                    # Connect: source -> router
                    ir_graph.add_edge(Edge(source=src, target=router_id))

                    # Connect router outputs: router -> targets
                    for outcome, target in path_map.items():
                        ir_graph.add_edge(
                            Edge(
                                source=router_id,
                                target=target,
                                source_port=outcome
                            )
                        )

        return ir_graph

    def _resolve_callable(self, node_val: Any) -> list:
        """Helper to resolve the underlying raw callable/function from wrappers."""
        candidates = [node_val]
        
        # Resolve LangGraph's wrapper (StateNodeSpec -> runnable)
        runnable = getattr(node_val, "runnable", None)
        if runnable is not None:
            candidates.append(runnable)
            
            # Resolve LangChain's wrappers (afunc, func, bound)
            for attr in ("afunc", "func", "bound"):
                inner = getattr(runnable, attr, None)
                if inner is not None:
                    candidates.append(inner)
                    
        return candidates

    def _get_node_attribute(self, node_val: Any, name: str, default: Any = None) -> Any:
        """Search candidates in order to find the first candidate with the attribute."""
        for candidate in self._resolve_callable(node_val):
            val = getattr(candidate, name, None)
            if val is not None:
                return val
        return default

    def _determine_node_type(self, name: str, node_val: Any) -> NodeType:
        """Heuristic to determine node type based on node properties or naming conventions."""
        name_lower = name.lower()
        if "llm" in name_lower or "agent" in name_lower or self._get_node_attribute(node_val, "model") is not None:
            return NodeType.LLM
        if "tool" in name_lower or self._get_node_attribute(node_val, "tool_name") is not None:
            return NodeType.TOOL
        return NodeType.TOOL  # Fallback to standard execution node as a tool
