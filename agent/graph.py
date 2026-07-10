import os
import sqlite3

from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage,
    AIMessage,
    HumanMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite import SqliteSaver

# 모듈
from agent.tools import tools, stackoverflow_search
from agent.prompts import SYSTEM_PROMPT, FINAL_PROMPT
from agent.parser import (
    get_format_instructions,
    safe_parse_debugging_answer,
    render_debugging_answer,
)

from dotenv import load_dotenv
load_dotenv()

# 환경 변수
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
CHAT_HISTORY_DB = os.getenv("CHAT_HISTORY_DB", "/mnt/data/chat_history.db")

os.makedirs(os.path.dirname(CHAT_HISTORY_DB), exist_ok=True)

# LLM 설정
llm = ChatOpenAI(
    model=LLM_MODEL,
    temperature=0,
)

tool_llm = llm.bind_tools(tools)

# State 정의
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

# 유틸 함수
def _content_to_text(content) -> str:
    """
    Message content를 문자열로 변환
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))

        return "\n".join(parts)

    return str(content)

def _get_last_user_query(state: AgentState) -> str:
    """
    가장 최근 사용자 메시지를 가져온다.
    """
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return _content_to_text(message.content)

    return ""

def _get_last_python_error_query(state: AgentState) -> str:
    """
    최근 AIMessage의 tool_calls에서 python_error_search 입력값을 가져온다.
    없으면 최근 사용자 메시지를 fallback으로 사용한다.
    """
    for message in reversed(state["messages"]):
        tool_calls = getattr(message, "tool_calls", None)

        if not tool_calls:
            continue

        for tool_call in reversed(tool_calls):
            name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", None)

            if name != "python_error_search":
                continue

            args = tool_call.get("args") if isinstance(tool_call, dict) else getattr(tool_call, "args", {})

            if isinstance(args, dict):
                return (
                    args.get("query")
                    or args.get("error_message")
                    or args.get("input")
                    or _get_last_user_query(state)
                )

            return str(args)

    return _get_last_user_query(state)

def _has_insufficient_python_error_result(state: AgentState) -> bool:
    """
    ToolNode 실행 결과 중 python_error_search 결과가 부족한지 확인한다.
    """
    for message in reversed(state["messages"]):
        if not isinstance(message, ToolMessage):
            continue

        content = _content_to_text(message.content)
        name = getattr(message, "name", "")

        is_python_error_result = (
            name == "python_error_search"
            or "[SEARCH_TOOL]: python_error_search" in content
        )

        if not is_python_error_result:
            continue

        if "[SEARCH_STATUS]: INSUFFICIENT" in content:
            return True

        if "[SEARCH_STATUS]: SUFFICIENT" in content:
            return False

    return False

# Node
def reasoning_node(state: AgentState):
    """
    LLM이 직접 답변할지 Tool을 호출할지 결정한다.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT)
    ] + state["messages"]

    response = tool_llm.invoke(messages)

    return {
        "messages": [response]
    }

def stackoverflow_fallback_node(state: AgentState):
    """
    python_error_search 결과가 부족할 때 StackOverflow를 자동 검색한다.
    """
    query = _get_last_python_error_query(state)

    result = stackoverflow_search.invoke({
        "query": query
    })

    content = f"""
    [자동 보완 검색: StackOverflow]
    python_error_search 결과가 충분하지 않아 StackOverflow 검색을 추가로 수행했습니다.

    검색어:
    {query}

    검색 결과:
    {result}
""".strip()

    return {
        "messages": [
            AIMessage(content=content)
        ]
    }

def final_answer_node(state: AgentState):
    """
    Tool 결과를 참고해 최종 답변을 생성한다.
    OutputParser를 사용해 JSON 구조로 파싱한 뒤 Markdown으로 변환한다.
    """

    parser_instruction = f"""
    아래 형식 지침을 반드시 따르세요.
    
    중요:
    - 반드시 JSON만 출력하세요.
    - Markdown을 직접 출력하지 마세요.
    - 코드 블록도 JSON 문자열 안에 넣으세요.
    - JSON 앞뒤에 설명 문장을 붙이지 마세요.
    
    {get_format_instructions()}
    """

    messages = [
        SystemMessage(content=FINAL_PROMPT),
        SystemMessage(content=parser_instruction),
    ] + state["messages"]

    response = llm.invoke(messages)

    raw_text = _content_to_text(response.content)

    parsed_answer = safe_parse_debugging_answer(raw_text)

    markdown_answer = render_debugging_answer(parsed_answer)

    return {
        "messages": [
            AIMessage(content=markdown_answer)
        ]
    }

# Router
def route_after_reasoning(state: AgentState) -> str:
    """
    reasoning_node 이후 Tool 호출 여부를 결정한다.
    """
    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"

    return "end"

def route_after_tools(state: AgentState) -> str:
    """
    Tool 실행 후 StackOverflow fallback 필요 여부를 결정한다.
    """
    if _has_insufficient_python_error_result(state):
        return "stackoverflow_fallback"

    return "final_answer"

# Graph 구성
builder = StateGraph(AgentState)

builder.add_node("reasoning", reasoning_node)
builder.add_node("tools", ToolNode(tools))
builder.add_node("stackoverflow_fallback", stackoverflow_fallback_node)
builder.add_node("final_answer", final_answer_node)

builder.add_edge(START, "reasoning")

builder.add_conditional_edges(
    "reasoning",
    route_after_reasoning,
    {
        "tools": "tools",
        "end": END,
    },
)

builder.add_conditional_edges(
    "tools",
    route_after_tools,
    {
        "stackoverflow_fallback": "stackoverflow_fallback",
        "final_answer": "final_answer",
    },
)

builder.add_edge("stackoverflow_fallback", "final_answer")
builder.add_edge("final_answer", END)

# SQLite Memory 설정
conn = sqlite3.connect(
    CHAT_HISTORY_DB,
    check_same_thread=False,
)

checkpointer = SqliteSaver(conn)

graph = builder.compile(
    checkpointer=checkpointer
)