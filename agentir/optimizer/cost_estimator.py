"""
Cost and Latency Estimator pass for AgentIR.
Performs static analysis on WorkflowGraphs to project API cost (USD)
and runtime latencies (serial execution vs concurrent critical path).
"""

import networkx as nx
from pydantic import BaseModel, Field

from agentir.analyzer.dependency import DependencyAnalyzer
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType


class CostEstimationReport(BaseModel):
    """Pydantic model containing the details of the cost/latency estimation."""
    total_nodes: int = Field(..., description="Total count of active nodes in the workflow")
    llm_calls_count: int = Field(..., description="Count of LLM inference steps")
    tool_calls_count: int = Field(..., description="Count of external tool executions")
    estimated_cost_usd: float = Field(..., description="Total estimated API cost in USD")
    serial_latency_seconds: float = Field(..., description="Estimated runtime if executed sequentially")
    critical_path_latency_seconds: float = Field(..., description="Estimated runtime if executed with concurrency")


class CostEstimator:
    """Estimates execution costs and path latencies for AgentIR graphs."""

    # Default performance models
    LLM_COST_USD = 0.015
    LLM_LATENCY_SEC = 1.5
    TOOL_COST_USD = 0.002
    TOOL_LATENCY_SEC = 0.5

    def estimate(self, graph: WorkflowGraph) -> CostEstimationReport:
        """
        Evaluate node patterns to generate cost and parallel path estimations.
        Translates node latencies into NetworkX edge weights to find the DAG's critical path.
        """
        total_nodes = len(graph.nodes)
        llm_calls = 0
        tool_calls = 0
        total_cost = 0.0
        serial_latency = 0.0

        for node in graph.nodes.values():
            if node.type == NodeType.LLM:
                llm_calls += 1
                total_cost += self.LLM_COST_USD
                serial_latency += self.LLM_LATENCY_SEC
            elif node.type == NodeType.TOOL:
                tool_calls += 1
                total_cost += self.TOOL_COST_USD
                serial_latency += self.TOOL_LATENCY_SEC

        # Calculate critical path concurrent latency
        critical_path_latency = 0.0
        if total_nodes > 0:
            # 1. Use loop-breaker from DependencyAnalyzer to get a DAG copy
            analyzer = DependencyAnalyzer(graph)
            dag = analyzer._get_dag_copy()

            # 2. Build a DiGraph mapping node latencies to edge weights
            weighted_dag = nx.DiGraph()
            node_latencies = {}

            for node_id, data in dag.nodes(data=True):
                node_obj = data.get("data")
                latency = 0.0
                if node_obj:
                    if node_obj.type == NodeType.LLM:
                        latency = self.LLM_LATENCY_SEC
                    elif node_obj.type == NodeType.TOOL:
                        latency = self.TOOL_LATENCY_SEC
                node_latencies[node_id] = latency
                weighted_dag.add_node(node_id)

            for u, v in dag.edges():
                # The weight of edge U -> V represents V's latency cost
                v_latency = node_latencies.get(v, 0.0)
                weighted_dag.add_edge(u, v, weight=v_latency)

            # 3. Find the longest path length (critical path latency)
            if weighted_dag.number_of_nodes() > 0:
                try:
                    path_length = nx.dag_longest_path_length(weighted_dag, weight="weight")
                    longest_path = nx.dag_longest_path(weighted_dag, weight="weight")
                    # Add start node latency (since edge weights only accumulate downstream nodes)
                    start_latency = node_latencies.get(longest_path[0], 0.0) if longest_path else 0.0
                    critical_path_latency = path_length + start_latency
                except Exception:
                    # Fallback to serial latency if path calculation fails
                    critical_path_latency = serial_latency

        return CostEstimationReport(
            total_nodes=total_nodes,
            llm_calls_count=llm_calls,
            tool_calls_count=tool_calls,
            estimated_cost_usd=round(total_cost, 4),
            serial_latency_seconds=round(serial_latency, 2),
            critical_path_latency_seconds=round(critical_path_latency, 2)
        )
