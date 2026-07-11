import html
import re
import requests

from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from app.config import CHROMA_DB_DIR, COLLECTION_NAME, EMBEDDING_MODEL
from app.projects import search_project_code

# 환경변수
ERROR_SCORE_THRESHOLD = 1.0

# ChromaDB 설정
embedding_model = OpenAIEmbeddings(
    model=EMBEDDING_MODEL
)

# ChromaDB 인스턴스 생성
vectorstore = Chroma(
    persist_directory=str(CHROMA_DB_DIR),
    embedding_function=embedding_model,
    collection_name=COLLECTION_NAME,
)

# Tavily 설정
_tavily_tool = TavilySearch(max_results=3)

# 공통 함수
def _format_doc(doc, index: int, score: float | None = None) -> str:
    """
    ChromaDB 검색 결과를 LLM이 읽기 좋은 형태로 변환
    """
    metadata = doc.metadata or {}

    title = metadata.get("title", "제목 없음")
    source = metadata.get("source", "출처 없음")
    section = metadata.get("section", "")
    content = doc.page_content.strip()

    score_text = ""
    if score is not None:
        score_text = f"\n관련도 거리: {score:.4f}"

    return f"""
[문서 {index}]
제목: {title}
섹션: {section}
출처: {source}{score_text}

내용:
{content}
""".strip()

# 검색 오류 메시지 처리
def _safe_search_error_message(e: Exception) -> str:
    return f"검색 중 오류가 발생했습니다: {type(e).__name__}: {str(e)}"


_EXCEPTION_NAME_PATTERN = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Warning))\b"
)


def _build_error_search_query(query: str) -> tuple[str, set[str]]:
    """긴 코드 전체보다 Exception 이름과 Traceback 핵심 줄을 우선 검색한다."""
    exception_names = {
        match.group(1)
        for match in _EXCEPTION_NAME_PATTERN.finditer(query)
    }
    lines = [line.strip() for line in query.splitlines() if line.strip()]
    important_lines = [
        line
        for line in lines
        if (
            "traceback" in line.lower()
            or any(name.lower() in line.lower() for name in exception_names)
        )
    ]

    if not important_lines:
        important_lines = lines[-8:]

    terms = " ".join(sorted(exception_names))
    core = "\n".join(important_lines[-8:])
    search_query = f"Python {terms} exception traceback {core}".strip()
    return search_query[:2000], {name.lower() for name in exception_names}


def _is_relevant_error_doc(doc, score: float, exception_names: set[str]) -> bool:
    """정확한 Exception 이름이 있거나 벡터 거리가 합리적이면 관련 문서로 본다."""
    metadata = doc.metadata or {}
    searchable = " ".join(
        [
            str(metadata.get("title", "")),
            str(metadata.get("section", "")),
            doc.page_content,
        ]
    ).lower()

    if exception_names and any(name in searchable for name in exception_names):
        return True

    return score <= ERROR_SCORE_THRESHOLD

# Tool 1. Python 공식문서 RAG 검색
@tool
def python_docs_search(query: str) -> str:
    """
    Python 공식 문서에서 Python 문법, 표준 라이브러리, 내장 함수, 언어 기능 정보를 검색합니다.

    이 도구는 Python 자체에 대한 공식적이고 정확한 설명이 필요할 때 사용합니다.

    반드시 다음과 같은 경우에 사용하세요.

    - Python 문법 설명
    - Python 내장 함수 사용법
    - Python 표준 라이브러리 사용법
    - 함수 / 클래스 사용법
    - typing
    - pathlib
    - asyncio
    - threading
    - multiprocessing
    - dataclass
    - iterator
    - generator
    - decorator
    - context manager
    - list comprehension
    - dictionary
    - set
    - tuple
    - with 문
    - yield
    - enumerate
    - zip
    - collections
    - itertools
    - functools

    사용 예시:

    - "dataclass 사용법 알려줘"
    - "asyncio.gather는 어떻게 동작해?"
    - "pathlib Path 사용법"
    - "yield와 generator 차이"
    - "with 문과 context manager 설명"

    사용하면 안 되는 경우:

    - 구체적인 에러 로그나 Traceback 해결
    - FastAPI, Django, Pandas 같은 외부 라이브러리 실무 문제
    - 최신 뉴스나 일반 웹 정보

    Args:
        query: Python 공식 문서에서 검색할 질문

    Returns:
        Python 공식 문서 기반 검색 결과
    """
    try:
        docs = vectorstore.max_marginal_relevance_search(
            query,
            k=5,
            fetch_k=20,
        )

        if not docs:
            return "[SEARCH_STATUS]: INSUFFICIENT\n관련된 Python 공식 문서를 찾지 못했습니다."

        results = [
            _format_doc(doc, index=i)
            for i, doc in enumerate(docs, 1)
        ]

        return "[SEARCH_STATUS]: SUFFICIENT\n\n" + "\n\n---\n\n".join(results)

    except Exception as e:
        return f"[SEARCH_STATUS]: INSUFFICIENT\n{_safe_search_error_message(e)}"

# Tool 2. Python 에러 전용 RAG 검색
@tool
def python_error_search(query: str) -> str:
    """
    Python 에러 메시지, Exception, Traceback을 Python 공식 문서에서 검색합니다.

    Python 실행 중 발생한 에러의 의미, 원인, 관련 Exception 정보를
    공식 문서 기준으로 확인할 때 사용합니다.

    반드시 다음과 같은 경우에 사용하세요.

    - TypeError
    - ValueError
    - AttributeError
    - ImportError
    - ModuleNotFoundError
    - NameError
    - KeyError
    - IndexError
    - RuntimeError
    - ZeroDivisionError
    - FileNotFoundError
    - RecursionError
    - SyntaxError
    - IndentationError
    - Traceback
    - Python 에러 로그
    - Python 디버깅 질문

    사용 예시:

    - "TypeError: 'int' object is not iterable"
    - "ModuleNotFoundError: No module named numpy"
    - "ImportError: cannot import name"
    - "AttributeError: 'list' object has no attribute"
    - "SyntaxError: invalid syntax"
    - "IndentationError: unexpected indent"

    가능하면 사용자가 입력한 에러 메시지나 Traceback을 그대로 query에 넣으세요.

    검색 결과가 충분하지 않으면 반환값에
    [SEARCH_STATUS]: INSUFFICIENT
    가 포함됩니다. 이 경우 graph.py에서 자동으로 stackoverflow_search를 추가 호출합니다.

    Args:
        query: Python 에러 메시지 또는 Traceback

    Returns:
        Python 공식 문서 기반 Exception 검색 결과와 충분성 상태
    """
    search_query, exception_names = _build_error_search_query(query)

    try:
        # k=8로 검색
        docs_with_scores = vectorstore.similarity_search_with_score(
            search_query,
            k=8,
        )

        if not docs_with_scores:
            return f"""
            [SEARCH_STATUS]: INSUFFICIENT
            [SEARCH_TOOL]: python_error_search
            [QUERY]: {query}
            
            Python 공식 문서에서 관련 에러 정보를 찾지 못했습니다.
            """.strip()

        # 관련도 기준을 통과한 문서 필터링
        filtered = [
            (doc, score)
            for doc, score in docs_with_scores
            if _is_relevant_error_doc(doc, score, exception_names)
        ]

        if not filtered:
            status = "INSUFFICIENT"
            reason = (
                "Exception 이름이 일치하거나 관련도 기준을 통과한 "
                "공식 문서를 찾지 못했습니다."
            )

            fallback_docs = docs_with_scores[:3]

            results = [
                _format_doc(doc, index=i, score=score)
                for i, (doc, score) in enumerate(fallback_docs, 1)
            ]

        else:
            status = "SUFFICIENT"
            reason = (
                f"Python 공식 문서에서 관련 문서 {len(filtered)}개를 찾았습니다. "
                "공식 문서를 우선 근거로 사용합니다."
            )

            results = [
                _format_doc(doc, index=i, score=score)
                for i, (doc, score) in enumerate(filtered[:5], 1)
            ]

        return f"""
[SEARCH_STATUS]: {status}
[SEARCH_TOOL]: python_error_search
[QUERY]: {query}
[REASON]: {reason}

{chr(10).join(results)}
""".strip()

    except Exception as e:
        return f"""
[SEARCH_STATUS]: ERROR
[SEARCH_TOOL]: python_error_search
[QUERY]: {query}

{_safe_search_error_message(e)}
""".strip()

# Tool 3. StackOverflow 검색
@tool
def stackoverflow_search(query: str) -> str:
    """
    Stack Overflow에서 Python 관련 질문과 해결 사례를 검색합니다.

    공식 문서보다 실제 개발자의 경험, 실무 해결책, 라이브러리별 오류 사례가
    더 필요한 경우 사용합니다.

    반드시 다음과 같은 경우에 사용하세요.

    - python_error_search 결과가 부족한 경우
    - 공식 문서만으로 해결하기 어려운 Python 에러
    - FastAPI
    - Django
    - Flask
    - Pandas
    - NumPy
    - SQLAlchemy
    - TensorFlow
    - PyTorch
    - Selenium
    - OpenCV
    - pytest
    - pip 문제
    - 가상환경 문제
    - VSCode 문제
    - Docker 환경 문제
    - 외부 라이브러리 버그
    - 실무 사례가 필요한 디버깅 질문

    사용 예시:

    - "FastAPI dependency injection error"
    - "Pandas merge duplicate columns"
    - "Selenium timeout exception"
    - "pip SSL certificate error"
    - "PyTorch CUDA out of memory"
    - "ModuleNotFoundError in virtualenv"

    검색어는 가능하면 영어가 좋습니다.

    Args:
        query: Stack Overflow에서 검색할 에러 메시지 또는 질문

    Returns:
        Stack Overflow 검색 결과
    """
    url = "https://api.stackexchange.com/2.3/search/advanced"

    params = {
        "order": "desc",
        "sort": "relevance",
        "q": query,
        "site": "stackoverflow",
        "tagged": "python",
        "answers": 1,
        "pagesize": 5,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        if not items:
            return f"'{query}'에 대한 Stack Overflow 검색 결과가 없습니다."

        result = f"'{query}'에 대한 Stack Overflow 검색 결과입니다:\n\n"

        for i, item in enumerate(items, 1):
            title = html.unescape(item.get("title", "제목 없음"))
            link = item.get("link", "")
            score = item.get("score", 0)
            answer_count = item.get("answer_count", 0)
            is_answered = "해결됨" if item.get("is_answered") else "답변 있음"

            result += f"{i}. {title} [{is_answered}]\n"
            result += f"   점수: {score}, 답변 수: {answer_count}\n"
            result += f"   링크: {link}\n\n"

        return result.strip()

    except requests.exceptions.Timeout:
        return "Stack Overflow API 요청이 시간 초과되었습니다."

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code

        if status_code == 429:
            return "Stack Overflow API 호출 한도를 초과했습니다."

        return f"Stack Overflow API 오류 HTTP {status_code}"

    except requests.exceptions.RequestException as e:
        return f"Stack Overflow 서버 연결 오류: {str(e)}"

    except Exception as e:
        return f"Stack Overflow 검색 중 알 수 없는 오류 발생: {str(e)}"

# Tool 4. 일반 웹 검색
@tool
def web_search(query: str) -> str:
    """
    Tavily를 사용해 인터넷 검색을 수행합니다.

    Python 공식 문서, Python 에러, Stack Overflow 사례 검색과 관련 없는
    일반적인 정보성 질문에 사용합니다.

    반드시 다음과 같은 경우에 사용하세요.

    - Python 디버깅과 관련 없는 일반 질문
    - 최신 정보
    - 뉴스
    - 기업 정보
    - 제품 비교
    - 여행 정보
    - 맛집 추천
    - 최근 기술 동향
    - 공식 문서나 Stack Overflow보다 웹 검색이 적절한 질문

    사용하면 안 되는 경우:

    - Python 공식 문법 설명
    - Python 표준 라이브러리 설명
    - Python Exception / Traceback / 에러 로그
    - Python 디버깅 질문

    Args:
        query: 웹에서 검색할 질문

    Returns:
        Tavily 웹 검색 결과
    """
    try:
        return str(_tavily_tool.invoke({"query": query}))
    except Exception as e:
        return f"웹 {_safe_search_error_message(e)}"


@tool
def project_code_search(project_id: str, query: str) -> str:
    """
    현재 업로드된 프로젝트 전체에서 관련 코드와 오류 위치를 검색합니다.

    시스템 메시지에 ACTIVE_PROJECT_ID가 있을 때만 사용합니다. 현재 열린 파일 외의
    함수, 클래스, 설정, import 관계를 찾아야 할 때 해당 project_id를 그대로 전달합니다.

    Args:
        project_id: 시스템 메시지에 제공된 활성 프로젝트 ID
        query: 찾을 함수명, 클래스명, 오류 메시지 또는 코드 특징
    """
    try:
        matches = search_project_code(project_id, query)
    except FileNotFoundError:
        return "[PROJECT_SEARCH_STATUS]: NOT_FOUND\n프로젝트를 찾을 수 없습니다."

    if not matches:
        return "[PROJECT_SEARCH_STATUS]: NO_MATCH\n관련 코드를 찾지 못했습니다."

    sections = ["[PROJECT_SEARCH_STATUS]: FOUND"]
    for index, match in enumerate(matches, 1):
        sections.append(
            f"[{index}] {match['path']}:{match['line']}\n{match['snippet']}"
        )
    return "\n\n".join(sections)

# Agent Tool 목록
tools = [
    project_code_search,
    python_docs_search,
    python_error_search,
    stackoverflow_search,
    web_search,
]
