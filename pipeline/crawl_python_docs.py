import os
import re
import time
import random
import hashlib
import requests

from pathlib import Path
from bs4 import BeautifulSoup
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from dotenv import load_dotenv

load_dotenv()


# 설정


TARGET_URLS = [
    "https://docs.python.org/ko/3/tutorial/",
    "https://docs.python.org/ko/3/whatsnew/",
    "https://docs.python.org/ko/3/library/",
    "https://docs.python.org/ko/3/reference/",
    "https://docs.python.org/ko/3/using/",
    "https://docs.python.org/ko/3/howto/",
    "https://docs.python.org/ko/3/installing/",
    "https://docs.python.org/ko/3/distributing/",
    "https://docs.python.org/ko/3/extending/",
    "https://docs.python.org/ko/3/c-api/",
    "https://docs.python.org/ko/3/faq/",
]

BASE_URL = os.getenv("DOCS_BASE_URL", "https://docs.python.org/ko/3/")
ROBOTS_URL = os.getenv("ROBOTS_URL", "https://docs.python.org/robots.txt")

SAVE_DIR = Path(os.getenv("RAW_DOCS_DIR", "/mnt/data/raw_docs"))

USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "PythonDebugAssistantCrawler/1.0"
)

REQUEST_DELAY_MIN = float(os.getenv("REQUEST_DELAY_MIN", "0.5"))
REQUEST_DELAY_MAX = float(os.getenv("REQUEST_DELAY_MAX", "1.0"))

# 하루 MVP용 안전장치
# 0이면 제한 없이 크롤링
MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", "300"))

EXCLUDE_EXTENSIONS = (
    ".pdf", ".zip", ".gz", ".tar", ".tgz",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".css", ".js", ".json", ".xml",
)

EXCLUDE_PATH_KEYWORDS = (
    "/_static/",
    "/_sources/",
    "/genindex",
    "/py-modindex",
    "/search",
)


# Session


session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT
})


# robots.txt


robot_parser = RobotFileParser()
robots_loaded = False

try:
    robot_parser.set_url(ROBOTS_URL)
    robot_parser.read()
    robots_loaded = True
    print(f"robots.txt 로드 완료: {ROBOTS_URL}")
except Exception as e:
    print(f"robots.txt 로드 실패: {e}")
    print("robots.txt 확인 실패 시에는 크롤링을 계속 진행합니다.")


def can_fetch(url: str) -> bool:
    """
    robots.txt 허용 여부 확인
    """
    if not robots_loaded:
        return True

    try:
        return robot_parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True



# URL 처리


def normalize_url(url: str) -> str | None:
    """
    URL 정규화:
    - fragment 제거
    - query 제거
    - docs.python.org 내부 URL만 유지
    """
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return None

        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            "",
            ""
        ))

        return normalized

    except Exception:
        return None


def is_valid_doc_url(url: str) -> bool:
    """
    Python 공식문서 한국어 v3 문서 URL인지 확인
    """
    if not url:
        return False

    if not url.startswith(BASE_URL):
        return False

    lower_url = url.lower()

    if lower_url.endswith(EXCLUDE_EXTENSIONS):
        return False

    if any(keyword in lower_url for keyword in EXCLUDE_PATH_KEYWORDS):
        return False

    return True



# 파일명 생성


def sanitize_filename(url: str) -> str:
    """
    URL을 안전한 파일명으로 변환
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")

    if not path:
        path = "index"

    filename = path.replace("/", "_")
    filename = filename.replace(".html", "")

    filename = re.sub(r"[^a-zA-Z0-9가-힣_.-]", "_", filename)

    # URL 충돌 방지를 위한 짧은 해시
    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]

    return f"{filename}_{url_hash}.txt"



# 페이지 요청


def get_page(url: str):
    """
    페이지 요청 후 BeautifulSoup 객체 반환
    """
    if not can_fetch(url):
        print(f"[SKIP] robots.txt 접근 금지: {url}")
        return None

    sleep_time = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    time.sleep(sleep_time)

    response = session.get(url, timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"

    content_type = response.headers.get("Content-Type", "")

    if "text/html" not in content_type:
        print(f"[SKIP] HTML 문서가 아님: {url}")
        return None

    return BeautifulSoup(response.text, "html.parser")



# 본문 / 제목 추출


def extract_title(soup: BeautifulSoup) -> str:
    """
    문서 제목 추출
    """
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)

    if soup.title:
        return soup.title.get_text(" ", strip=True)

    return "제목 없음"


def extract_text(soup: BeautifulSoup) -> str | None:
    """
    문서 본문 추출
    """
    body = (
        soup.find("div", class_="body")
        or soup.find("main")
        or soup.find("div", role="main")
        or soup.find("section")
        or soup.body
    )

    if not body:
        return None

    # 불필요한 태그 제거
    for tag in body.find_all([
        "script", "style", "nav", "header", "footer", "aside"
    ]):
        tag.decompose()

    text = body.get_text(separator="\n", strip=True)

    # 과도한 줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()



# 링크 추출


def get_links(soup: BeautifulSoup, current_url: str) -> set[str]:
    """
    현재 페이지에서 내부 링크 추출
    """
    links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]

        full_url = urljoin(current_url, href)
        full_url = normalize_url(full_url)

        if not is_valid_doc_url(full_url):
            continue

        if can_fetch(full_url):
            links.add(full_url)

    return links



# 저장


def save_text(url: str, title: str, text: str):
    """
    원본 문서를 txt로 저장.
    상단에 metadata header를 함께 저장해서
    build_chroma_db.py에서 source/title metadata로 활용한다.
    """
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    filename = sanitize_filename(url)
    filepath = SAVE_DIR / filename

    crawled_at = datetime.now(timezone.utc).isoformat()

    content = f"""SOURCE_URL: {url}
TITLE: {title}
CRAWLED_AT: {crawled_at}
---

{text}
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"저장 완료: {filepath.name} ({len(text):,}자)")



# 크롤링


def crawl():
    """
    BFS 방식으로 Python 공식문서 한국어 페이지를 크롤링한다.
    """
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    visited = set()
    queued = set()

    queue = deque()

    for url in TARGET_URLS:
        normalized = normalize_url(url)
        if normalized and is_valid_doc_url(normalized):
            queue.append(normalized)
            queued.add(normalized)

    saved_count = 0

    while queue:
        if MAX_PAGES > 0 and len(visited) >= MAX_PAGES:
            print(f"MAX_PAGES={MAX_PAGES}에 도달하여 크롤링을 종료합니다.")
            break

        url = queue.popleft()

        if url in visited:
            continue

        visited.add(url)

        print("=" * 70)
        print(f"[{len(visited)}] 크롤링: {url}")

        try:
            soup = get_page(url)

            if soup is None:
                continue

            title = extract_title(soup)
            text = extract_text(soup)

            if text:
                save_text(url, title, text)
                saved_count += 1
            else:
                print(f"본문 없음: {url}")

            links = get_links(soup, url)

            new_count = 0

            for link in links:
                if link not in visited and link not in queued:
                    queue.append(link)
                    queued.add(link)
                    new_count += 1

            print(f"새 링크: {new_count}")
            print(f"대기열: {len(queue)}")

        except requests.exceptions.RequestException as e:
            print(f"네트워크 오류: {url} / {e}")

        except Exception as e:
            print(f"오류: {url} / {type(e).__name__}: {e}")

    print("=" * 70)
    print("크롤링 완료")
    print(f"방문 URL 수: {len(visited)}")
    print(f"저장 문서 수: {saved_count}")
    print(f"저장 위치: {SAVE_DIR}")



# 실행


if __name__ == "__main__":
    print("=" * 70)
    print("Python Docs 한국어 문서 크롤링 시작")
    print("=" * 70)

    crawl()

    print("=" * 70)
    print("크롤링 작업 완료")
    print("=" * 70)