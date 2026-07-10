# FastAPI 앱 실행 진입점


import os
import sqlite3
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid

# 프로젝트 내부 모듈 가져오기
from agent.graph import graph
from app.middleware import AuthAndLoggingMiddleware

app = FastAPI(title="Python Debugging Assistant API")

# 1. 미들웨어 등록 (로깅, 예외처리, 속도 제한)
app.add_middleware(AuthAndLoggingMiddleware)

# 2. 정적 파일 마운트 (HTML/CSS/JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 요청 스키마 정의
class QueryRequest(BaseModel):
    question: str
    session_id: str = "default_session"

@app.post("/api/debug")
async def debug_query(request: QueryRequest):
    """
    사용자의 질문을 받아 LangGraph 에이전트로 전달하고 JSON 응답을 반환합니다.
    """
    config = {"configurable": {"thread_id": request.session_id}}
    
    # LangGraph 실행 (입력은 messages 형태)
    input_state = {"messages": [{"role": "user", "content": request.question}]}
    
    # 결과 호출
    result = graph.invoke(input_state, config=config)
    
    # 마지막 AI 메시지 추출
    last_message = result["messages"][-1]
    
    return {
        "success": True,
        "answer": last_message.content,
        "session_id": request.session_id
    }

# 루트 경로에서 정적 페이지 제공
@app.get("/")
async def root():
    return {"message": "에이전트 서버가 실행 중입니다. /static/index.html을 확인하세요."}

@app.get("/api/sessions")
def get_sessions():
    """저장된 모든 세션 ID(thread_id) 목록을 가져옵니다."""
    try:
        conn = sqlite3.connect("chat_history.db", check_same_thread=False)
        cursor = conn.cursor()
        # SqliteSaver가 생성하는 'threads' 테이블에서 thread_id 조회
        cursor.execute("SELECT thread_id FROM threads")
        sessions = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {"sessions": sessions}
    except Exception as e:
        return {"sessions": ["default_session"]} # DB가 없으면 기본값 반환

@app.get("/api/history/{session_id}")
async def get_history(session_id: str):
    """특정 세션의 대화 내역을 조회합니다."""
    try:
        config = {"configurable": {"thread_id": session_id}}
        # LangGraph의 현재 상태를 스냅샷으로 가져옵니다.
        state = graph.get_state(config)
        
        # 상태가 존재하고 messages 채널에 데이터가 있다면 반환
        messages = state.values.get("messages", [])
        
        # 메시지 객체들을 JSON 직렬화 가능한 형태로 변환
        serialized_messages = []
        for msg in messages:
            serialized_messages.append({
                "type": msg.__class__.__name__, # HumanMessage, AIMessage 등
                "content": msg.content
            })
            
        return {"messages": serialized_messages}
    except Exception as e:
        return {"messages": []}

@app.post("/api/debug")
async def debug_query(request: QueryRequest):
    # 이제 request.session_id는 프론트에서 선택한 값이 들어옵니다.
    config = {"configurable": {"thread_id": request.session_id}}
    input_state = {"messages": [{"role": "user", "content": request.question}]}
    result = graph.invoke(input_state, config=config)
    last_message = result["messages"][-1]
    
    return {
        "success": True,
        "answer": last_message.content,
        "session_id": request.session_id
    }