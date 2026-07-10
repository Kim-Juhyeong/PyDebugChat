from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="대화 세션 ID. 없으면 서버에서 새로 생성합니다.",
    )

    message: str = Field(
        ...,
        min_length=1,
        max_length=12000,
        description="사용자 입력 메시지",
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("message는 비어 있을 수 없습니다.")

        return value


class SanitizationInfo(BaseModel):
    masked: bool = False
    pii_detected: bool = False
    pii_types: List[str] = []
    pii_counts: Dict[str, int] = {}
    profanity_detected: bool = False
    profanity_count: int = 0


class UsageInfo(BaseModel):
    model_calls: int = 0
    tool_calls: int = 0
    total_calls: int = 0
    graph_recursion_limit: int = 0
    elapsed_ms: float = 0.0


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    masked_input: str
    input_sanitization: SanitizationInfo
    output_sanitization: SanitizationInfo
    usage: UsageInfo


class HealthResponse(BaseModel):
    status: str
    service: str
    chroma_db_dir: str
    chat_history_db: str


class GraphResponse(BaseModel):
    mermaid: str


class ErrorResponse(BaseModel):
    error_type: str
    message: str
    detail: Optional[Any] = None