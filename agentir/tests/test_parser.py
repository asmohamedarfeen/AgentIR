import pytest
from typing import Dict, Any

from agentir.parser.langgraph import LangGraphParser
from agentir.ir.graph import WorkflowGraph
from agentir.ir.node import NodeType, LLMNode, ToolNode, ConditionNode


def test_parser_dict_deserialization():
    """Verify that parsing a dict-based serialized graph works correctly."""
    data = {
        "nodes": {
            "start": {
                "id": "start",
                "type": "start",
                "name": "Start Node"
            },
            "llm_1": {
                "id": "llm_1",
                "type": "llm",
                "name": "LLM Inference",
                "model": "gpt-4",
                "prompt_template": "Analyze: {text}"
            },
            "end": {
                "id": "end",
                "type": "end",
                "name": "End Node"
            }
        },
        "edges": [
            {"source": "start", "target": "llm_1"},
            {"source": "llm_1", "target": "end"}
        ]
    }

    parser = LangGraphParser()
    graph = parser.parse(data)

    assert isinstance(graph, WorkflowGraph)
    assert len(graph.nodes) == 3
    assert isinstance(graph.nodes["llm_1"], LLMNode)
    assert len(graph.edges) == 2
    assert graph.edges[0].source == "start"
    assert graph.edges[0].target == "llm_1"


class MockBranch:
    """Mock representing a conditional branch in a LangGraph builder."""
    def __init__(self, path_func_name: str, path_map: Dict[str, str]):
        # Set function name via double underscore or callable mock
        class PathFunc:
            pass
        self.path = PathFunc()
        self.path.__name__ = path_func_name
        self.path_map = path_map


class MockLangGraph:
    """Mock representing a live LangGraph StateGraph builder."""
    def __init__(self):
        class LLMCallable:
            model = "gpt-4-mini"
            prompt_template = "Question: {text}"
            inputs = ["text"]
            outputs = ["answer"]

        class ToolCallable:
            tool_name = "weather_lookup"
            args = {"location": "London"}

        self.nodes = {
            "llm_agent": LLMCallable(),
            "weather_tool": ToolCallable()
        }
        self.edges = [
            ("__start__", "llm_agent"),
            ("weather_tool", "__end__")
        ]
        # Branches mapping source -> branch_key -> MockBranch
        self.branches = {
            "llm_agent": {
                "routing_branch": MockBranch("router_func", {"yes": "weather_tool", "no": "__end__"})
            }
        }


def test_parser_live_mock_graph():
    """Verify live LangGraph parsing with standard, conditional routing translation."""
    mock_graph = MockLangGraph()
    parser = LangGraphParser()
    
    graph = parser.parse(mock_graph)
    
    assert isinstance(graph, WorkflowGraph)
    
    # Boundary nodes
    assert "__start__" in graph.nodes
    assert "__end__" in graph.nodes
    
    # Typed mapped nodes
    assert "llm_agent" in graph.nodes
    assert isinstance(graph.nodes["llm_agent"], LLMNode)
    assert graph.nodes["llm_agent"].model == "gpt-4-mini"
    assert graph.nodes["llm_agent"].inputs == ["text"]
    assert graph.nodes["llm_agent"].outputs == ["answer"]

    assert "weather_tool" in graph.nodes
    assert isinstance(graph.nodes["weather_tool"], ToolNode)
    assert graph.nodes["weather_tool"].tool_name == "weather_lookup"

    # Conditional Branch parsed as ConditionNode
    assert "llm_agent_router" in graph.nodes
    router = graph.nodes["llm_agent_router"]
    assert isinstance(router, ConditionNode)
    assert router.condition_expr == "router_func"
    assert router.branches == {"yes": "weather_tool", "no": "__end__"}

    # Edge routing validation:
    # __start__ -> llm_agent
    # llm_agent -> llm_agent_router
    # llm_agent_router -> weather_tool (port "yes")
    # llm_agent_router -> __end__ (port "no")
    # weather_tool -> __end__
    assert len(graph.edges) == 5

    # Check start connection
    start_edges = [e for e in graph.edges if e.source == "__start__"]
    assert len(start_edges) == 1
    assert start_edges[0].target == "llm_agent"

    # Check routing connections
    router_edges = [e for e in graph.edges if e.source == "llm_agent_router"]
    assert len(router_edges) == 2
    ports = {e.source_port: e.target for e in router_edges}
    assert ports == {"yes": "weather_tool", "no": "__end__"}
