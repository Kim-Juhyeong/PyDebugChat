#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "============================================================"
echo "Python Debug Assistant 서버 시작"
echo "PROJECT_ROOT: $PROJECT_ROOT"
echo "============================================================"

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

if [ -z "${OPENAI_API_KEY:-}" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key" ]; then
    echo "ERROR: OPENAI_API_KEY가 설정되지 않았습니다."
    echo ".env 파일을 수정하세요."
    exit 1
fi

if [ -z "${TAVILY_API_KEY:-}" ] || [ "$TAVILY_API_KEY" = "your_tavily_api_key" ]; then
    echo "WARNING: TAVILY_API_KEY가 설정되지 않았습니다."
    echo "web_search Tool 사용 시 오류가 발생할 수 있습니다."
fi

mkdir -p "${RAW_DOCS_DIR:-/mnt/data/raw_docs}"
mkdir -p "${PROCESSED_DOCS_DIR:-/mnt/data/processed_docs}"
mkdir -p "${CHROMA_DB_DIR:-/mnt/data/chroma_db}"
mkdir -p "${LOG_DIR:-/mnt/data/logs}"

if [ ! -d "${CHROMA_DB_DIR:-/mnt/data/chroma_db}" ] || [ -z "$(ls -A "${CHROMA_DB_DIR:-/mnt/data/chroma_db}" 2>/dev/null)" ]; then
    echo "WARNING: ChromaDB 디렉토리가 비어 있습니다."
    echo "RAG 검색을 사용하려면 먼저 아래 명령을 실행하세요."
    echo
    echo "./pipeline/run_pipeline.sh"
    echo
fi

HOST="0.0.0.0"
PORT="3000"

echo "서버 실행 설정"
echo "HOST=$HOST"
echo "PORT=$PORT"
echo "CHROMA_DB_DIR=${CHROMA_DB_DIR:-/mnt/data/chroma_db}"
echo "CHAT_HISTORY_DB=${CHAT_HISTORY_DB:-/mnt/data/chat_history.db}"
echo

echo "브라우저:"
echo "http://localhost:3000"
echo "http://<your-server-ip>:3000"
echo

python -m uvicorn app.server:app \
    --host "$HOST" \
    --port "$PORT"