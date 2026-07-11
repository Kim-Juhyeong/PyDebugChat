# ai

import re
import json
import time
import logging

from typing import Any, Dict, Tuple
from logging.handlers import RotatingFileHandler

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from langchain_core.callbacks import BaseCallbackHandler

from app.config import LOG_DIR, MAX_REQUEST_BYTES, MAX_UPLOAD_BYTES


# 환경변수
LOG_FILE = LOG_DIR / "chatbot.log"


# 로깅
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler(
            str(LOG_FILE),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("debugging_agent")



# 호출 제한 예외
class CallLimitExceeded(RuntimeError):
    pass



# 모델 / Tool 호출 횟수 제한 Callback
class CallLimitCallbackHandler(BaseCallbackHandler):
    """
    LangChain / LangGraph 실행 중 모델 호출과 Tool 호출 횟수를 제한한다.

    server.py에서 graph.invoke(..., config={"callbacks": [handler]}) 형태로 사용한다.
    """

    def __init__(
        self,
        max_model_calls: int = 3,
        max_tool_calls: int = 5,
        max_total_calls: int = 8,
    ):
        self.max_model_calls = max_model_calls
        self.max_tool_calls = max_tool_calls
        self.max_total_calls = max_total_calls

        self.model_calls = 0
        self.tool_calls = 0

    def _check_limit(self):
        total = self.model_calls + self.tool_calls

        if self.model_calls > self.max_model_calls:
            raise CallLimitExceeded(
                f"모델 호출 횟수 제한 초과: {self.model_calls}/{self.max_model_calls}"
            )

        if self.tool_calls > self.max_tool_calls:
            raise CallLimitExceeded(
                f"Tool 호출 횟수 제한 초과: {self.tool_calls}/{self.max_tool_calls}"
            )

        if total > self.max_total_calls:
            raise CallLimitExceeded(
                f"전체 호출 횟수 제한 초과: {total}/{self.max_total_calls}"
            )

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.model_calls += 1
        self._check_limit()

    def on_llm_start(self, serialized, prompts, **kwargs):
        self.model_calls += 1
        self._check_limit()

    def on_tool_start(self, serialized, input_str, **kwargs):
        self.tool_calls += 1
        self._check_limit()

    def get_counts(self) -> Dict[str, int]:
        return {
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "total_calls": self.model_calls + self.tool_calls,
        }



# 개인정보 / 욕설 마스킹
PII_PATTERNS = [
    (
        "resident_registration_number",
        re.compile(r"\b\d{6}[-\s]?[1-4]\d{6}\b"),
        "[RRN]",
    ),
    (
        "email",
        re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
        "[EMAIL]",
    ),
    (
        "korean_phone",
        re.compile(r"\b01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}\b"),
        "[PHONE]",
    ),
    (
        "phone",
        re.compile(r"\b\d{2,4}[-.\s]\d{3,4}[-.\s]\d{4}\b"),
        "[PHONE]",
    ),
    (
        "credit_card",
        re.compile(r"(?<!\d)(?:\d[ -]?){13,16}(?!\d)"),
        "[CARD]",
    ),
    (
        "ipv4",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
        ),
        "[IP]",
    ),
    (
        "openai_api_key",
        re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
        "[API_KEY]",
    ),
]

SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token)\b\s*[:=]\s*[\"']?([^\s\"']+)"
)

PROFANITY_WORDS = [
    "씨발",
    "시발",
    "ㅅㅂ",
    "ㅆㅂ",
    "병신",
    "ㅂㅅ",
    "개새끼",
    "새끼",
    "지랄",
    "ㅈㄹ",
    "좆",
    "좃",
    "ㅈ같",
    "엿같",
    "꺼져",
    "미친놈",
    "미친년",
    "염병",
]

PROFANITY_PATTERN = re.compile(
    "|".join(re.escape(word) for word in PROFANITY_WORDS),
    re.IGNORECASE,
)


def _empty_summary() -> Dict[str, Any]:
    return {
        "masked": False,
        "pii_detected": False,
        "pii_types": [],
        "pii_counts": {},
        "profanity_detected": False,
        "profanity_count": 0,
    }


def _merge_summary(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    base["masked"] = base["masked"] or other.get("masked", False)
    base["pii_detected"] = base["pii_detected"] or other.get("pii_detected", False)
    base["profanity_detected"] = base["profanity_detected"] or other.get("profanity_detected", False)
    base["profanity_count"] += other.get("profanity_count", 0)

    for pii_type in other.get("pii_types", []):
        if pii_type not in base["pii_types"]:
            base["pii_types"].append(pii_type)

    for key, value in other.get("pii_counts", {}).items():
        base["pii_counts"][key] = base["pii_counts"].get(key, 0) + value

    return base


def sanitize_text(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    문자열에서 개인정보와 욕설을 마스킹한다.
    """
    summary = _empty_summary()
    sanitized = text

    def secret_replacer(match):
        summary["masked"] = True
        summary["pii_detected"] = True
        summary["pii_counts"]["secret"] = summary["pii_counts"].get("secret", 0) + 1

        if "secret" not in summary["pii_types"]:
            summary["pii_types"].append("secret")

        key = match.group(1)
        return f"{key}=[SECRET]"

    sanitized = SECRET_PATTERN.sub(secret_replacer, sanitized)

    for pii_type, pattern, placeholder in PII_PATTERNS:
        sanitized, count = pattern.subn(placeholder, sanitized)

        if count > 0:
            summary["masked"] = True
            summary["pii_detected"] = True
            summary["pii_counts"][pii_type] = summary["pii_counts"].get(pii_type, 0) + count

            if pii_type not in summary["pii_types"]:
                summary["pii_types"].append(pii_type)

    sanitized, profanity_count = PROFANITY_PATTERN.subn("[욕설]", sanitized)

    if profanity_count > 0:
        summary["masked"] = True
        summary["profanity_detected"] = True
        summary["profanity_count"] = profanity_count

    return sanitized, summary


def sanitize_payload(payload: Any) -> Tuple[Any, Dict[str, Any]]:
    """
    JSON payload 내부의 모든 문자열을 재귀적으로 마스킹한다.
    """
    summary = _empty_summary()

    if isinstance(payload, str):
        return sanitize_text(payload)

    if isinstance(payload, list):
        sanitized_list = []

        for item in payload:
            sanitized_item, item_summary = sanitize_payload(item)
            sanitized_list.append(sanitized_item)
            _merge_summary(summary, item_summary)

        return sanitized_list, summary

    if isinstance(payload, dict):
        sanitized_dict = {}

        for key, value in payload.items():
            sanitized_value, value_summary = sanitize_payload(value)
            sanitized_dict[key] = sanitized_value
            _merge_summary(summary, value_summary)

        return sanitized_dict, summary

    return payload, summary



# 요청 Body 교체


async def _replace_request_body(request: Request, body: bytes):
    async def receive():
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    request._receive = receive



# FastAPI Middleware


class ChatSafetyMiddleware(BaseHTTPMiddleware):
    """
    채팅 서비스용 Middleware.

    기능:
    - 요청 로깅
    - 응답 시간 측정
    - 개인정보 탐지/마스킹
    - 욕설 탐지/마스킹
    - 요청 크기 제한
    - 예외 처리
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/static") or request.url.path in ["/", "/favicon.ico"]:
            return await call_next(request)

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"

        try:
            content_length = int(request.headers.get("content-length", "0"))

            request_limit = (
                MAX_UPLOAD_BYTES + 1024 * 1024
                if request.url.path == "/api/projects" and request.method.upper() == "POST"
                else MAX_REQUEST_BYTES
            )

            if content_length > request_limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error_type": "RequestTooLarge",
                        "message": f"요청 크기가 너무 큽니다. 최대 {request_limit} bytes까지 허용됩니다.",
                    },
                )

            logger.info(f"[{client_ip}] Request started: {request.method} {request.url.path}")

            request.state.sanitization = _empty_summary()

            if request.url.path == "/chat" and request.method.upper() == "POST":
                raw_body = await request.body()

                if raw_body:
                    try:
                        payload = json.loads(raw_body.decode("utf-8"))
                        sanitized_payload, summary = sanitize_payload(payload)

                        request.state.sanitization = summary

                        sanitized_body = json.dumps(
                            sanitized_payload,
                            ensure_ascii=False,
                        ).encode("utf-8")

                        await _replace_request_body(request, sanitized_body)

                        if summary["masked"]:
                            logger.info(
                                f"[{client_ip}] Input masked. "
                                f"pii={summary['pii_types']}, "
                                f"profanity={summary['profanity_count']}"
                            )

                    except json.JSONDecodeError:
                        await _replace_request_body(request, raw_body)

            response = await call_next(request)

            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Process-Time-ms"] = str(elapsed_ms)

            logger.info(
                f"[{client_ip}] Request finished: "
                f"{request.method} {request.url.path} "
                f"status={response.status_code} "
                f"elapsed_ms={elapsed_ms}"
            )

            return response

        except Exception as e:
            logger.error(f"[{client_ip}] Middleware error: {str(e)}", exc_info=True)

            return JSONResponse(
                status_code=500,
                content={
                    "error_type": "MiddlewareError",
                    "message": "요청 처리 중 서버 오류가 발생했습니다.",
                },
            )
