#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python}"


# .env 확인 및 로드


if [ ! -f ".env" ]; then
    echo "ERROR: .env 파일이 없습니다."
    echo "다음 명령으로 .env 파일을 먼저 생성하세요."
    echo
    echo "cp .env.example .env"
    echo "nano .env"
    exit 1
fi

set -a
source .env
set +a


# 필수 환경 변수 확인


if [ -z "${OPENAI_API_KEY:-}" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key" ]; then
    echo "ERROR: OPENAI_API_KEY가 설정되어 있지 않습니다."
    echo ".env 파일에 OPENAI_API_KEY를 설정하세요."
    exit 1
fi


# 기본 경로 생성


RAW_DOCS_DIR="${RAW_DOCS_DIR:-/mnt/data/raw_docs}"
PROCESSED_DOCS_DIR="${PROCESSED_DOCS_DIR:-/mnt/data/processed_docs}"
CHROMA_DB_DIR="${CHROMA_DB_DIR:-/mnt/data/chroma_db}"
LOG_DIR="${LOG_DIR:-/mnt/data/logs}"

mkdir -p "$RAW_DOCS_DIR"
mkdir -p "$PROCESSED_DOCS_DIR"
mkdir -p "$CHROMA_DB_DIR"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/pipeline_$(date +%Y%m%d_%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "============================================================"
echo "Python Debug Assistant 데이터 파이프라인 시작"
echo "시작 시간: $(date)"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "RAW_DOCS_DIR: $RAW_DOCS_DIR"
echo "PROCESSED_DOCS_DIR: $PROCESSED_DOCS_DIR"
echo "CHROMA_DB_DIR: $CHROMA_DB_DIR"
echo "LOG_FILE: $LOG_FILE"
echo "============================================================"

echo
echo "1단계: Python 공식 문서 크롤링"
$PYTHON_BIN -m pipeline.crawl_python_docs

echo
echo "2단계: 문서 정제, 청크 분할, 임베딩, ChromaDB 저장"
$PYTHON_BIN -m pipeline.build_chroma_db

echo
echo "============================================================"
echo "데이터 파이프라인 완료"
echo "종료 시간: $(date)"
echo "로그 파일: $LOG_FILE"
echo "============================================================"