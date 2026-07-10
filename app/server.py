# ai

import os
import time
import uuid
import json

from pathlib import Path
from dotenv import load_dotenv

from agent import graph
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

try:
    from langgraph.errors import GraphRecursionError
except Exception:
    class GraphRecursionError(Exception):
        pass

from agent.graph import get_graph
from app.schemas import ChatRequest, ChatResponse, SanitizationInfo, UsageInfo
from app.middleware import ChatSafetyMiddleware, CallLimitCallbackHandler, CallLimitExceeded, sanitize_text, logger

load_dotenv()


# 환경 변수
SERVICE_NAME = "Python Debug Assistant"

CHROMA_DB_DIR = "/mnt/data/chroma_db"
CHAT_HISTORY_DB = "/mnt/data/chat_history.db"

MAX_MODEL_CALLS = "3"
MAX_TOOL_CALLS = "5"
MAX_TOTAL_CALLS = "8"
MAX_GRAPH_STEPS = "12"

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


# FastAPI App
app = FastAPI(
    title=SERVICE_NAME,
    description="OCI VM에서 실행되는 LangGraph 기반 Python 디버깅 Assistant",
    version="1.0.0",
)


# Middleware


app.add_middleware(ChatSafetyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Static Files
if STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )



# 유틸 함수
def _get_message_text(content) -> str:
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


def _extract_final_answer(result: dict) -> str:
    messages = result.get("messages", [])

    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _get_message_text(message.content)

    if messages:
        return _get_message_text(messages[-1].content)

    return "답변을 생성하지 못했습니다."


def _count_tool_messages(result: dict) -> int:
    messages = result.get("messages", [])
    return sum(1 for message in messages if isinstance(message, ToolMessage))


def _build_sanitization_info(raw: dict) -> SanitizationInfo:
    if not isinstance(raw, dict):
        raw = {}

    return SanitizationInfo(
        masked=raw.get("masked", False),
        pii_detected=raw.get("pii_detected", False),
        pii_types=raw.get("pii_types", []),
        pii_counts=raw.get("pii_counts", {}),
        profanity_detected=raw.get("profanity_detected", False),
        profanity_count=raw.get("profanity_count", 0),
    )



# Routes
@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = STATIC_DIR / "index.html"

    if index_path.exists():
        return FileResponse(index_path)

    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="ko">
        <head>
            <meta charset="UTF-8" />
            <title>Python Debug Assistant</title>
        </head>
        <body>
            <h1>Python Debug Assistant</h1>
            <p>POST /chat 으로 메시지를 보내세요.</p>
        </body>
        </html>
        """
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest):
    start_time = time.perf_counter()

    session_id = payload.session_id or str(uuid.uuid4())

    input_sanitization = _build_sanitization_info(
        getattr(request.state, "sanitization", {})
    )

    limiter = CallLimitCallbackHandler(
        max_model_calls=int(MAX_MODEL_CALLS),
        max_tool_calls=int(MAX_TOOL_CALLS),
        max_total_calls=int(MAX_TOTAL_CALLS),
    )

    try:
        runtime_graph = await get_graph()

        result = await runtime_graph.ainvoke(
            {
                "messages": [
                    HumanMessage(content=payload.message)
                ]
            },
            config={
                "configurable": {
                    "thread_id": session_id,
                },
                "callbacks": [
                    limiter,
                ],
                "recursion_limit": MAX_GRAPH_STEPS,
            },
        )

        raw_answer = _extract_final_answer(result)

        # 모델 응답도 한 번 더 개인정보 / 욕설 마스킹
        safe_answer, output_summary = sanitize_text(raw_answer)
        output_sanitization = _build_sanitization_info(output_summary)

        counts = limiter.get_counts()

        # ToolNode 외부에서 직접 실행된 fallback 검색까지 대략 반영
        actual_tool_messages = _count_tool_messages(result)
        if actual_tool_messages > counts["tool_calls"]:
            counts["tool_calls"] = actual_tool_messages
            counts["total_calls"] = counts["model_calls"] + counts["tool_calls"]

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return ChatResponse(
            session_id=session_id,
            answer=safe_answer,
            masked_input=payload.message,
            input_sanitization=input_sanitization,
            output_sanitization=output_sanitization,
            usage=UsageInfo(
                model_calls=counts["model_calls"],
                tool_calls=counts["tool_calls"],
                total_calls=counts["total_calls"],
                graph_recursion_limit=int(MAX_GRAPH_STEPS),
                elapsed_ms=elapsed_ms,
            ),
        )

    except CallLimitExceeded as e:
        logger.warning(f"Call limit exceeded. session_id={session_id}, error={str(e)}")

        raise HTTPException(
            status_code=429,
            detail={
                "error_type": "CallLimitExceeded",
                "message": "모델 또는 Tool 호출 횟수 제한을 초과했습니다.",
                "detail": str(e),
            },
        )

    except GraphRecursionError as e:
        logger.warning(f"Graph recursion limit exceeded. session_id={session_id}, error={str(e)}")

        raise HTTPException(
            status_code=429,
            detail={
                "error_type": "GraphRecursionLimitExceeded",
                "message": "Agent 실행 단계가 너무 많아 중단했습니다. 무한 루프 방지를 위해 종료되었습니다.",
                "detail": str(e),
            },
        )

    except Exception as e:
        logger.error(f"Chat execution error. session_id={session_id}, error={str(e)}", exc_info=True)

        raise HTTPException(
            status_code=500,
            detail={
                "error_type": "AgentExecutionError",
                "message": "에이전트 처리 중 오류가 발생했습니다.",
                "detail": str(e),
            },
        )

def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _message_content_to_text(content) -> str:
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


@app.get("/api/agent/stream")
async def agent_stream(
    question: str = Query(...),
    session_id: str | None = Query(None),
):
    """
    UI에서 Agent 실행 과정을 실시간으로 보기 위한 SSE endpoint.

    반환 이벤트 type:
    - start
    - input_masked
    - tool_call
    - tool_result
    - answer
    - done
    - error
    """

    session_id = session_id or str(uuid.uuid4())

    async def event_generator():
        limiter = CallLimitCallbackHandler(
            max_model_calls=int(MAX_MODEL_CALLS),
            max_tool_calls=int(MAX_TOOL_CALLS),
            max_total_calls=int(MAX_TOTAL_CALLS),
        )

        try:
            safe_question, input_summary = sanitize_text(question)

            yield sse({
                "type": "start",
                "session_id": session_id,
                "message": "Agent 실행을 시작합니다.",
            })

            if input_summary.get("masked"):
                yield sse({
                    "type": "input_masked",
                    "session_id": session_id,
                    "masked_question": safe_question,
                    "summary": input_summary,
                })

            final_answer = ""

            runtime_graph = await get_graph()

            async for update in runtime_graph.astream(
                {
                    "messages": [
                        HumanMessage(content=safe_question)
                    ]
                },
                config={
                    "configurable": {
                        "thread_id": session_id,
                    },
                    "callbacks": [
                        limiter,
                    ],
                    "recursion_limit": MAX_GRAPH_STEPS,
                },
                stream_mode="updates",
            ):
                for node_name, node_data in update.items():
                    messages = node_data.get("messages", [])

                    for msg in messages:
                        # 1) LLM이 Tool 호출을 결정한 경우
                        tool_calls = getattr(msg, "tool_calls", None)

                        if tool_calls:
                            for tool_call in tool_calls:
                                yield sse({
                                    "type": "tool_call",
                                    "node": node_name,
                                    "tool": tool_call.get("name", "unknown"),
                                    "args": tool_call.get("args", {}),
                                })

                        # 2) Tool 실행 결과
                        if isinstance(msg, ToolMessage):
                            content = _message_content_to_text(msg.content)

                            yield sse({
                                "type": "tool_result",
                                "node": node_name,
                                "tool": getattr(msg, "name", "unknown"),
                                "content": content,
                            })

                        # 3) StackOverflow fallback은 AIMessage로 들어오므로 별도 표시
                        elif node_name == "stackoverflow_fallback" and isinstance(msg, AIMessage):
                            content = _message_content_to_text(msg.content)

                            yield sse({
                                "type": "tool_result",
                                "node": node_name,
                                "tool": "stackoverflow_search",
                                "content": content,
                            })

                        # 4) 최종 답변
                        elif node_name in ["final_answer", "reasoning"] and isinstance(msg, AIMessage):
                            content = _message_content_to_text(msg.content)

                            if content.strip() and not tool_calls:
                                safe_answer, output_summary = sanitize_text(content)
                                final_answer = safe_answer

                                yield sse({
                                    "type": "answer",
                                    "session_id": session_id,
                                    "content": safe_answer,
                                    "output_sanitization": output_summary,
                                })

            counts = limiter.get_counts()

            yield sse({
                "type": "done",
                "session_id": session_id,
                "usage": {
                    "model_calls": counts["model_calls"],
                    "tool_calls": counts["tool_calls"],
                    "total_calls": counts["total_calls"],
                    "graph_recursion_limit": int(MAX_GRAPH_STEPS),
                },
                "answer": final_answer,
            })

        except CallLimitExceeded as e:
            logger.warning(f"SSE call limit exceeded: {str(e)}")

            yield sse({
                "type": "error",
                "error_type": "CallLimitExceeded",
                "message": "모델 또는 Tool 호출 횟수 제한을 초과했습니다.",
                "detail": str(e),
            })

        except Exception as e:
            logger.error(f"SSE agent stream error: {str(e)}", exc_info=True)

            yield sse({
                "type": "error",
                "error_type": "AgentStreamError",
                "message": str(e),
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )