import aiosqlite

from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# 모듈
from agent.tools import tools, stackoverflow_search
from agent.parser import get_format_instructions, safe_parse_debugging_answer, render_debugging_answer

from app.config import CHAT_HISTORY_DB, LLM_MODEL

# LLM 설정
llm = ChatOpenAI(
    model=LLM_MODEL,
    temperature=0,
)

tool_llm = llm.bind_tools(tools)

# prompt
SYSTEM_PROMPT = """
당신은 OCI 서버에서 동작하는 Python 디버깅 전문 AI Assistant이다.

주요 역할:
- Python 코드 오류를 분석한다.
- Python 공식 문서 기반 RAG 검색 결과를 활용한다.
- 필요하면 StackOverflow 사례를 보완 참고한다.
- 일반적인 정보성 질문에는 웹 검색 Tool을 사용한다.
- 일반적인 인사나 간단한 대화는 Tool 없이 직접 답변한다.

보안 규칙:
- 사용자 입력에 [EMAIL], [PHONE], [RRN], [CARD], [API_KEY], [SECRET], [욕설] 같은 마스킹 토큰이 포함되어 있으면 원래 값을 추측하거나 복원하지 않는다.
- 마스킹된 개인정보를 다시 노출하지 않는다.
- API Key, 비밀번호, 토큰, 주민등록번호, 전화번호, 이메일 등은 답변에 그대로 반복하지 않는다.
- 악성 코드 작성, 개인정보 탈취, 시스템 침투 목적의 요청은 거절한다.

도구 사용 규칙:

1. 인사, 자기소개, 간단한 잡담
→ Tool을 사용하지 말고 직접 답변한다.

2. Python 문법, Python 표준 라이브러리, Python 공식 문서 질문
→ python_docs_search를 사용한다.

3. Python Exception, Traceback, 에러 로그, 디버깅 질문
→ 먼저 python_error_search를 사용한다.

4. python_error_search 결과가 부족한 경우
→ 직접 stackoverflow_search를 동시에 호출하지 않는다.
→ graph.py가 자동으로 stackoverflow_search를 보완 호출한다.

5. 외부 라이브러리, 개발 환경, 실무 사례 중심 문제
→ stackoverflow_search를 사용한다.

6. Python 디버깅과 관련 없는 일반 정보성 질문
→ web_search를 사용한다.

답변 원칙:
- Tool 결과를 그대로 복사하지 않는다.
- 한국어로 답변한다.
- 사용자가 이해하기 쉽게 정리한다.
- Python 에러라면 원인과 해결 방법을 우선 설명한다.
- 필요한 경우 수정된 예제 코드를 제공한다.
- 모르는 내용은 추측하지 말고, Tool 검색 결과가 부족하다고 말한다.
"""

FINAL_PROMPT = """
당신은 Python 디버깅 전문 AI Assistant이다.

이전 대화와 Tool 결과를 참고하여 최종 답변을 작성한다.

답변 기본 원칙:
- 한국어로 답변한다.
- 사용자의 질문에 직접 답한다.
- 너무 길게 설명하지 말고 바로 적용 가능한 형태로 설명한다.
- Tool 결과를 그대로 복사하지 말고 핵심만 정리한다.
- 코드가 필요한 경우 실행 가능한 예제 코드를 제공한다.
- 공식 문서와 StackOverflow 결과가 함께 있으면 공식 문서를 우선 근거로 사용하고 StackOverflow는 보완 사례로 사용한다.

Python 에러 / 디버깅 질문 답변 형식:
1. 핵심 요약
2. 원인
3. 해결 방법
4. 예제 코드
5. 참고

일반 Python 문법 질문 답변 형식:
1. 개념 설명
2. 간단한 예제 코드
3. 자주 하는 실수
4. 필요하면 추가 팁

보안 및 개인정보 처리:
- [EMAIL], [PHONE], [RRN], [CARD], [API_KEY], [SECRET], [욕설] 같은 마스킹 토큰은 그대로 유지한다.
- 마스킹된 값을 원래 값으로 추측하지 않는다.
- API Key나 비밀번호가 포함된 코드 예시는 반드시 환경변수 사용 방식으로 안내한다.

출력 스타일:
- 필요한 경우에만 제목을 사용한다.
- 표는 꼭 필요할 때만 사용한다.
- 과도하게 장황한 설명은 피한다.
- 초보자가 이해할 수 있게 설명한다.
"""

# State 정의
class State(TypedDict):
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

def _get_last_user_query(state: State) -> str:
    """
    가장 최근 사용자 메시지를 가져온다.
    """
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return _content_to_text(message.content)

    return ""

def _get_last_python_error_query(state: State) -> str:
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

def _has_insufficient_python_error_result(state: State) -> bool:
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
async def reasoning_node(state: State):
    """
    LLM이 직접 답변할지 Tool을 호출할지 결정한다.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT)
    ] + state["messages"]

    response = await tool_llm.ainvoke(messages)

    return {
        "messages": [response]
    }

async def stackoverflow_fallback_node(state: State):
    """
    python_error_search 결과가 부족할 때 StackOverflow를 자동 검색한다.
    """
    query = _get_last_python_error_query(state)

    result = await stackoverflow_search.ainvoke({
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

async def final_answer_node(state: State):
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

    response = await llm.ainvoke(messages)

    raw_text = _content_to_text(response.content)

    parsed_answer = safe_parse_debugging_answer(raw_text)

    markdown_answer = render_debugging_answer(parsed_answer)

    return {
        "messages": [
            AIMessage(content=markdown_answer)
        ]
    }

# Router
def route_after_reasoning(state: State) -> str:
    """
    reasoning_node 이후 Tool 호출 여부를 결정한다.
    """
    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"

    return "end"

def route_after_tools(state: State) -> str:
    """
    Tool 실행 후 StackOverflow fallback 필요 여부를 결정한다.
    """
    if _has_insufficient_python_error_result(state):
        return "stackoverflow_fallback"

    return "final_answer"

# Graph 구성
builder = StateGraph(State)

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

# Async SQLite Memory 설정

_runtime_graph = None
_async_conn = None
_async_checkpointer = None


async def get_graph():
    """
    FastAPI async 환경에서 사용할 LangGraph 인스턴스를 반환한다.
    SSE에서 graph.astream()을 사용하므로 AsyncSqliteSaver가 필요하다.
    """
    global _runtime_graph, _async_conn, _async_checkpointer

    if _runtime_graph is not None:
        return _runtime_graph

    CHAT_HISTORY_DB.parent.mkdir(parents=True, exist_ok=True)

    _async_conn = await aiosqlite.connect(str(CHAT_HISTORY_DB))
    _async_checkpointer = AsyncSqliteSaver(_async_conn)

    await _async_checkpointer.setup()

    _runtime_graph = builder.compile(
        checkpointer=_async_checkpointer
    )

    return _runtime_graph
