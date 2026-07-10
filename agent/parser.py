from typing import List, Optional, Literal

from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser


# 레퍼런스 스키마
class Reference(BaseModel):
    """
    답변에 사용한 참고 근거 정보
    """

    title: str = Field(
        default="",
        description="참고 문서나 검색 결과 제목"
    )

    source: str = Field(
        default="",
        description="참고한 문서 URL, 파일명, 검색 결과 링크"
    )

    source_type: Literal[
        "python_docs",
        "stackoverflow",
        "web",
        "memory",
        "none"
    ] = Field(
        default="none",
        description="참고 출처 유형"
    )

# 최종 답변 스키마
class DebuggingAnswer(BaseModel):
    """
    Python Debug Assistant의 최종 답변 구조
    """

    answer_type: Literal[
        "general_chat",
        "python_concept",
        "python_error",
        "external_library_error",
        "web_info",
        "unknown"
    ] = Field(
        description="사용자 질문 유형"
    )

    summary: str = Field(
        description="핵심 요약. 사용자의 질문에 대한 짧은 답변"
    )

    cause: Optional[str] = Field(
        default="",
        description="에러나 문제가 발생한 원인. 일반 대화면 비워도 된다."
    )

    solution_steps: List[str] = Field(
        default_factory=list,
        description="해결 방법을 단계별로 정리한 목록"
    )

    code: Optional[str] = Field(
        default="",
        description="필요한 경우 제공할 예제 코드. 코드가 필요 없으면 빈 문자열"
    )

    references: List[Reference] = Field(
        default_factory=list,
        description="답변에 사용한 참고 근거 목록"
    )

    used_rag: bool = Field(
        default=False,
        description="Python 공식 문서 RAG를 사용했는지 여부"
    )

    used_stackoverflow: bool = Field(
        default=False,
        description="StackOverflow 검색을 사용했는지 여부"
    )

    used_web_search: bool = Field(
        default=False,
        description="일반 웹 검색을 사용했는지 여부"
    )

    safety_note: Optional[str] = Field(
        default="",
        description="개인정보 마스킹, 보안상 주의사항 등이 있으면 작성"
    )

debugging_answer_parser = PydanticOutputParser(
    pydantic_object=DebuggingAnswer
)

def get_format_instructions() -> str:
    """
    LLM에게 전달할 JSON 출력 형식 안내문을 반환한다.
    """
    return debugging_answer_parser.get_format_instructions()

def parse_debugging_answer(text: str) -> DebuggingAnswer:
    """
    LLM이 생성한 JSON 문자열을 DebuggingAnswer 객체로 파싱한다.
    """
    return debugging_answer_parser.parse(text)

# Fallback Parser
def safe_parse_debugging_answer(text: str) -> DebuggingAnswer:
    """
    파싱 실패 시에도 서버가 죽지 않도록 기본 구조로 감싸서 반환한다.
    """
    try:
        return parse_debugging_answer(text)

    except Exception:
        return DebuggingAnswer(
            answer_type="unknown",
            summary=text.strip() if text else "답변을 생성하지 못했습니다.",
            cause="",
            solution_steps=[],
            code="",
            references=[],
            used_rag=False,
            used_stackoverflow=False,
            used_web_search=False,
            safety_note="응답 구조화 파싱에 실패하여 원문 답변을 반환했습니다."
        )



# Markdown Renderer
def render_debugging_answer(answer: DebuggingAnswer) -> str:
    """
    DebuggingAnswer 객체를 사용자에게 보여줄 Markdown 문자열로 변환한다.
    """

    # 일반 채팅은 너무 딱딱한 형식으로 만들지 않음
    if answer.answer_type == "general_chat":
        return answer.summary.strip()

    parts = []

    
    # 1. 핵심 요약
    if answer.summary:
        parts.append("## 핵심 요약")
        parts.append(answer.summary.strip())
   
    # 2. 원인   
    if answer.cause:
        parts.append("\n## 원인")
        parts.append(answer.cause.strip())

    # 3. 해결 방법    
    if answer.solution_steps:
        parts.append("\n## 해결 방법")

        for i, step in enumerate(answer.solution_steps, 1):
            parts.append(f"{i}. {step}")

    
    # 4. 예제 코드   
    if answer.code:
        parts.append("\n## 예제 코드")
        parts.append("```python")
        parts.append(answer.code.strip())
        parts.append("```")

    
    # 5. 참고   
    reference_lines = []

    if answer.used_rag:
        reference_lines.append("- Python 공식 문서 기반 RAG 검색 결과를 참고했습니다.")

    if answer.used_stackoverflow:
        reference_lines.append("- 공식 문서 검색 결과가 부족하거나 실무 사례가 필요해 StackOverflow 결과를 보완 참고했습니다.")

    if answer.used_web_search:
        reference_lines.append("- 일반 웹 검색 결과를 참고했습니다.")

    if answer.references:
        for ref in answer.references:
            title = ref.title or "참고 자료"
            source = ref.source or ""
            source_type = ref.source_type

            if source:
                reference_lines.append(f"- [{source_type}] {title}: {source}")
            else:
                reference_lines.append(f"- [{source_type}] {title}")

    if reference_lines:
        parts.append("\n## 참고")
        parts.extend(reference_lines)

    
    # 6. 안전 안내    
    if answer.safety_note:
        parts.append("\n## 안내")
        parts.append(answer.safety_note.strip())

    return "\n".join(parts).strip()