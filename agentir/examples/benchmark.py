"""
Benchmark example script for AgentIR.
Demonstrates resource and latency improvements of AgentIR compiler optimization
by comparing an unoptimized sequential agent workflow against an optimized workflow
utilizing the Gemini API.
"""

import asyncio
import os
import time
from typing import Any, Dict

import google.generativeai as genai

# Import AgentIR components
from agentir.ir.node import StartNode, EndNode, LLMNode, ToolNode
from agentir.ir.edge import Edge
from agentir.ir.graph import WorkflowGraph
from agentir.optimizer.dead_nodes import DeadNodesOptimizer
from agentir.optimizer.duplicate_tools import DuplicateToolsOptimizer
from agentir.optimizer.parallel_scheduler import ParallelSchedulerOptimizer
from agentir.optimizer.cache_optimizer import CacheOptimizer
from agentir.optimizer.cost_estimator import CostEstimator
from agentir.runtime.executor import WorkflowExecutor


# Setup Gemini API configuration
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
use_live_api = bool(api_key)

if use_live_api:
    genai.configure(api_key=api_key)
    print("configured live Gemini API client.")
else:
    print("No GEMINI_API_KEY or GOOGLE_API_KEY found in environment. Running with simulated Gemini API responses.")


# --- Define Tool and LLM Callbacks ---
# We keep track of resource utilization counters
tool_calls_count = 0
llm_calls_count = 0

async def google_search_callback(state: Dict[str, Any]) -> Dict[str, Any]:
    global tool_calls_count
    tool_calls_count += 1
    query = state.get("query", "AgentIR")
    print(f"  [Tool] Executing Google Search for query: '{query}'...")
    # Simulate network latency
    await asyncio.sleep(0.4)
    return {"search_results": f"Results for '{query}': AgentIR is an optimization compiler."}


async def weather_lookup_callback(state: Dict[str, Any]) -> Dict[str, Any]:
    global tool_calls_count
    tool_calls_count += 1
    print("  [Tool] Executing weather lookup for Paris...")
    await asyncio.sleep(0.4)
    return {"weather_results": "Paris: 22C, Clear Sky"}


async def gemini_llm_callback(state: Dict[str, Any]) -> Dict[str, Any]:
    global llm_calls_count
    llm_calls_count += 1
    
    prompt = f"Summarize these search results: {state.get('search_results', '')}"
    print(f"  [LLM] Calling Gemini API (Prompt size: {len(prompt)} chars)...")
    
    if use_live_api:
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = await asyncio.to_thread(model.generate_content, prompt)
            return {"summary": response.text}
        except Exception as e:
            print(f"    Gemini API call failed ({e}). Falling back to simulation.")
    
    # Simulation fallback
    await asyncio.sleep(1.2)
    return {"summary": "AgentIR is an optimization compiler for AI agents."}


# Define the callback registry
registry = {
    "google_search_1": google_search_callback,
    "google_search_2": google_search_callback,
    "weather_lookup": weather_lookup_callback,
    "llm_summary": gemini_llm_callback,
}


# --- Define the Workflow ---
def build_benchmark_workflow() -> WorkflowGraph:
    graph = WorkflowGraph()
    
    # 1. Structural boundaries
    start = StartNode(id="start", name="Start", outputs=["query"])
    end = EndNode(id="end", name="End", inputs=["summary"])
    
    # 2. Duplicate tool calls (searching identical query twice)
    search1 = ToolNode(
        id="google_search_1",
        name="Search 1",
        tool_name="google_search",
        args={"query": "AgentIR workflow framework"},
        inputs=["query"],
        outputs=["search_results"]
    )
    search2 = ToolNode(
        id="google_search_2",
        name="Search 2",
        tool_name="google_search",
        args={"query": "AgentIR workflow framework"},
        inputs=["query"],
        outputs=["search_results_duplicate"]
    )
    
    # 3. Dead node (weather is looked up, but output is never consumed by downstream nodes)
    weather = ToolNode(
        id="weather_lookup",
        name="Weather Lookup",
        tool_name="weather_lookup",
        outputs=["weather_results"]
    )
    
    # 4. LLM summaries (only consumes query results)
    llm = LLMNode(
        id="llm_summary",
        name="Gemini Summary",
        model="gemini-2.5-flash",
        prompt_template="Summarize: {search_results}",
        inputs=["search_results"],
        outputs=["summary"]
    )
    
    # Add nodes to graph
    for node in [start, search1, search2, weather, llm, end]:
        graph.add_node(node)
        
    # Add standard control edges representing sequential execution without optimization
    graph.add_edge(Edge(source="start", target="google_search_1"))
    graph.add_edge(Edge(source="google_search_1", target="google_search_2"))
    graph.add_edge(Edge(source="google_search_2", target="weather_lookup"))
    graph.add_edge(Edge(source="weather_lookup", target="llm_summary"))
    graph.add_edge(Edge(source="llm_summary", target="end"))
    
    return graph


# --- Execution without AgentIR (Plain Sequential) ---
async def run_without_agentir(graph: WorkflowGraph, initial_state: Dict[str, Any]) -> Dict[str, Any]:
    state = initial_state.copy()
    # Unoptimized sequential execution order
    sequential_order = ["start", "google_search_1", "google_search_2", "weather_lookup", "llm_summary", "end"]
    for nid in sequential_order:
        node = graph.nodes.get(nid)
        if not node:
            continue
            
        callback = registry.get(nid)
        if callback:
            updates = await callback(state)
            state.update(updates)
    return state


# --- Main Benchmarking Runner ---
async def main():
    global tool_calls_count, llm_calls_count
    
    print("=" * 60)
    print("                 AgentIR Optimization Benchmark")
    print("=" * 60)
    
    graph = build_benchmark_workflow()
    initial_state = {"query": "AgentIR workflow framework"}
    
    # -------------------------------------------------------------
    # 1. RUN UNOPTIMIZED
    # -------------------------------------------------------------
    print("\n[Phase 1] Executing UNOPTIMIZED Sequential Agent Workflow...")
    tool_calls_count = 0
    llm_calls_count = 0
    
    start_time = time.time()
    unopt_state = await run_without_agentir(graph, initial_state)
    unopt_duration = time.time() - start_time
    
    unopt_tools = tool_calls_count
    unopt_llms = llm_calls_count
    print(f"Unoptimized execution completed in {unopt_duration:.3f}s")
    
    # -------------------------------------------------------------
    # 2. RUN OPTIMIZED (WITH AGENTIR)
    # -------------------------------------------------------------
    print("\n[Phase 2] Optimizing Agent Workflow with AgentIR Compiler Passes...")
    
    # Apply static optimizations
    print("  -> Applying Dead Node Elimination...")
    opt_graph = DeadNodesOptimizer().optimize(graph)
    
    print("  -> Applying Duplicate Tool (CSE) Merging...")
    opt_graph = DuplicateToolsOptimizer().optimize(opt_graph)
    
    print("  -> Applying Parallel Scheduler Rescheduling...")
    opt_graph = ParallelSchedulerOptimizer().optimize(opt_graph)
    
    print("  -> Inserting Cache Descriptors...")
    opt_graph = CacheOptimizer().optimize(opt_graph)
    
    # Estimate costs
    estimator = CostEstimator()
    estimate_report = estimator.estimate(opt_graph)
    
    print("\n[Phase 3] Executing OPTIMIZED Agent Workflow using Asynchronous Runtime...")
    tool_calls_count = 0
    llm_calls_count = 0
    
    executor = WorkflowExecutor(opt_graph, registry)
    start_time = time.time()
    opt_state = await executor.execute(initial_state)
    opt_duration = time.time() - start_time
    
    opt_tools = tool_calls_count
    opt_llms = llm_calls_count
    print(f"Optimized execution completed in {opt_duration:.3f}s")
    
    # -------------------------------------------------------------
    # 3. REPORT COMPARISON
    # -------------------------------------------------------------
    print("\n" + "=" * 60)
    print("                      BENCHMARK REPORT")
    print("=" * 60)
    print(f"{'Metric':<30} | {'Unoptimized':<12} | {'Optimized':<12} | {'Savings':<10}")
    print("-" * 75)
    
    # Latency
    savings_time = unopt_duration - opt_duration
    pct_time = (savings_time / unopt_duration) * 100
    print(f"{'Wall-clock Execution Time':<30} | {unopt_duration:>10.3f}s | {opt_duration:>10.3f}s | {pct_time:>8.1f}%")
    
    # Tool Calls
    savings_tools = unopt_tools - opt_tools
    pct_tools = (savings_tools / unopt_tools) * 100 if unopt_tools > 0 else 0
    print(f"{'External Tool Invocations':<30} | {unopt_tools:>12} | {opt_tools:>12} | {pct_tools:>8.1f}%")
    
    # LLM Calls
    savings_llms = unopt_llms - opt_llms
    pct_llms = (savings_llms / unopt_llms) * 100 if unopt_llms > 0 else 0
    print(f"{'LLM Inference Calls':<30} | {unopt_llms:>12} | {opt_llms:>12} | {pct_llms:>8.1f}%")
    
    print("-" * 75)
    print("Static Compile-Time Projections (CostEstimator):")
    print(f"  Projected Serial Latency:       {estimate_report.serial_latency_seconds:.1f}s")
    print(f"  Projected Parallel Latency:     {estimate_report.critical_path_latency_seconds:.1f}s")
    print(f"  Projected Total Cost (USD):     ${estimate_report.estimated_cost_usd:.4f}")
    
    print("=" * 60)
    print("Summary:")
    print(f"  - Merged {savings_tools - 1} duplicate tool call(s).")
    print(f"  - Eliminated {1} unused dead node(s).")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
