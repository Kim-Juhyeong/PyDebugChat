import os
import re
import time
import random
import requests

from bs4 import BeautifulSoup
from collections import deque
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser


# 설정

# 한국어 Python Docs 내부에서만 크롤링
BASE_URL = "https://docs.python.org/ko/3/"
# 크롤링 제한 확인용 robots.txt
ROBOTS_URL = "https://docs.python.org/robots.txt"
# 크롤링 시작 위치 urls
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
    "https://docs.python.org/ko/3/faq/"
]
# 크롤링 데이터 저장 위치
SAVE_DIR = "/mnt/data/raw_docs"

# Session 생성
session = requests.Session()
session.headers.update({
    "User-Agent": "PythonDocsCrawler/1.0"
})

# robots.txt 파싱
robot_parser = RobotFileParser()
try:
    robot_parser.set_url(ROBOTS_URL)
    robot_parser.read()
    print("robots.txt 로드 완료")
except Exception as e:
    print(f"robots.txt 로드 실패 : {e}")

# 크롤링 허용 여부 확인
def can_fetch(url):
    """
    robots.txt 허용 여부 확인
    """
    try:
        return robot_parser.can_fetch("PythonDocsCrawler/1.0", url)
    except Exception:
        return True

# 파일명 생성
def sanitize_filename(url):

    parsed = urlparse(url)

    path = parsed.path.strip("/")

    if path == "":
        path = "index"

    filename = path.replace("/", "_")
    filename = filename.replace(".html", "")

    filename = re.sub(r'[^a-zA-Z0-9가-힣_.-]', '_', filename)

    return filename + ".txt"

# 페이지 요청
def get_page(url):

    # robots.txt 확인
    if not can_fetch(url):
        print(f"[SKIP] robots.txt 접근 금지 : {url}")
        return None

    # 요청 속도 제한
    time.sleep(random.uniform(0.1, 0.5))

    response = session.get(url, timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"

    return BeautifulSoup(response.text, "html.parser")

# 본문 추출
def extract_text(soup):

    body = (
        soup.find("div", class_="body")
        or soup.find("div", role="main")
        or soup.find("section")
        or soup.body
    )

    if body:
        return body.get_text(separator="\n", strip=True)

    return None

# 링크 추출
def get_links(soup, current_url):

    links = set()

    for a in soup.find_all("a", href=True):

        href = a["href"]

        full_url = urljoin(current_url, href)

        # #section 제거
        full_url = full_url.split("#")[0]

        # 한국어 Python Docs만
        if not full_url.startswith(BASE_URL):
            continue

        # html 문서만
        if any(full_url.endswith(ext) for ext in [
            ".pdf",
            ".zip",
            ".gz",
            ".png",
            ".jpg",
            ".jpeg",
            ".svg",
            ".css",
            ".js",
            ".ico"
        ]):
            continue

        # robots.txt 확인
        if can_fetch(full_url):
            links.add(full_url)

    return links

# 저장
def save_text(url, text):

    filename = sanitize_filename(url)

    filepath = os.path.join(SAVE_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"저장 완료 : {filename} ({len(text):,}자)")

# 크롤링
def crawl():

    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    visited = set()

    queue = deque(TARGET_URLS)

    while queue:

        url = queue.popleft()

        if url in visited:
            continue

        visited.add(url)

        print("=" * 70)
        print(f"[{len(visited)}] {url}")

        try:

            soup = get_page(url)

            if soup is None:
                continue

            text = extract_text(soup)

            if text:
                save_text(url, text)

            links = get_links(soup, url)

            new_count = 0

            for link in links:

                if link not in visited:
                    queue.append(link)
                    new_count += 1

            print(f"새 링크 : {new_count}")
            print(f"대기열 : {len(queue)}")

        except requests.exceptions.RequestException as e:
            print(f"네트워크 오류 : {e}")

        except Exception as e:
            print(f"오류 : {e}")

    print("=" * 70)
    print(f"크롤링 완료")
    print(f"총 방문 페이지 : {len(visited)}")

# 실행
if __name__ == "__main__":

    print("=" * 70)
    print("Python Docs 한국어 문서 전체 크롤링 시작")
    print("=" * 70)

    crawl()

    print("=" * 70)
    print("모든 작업 완료")
    print("=" * 70)