import os
import re
import shutil

from pathlib import Path
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

load_dotenv()


# 설정

# 저장 디렉토리
RAW_DATA_DIR = Path("/mnt/data/raw_docs")
CHROMA_DB_DIR = Path("/mnt/data/chroma_db")
PROCESSED_DATA_DIR = Path("/mnt/data/processed_docs")
# 컬렉션 이름
COLLECTION_NAME = "python_docs_collection"
# 임베딩 모델 및 배치 사이즈
EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 64
# 청크 분할 설정
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
# true면 기존 ChromaDB 삭제 후 재생성
RESET_CHROMA_DB = True



# 텍스트 처리
def clean_text(text: str) -> str:
    """
    기본 텍스트 정제
    """
    # 개행문자 통일
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 불필요한 공백 정리
    text = re.sub(r"[ \t]+", " ", text)

    # 과도한 줄바꿈 정리
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

# metadata 파싱
def parse_metadata_header(raw_text: str) -> tuple[dict, str]:
    """
    crawl_python_docs.py에서 저장한 metadata header를 파싱한다.

    형식:
    SOURCE_URL: ...
    TITLE: ...
    CRAWLED_AT: ...
    ---
    본문
    """
    metadata = {}

    if "\n---\n" not in raw_text:
        return metadata, raw_text

    header, body = raw_text.split("\n---\n", 1)

    for line in header.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "source_url":
            metadata["source"] = value
            metadata["source_url"] = value
        elif key == "title":
            metadata["title"] = value
        elif key == "crawled_at":
            metadata["crawled_at"] = value
        else:
            metadata[key] = value

    return metadata, body

# 원시 데이터 로드 및 가공
def load_raw_documents() -> list[Document]:
    """
    /mnt/data/raw_docs 아래 txt 파일들을 읽어 LangChain Document로 변환한다.
    """
    if not RAW_DATA_DIR.exists():
        print(f"RAW_DATA_DIR가 없습니다: {RAW_DATA_DIR}")
        return []

    txt_files = sorted(RAW_DATA_DIR.glob("*.txt"))

    if not txt_files:
        print(f"처리할 txt 파일이 없습니다: {RAW_DATA_DIR}")
        return []

    documents = []

    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for file_path in txt_files:
        try:
            raw_text = file_path.read_text(encoding="utf-8")
            # metadata 파싱
            metadata, body = parse_metadata_header(raw_text)
            # 텍스트 정제
            cleaned = clean_text(body)

            if not cleaned:
                continue

            # metadata 공통정보 설정
            metadata.setdefault("source", str(file_path))
            metadata.setdefault("source_url", metadata["source"])
            metadata.setdefault("title", file_path.stem)

            metadata["raw_file_path"] = str(file_path)
            metadata["file_name"] = file_path.name

            # 가공된 텍스트도 저장
            processed_path = PROCESSED_DATA_DIR / file_path.name
            processed_path.write_text(cleaned, encoding="utf-8")

            documents.append(
                Document(
                    page_content=cleaned,
                    metadata=metadata,
                )
            )

        except Exception as e:
            print(f"[SKIP] 파일 처리 실패: {file_path} / {type(e).__name__}: {e}")

    return documents

# 기존 ChromaDB 삭제
def reset_chroma_db():
    """
    기존 ChromaDB 삭제
    """
    if RESET_CHROMA_DB and CHROMA_DB_DIR.exists():
        print(f"기존 ChromaDB 삭제: {CHROMA_DB_DIR}")
        shutil.rmtree(CHROMA_DB_DIR)

    CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)

# 청크 분할
def split_documents(documents: list[Document]) -> list[Document]:
    """
    문서를 청크 단위로 분할
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
            "",
        ],
    )

    chunks = text_splitter.split_documents(documents)

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_id"] = i

    return chunks

# 임베딩 생성 및 ChromaDB 저장
def build_vector_db(chunks: list[Document]):
    """
    OpenAI Embedding을 생성하고 ChromaDB에 저장
    """
    # 임베딩 모델 초기화
    embedding_model = OpenAIEmbeddings(
        model=EMBEDDING_MODEL
    )

    # ChromaDB 인스턴스 생성
    vectorstore = Chroma(
        persist_directory=str(CHROMA_DB_DIR),
        embedding_function=embedding_model,
        collection_name=COLLECTION_NAME,
    )

    total = len(chunks)

    # 배치 단위로 임베딩 생성 및 저장
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        batch = chunks[start:end]

        print(f"임베딩 저장 중: {start + 1} ~ {end} / {total}")

        # ChromaDB 저장
        vectorstore.add_documents(batch)

    if hasattr(vectorstore, "persist"):
        vectorstore.persist()

    return vectorstore

# 실행 함수
def process_and_store_data():

    print(f"RAW_DATA_DIR: {RAW_DATA_DIR}")
    print(f"PROCESSED_DATA_DIR: {PROCESSED_DATA_DIR}")
    print(f"CHROMA_DB_DIR: {CHROMA_DB_DIR}")
    print(f"COLLECTION_NAME: {COLLECTION_NAME}")

    # 원본 문서 로드
    documents = load_raw_documents()

    if not documents:
        print("처리할 문서가 없습니다. 먼저 crawl_python_docs.py를 실행하세요.")
        return

    print(f"로드된 원본 문서 수: {len(documents)}")

    # 문서 청크 분할
    chunks = split_documents(documents)

    if not chunks:
        print("생성된 청크가 없습니다.")
        return

    print(f"생성된 청크 수: {len(chunks)}")
    print(f"청크 크기: {CHUNK_SIZE}")
    print(f"청크 overlap: {CHUNK_OVERLAP}")

    # 기존 ChromaDB 삭제
    reset_chroma_db()
    # ChromaDB 구축
    vectorstore = build_vector_db(chunks)

    print("=" * 70)
    print("ChromaDB 구축 완료")
    print(f"저장 경로: {CHROMA_DB_DIR}")
    print(f"Collection: {COLLECTION_NAME}")

if __name__ == "__main__":

    print("=" * 70)
    print("데이터 파이프라인: 가공(Process) 및 저장(Store) 단계 시작")
    print("=" * 70)

    process_and_store_data()
    
    print("=" * 70)
    print("데이터 전처리 및 벡터DB 적재 파이프라인 완료")
    print("=" * 70)