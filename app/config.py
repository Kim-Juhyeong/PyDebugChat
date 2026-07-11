"""Application paths and runtime settings shared by every component."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """Use the OCI block volume on Linux and a local folder during development."""
    if os.name == "posix":
        return Path("/mnt/data/pydebugchat")
    return PROJECT_ROOT / "data"


DATA_DIR = Path(os.getenv("DATA_DIR", str(_default_data_dir()))).expanduser().resolve()
RAW_DATA_DIR = DATA_DIR / "raw_docs"
PROCESSED_DATA_DIR = DATA_DIR / "processed_docs"
CHROMA_DB_DIR = DATA_DIR / "chroma_db"
CHAT_HISTORY_DB = DATA_DIR / "chat_history.db"
LOG_DIR = DATA_DIR / "logs"
PROJECTS_DIR = DATA_DIR / "projects"
UPLOADS_DIR = DATA_DIR / "uploads"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "3000"))
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "python_docs_collection")

MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", "20000"))
MAX_MODEL_CALLS = int(os.getenv("MAX_MODEL_CALLS", "3"))
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "5"))
MAX_TOTAL_CALLS = int(os.getenv("MAX_TOTAL_CALLS", "8"))
MAX_GRAPH_STEPS = int(os.getenv("MAX_GRAPH_STEPS", "12"))


def ensure_data_directories() -> None:
    """Create directories required by the crawler, RAG, logs, and chat memory."""
    for directory in (
        DATA_DIR,
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        CHROMA_DB_DIR,
        LOG_DIR,
        PROJECTS_DIR,
        UPLOADS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def validate_runtime_environment() -> None:
    """Fail early with a clear message when required API settings are missing."""
    required = ("OPENAI_API_KEY", "TAVILY_API_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f".env에 필수 환경 변수를 설정해 주세요: {names}")


ensure_data_directories()
