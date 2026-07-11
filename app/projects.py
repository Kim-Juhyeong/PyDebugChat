"""Safe project ZIP storage and source-file browsing helpers."""

import json
import re
import shutil
import stat
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.config import (
    MAX_FILE_BYTES,
    MAX_PROJECT_BYTES,
    MAX_PROJECT_FILES,
    MAX_UPLOAD_BYTES,
    PROJECTS_DIR,
)


ALLOWED_SUFFIXES = {
    ".c", ".cc", ".cfg", ".conf", ".cpp", ".cs", ".css", ".csv",
    ".cxx", ".go", ".gradle", ".h", ".hpp", ".htm", ".html", ".ini",
    ".java", ".js", ".json", ".jsx", ".kt", ".kts", ".md", ".php",
    ".properties", ".py", ".rb", ".rs", ".sh", ".sql", ".toml", ".ts",
    ".tsx", ".txt", ".vue", ".xml", ".yaml", ".yml",
}

ALLOWED_NAMES = {
    "dockerfile", "makefile", "pipfile", "procfile", "requirements.txt",
}

IGNORED_PARTS = {
    ".git", ".idea", ".venv", "__macosx", "__pycache__", "build", "dist",
    "node_modules", "target", "venv",
}

LANGUAGE_BY_SUFFIX = {
    ".c": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".h": "cpp",
    ".hpp": "cpp", ".css": "css", ".go": "go", ".html": "html",
    ".htm": "html", ".java": "java", ".js": "javascript", ".jsx": "javascript",
    ".json": "json", ".kt": "kotlin", ".kts": "kotlin", ".md": "markdown",
    ".php": "php", ".py": "python", ".rb": "ruby", ".rs": "rust",
    ".sh": "shell", ".sql": "sql", ".toml": "toml", ".ts": "typescript",
    ".tsx": "typescript", ".vue": "vue", ".xml": "xml", ".yaml": "yaml",
    ".yml": "yaml",
}


class ProjectArchiveError(ValueError):
    pass


def _safe_project_name(filename: str) -> str:
    stem = Path(filename or "project.zip").stem
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._ -]+", "_", stem).strip(" ._")
    return cleaned[:80] or "새 프로젝트"


def _archive_path(info: ZipInfo) -> PurePosixPath:
    normalized = info.filename.replace("\\", "/")
    path = PurePosixPath(normalized)

    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ProjectArchiveError("ZIP 파일에 허용되지 않는 경로가 포함되어 있습니다.")

    if any(part.lower() in IGNORED_PARTS for part in path.parts):
        return PurePosixPath()

    if any(part.lower() == ".env" or part.lower().startswith(".env.") for part in path.parts):
        return PurePosixPath()

    return path


def _is_symlink(info: ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _is_supported(path: PurePosixPath) -> bool:
    return path.name.lower() in ALLOWED_NAMES or path.suffix.lower() in ALLOWED_SUFFIXES


def _project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", project_id):
        raise FileNotFoundError("프로젝트를 찾을 수 없습니다.")
    return PROJECTS_DIR / project_id


def _write_metadata(project_dir: Path, metadata: dict) -> None:
    (project_dir / "project.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_project_from_zip(filename: str, payload: bytes) -> dict:
    if not filename.lower().endswith(".zip"):
        raise ProjectArchiveError("ZIP 파일만 업로드할 수 있습니다.")
    if not payload:
        raise ProjectArchiveError("업로드한 ZIP 파일이 비어 있습니다.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ProjectArchiveError("ZIP 파일은 최대 10MB까지 업로드할 수 있습니다.")

    project_id = uuid.uuid4().hex
    project_dir = PROJECTS_DIR / project_id
    files_dir = project_dir / "files"
    extracted_files = []
    skipped_files = 0

    try:
        with ZipFile(BytesIO(payload)) as archive:
            candidates = []
            total_size = 0

            for info in archive.infolist():
                if info.is_dir():
                    continue
                if info.flag_bits & 0x1 or _is_symlink(info):
                    raise ProjectArchiveError("암호화 파일이나 심볼릭 링크는 업로드할 수 없습니다.")

                path = _archive_path(info)
                if not path.parts or not _is_supported(path):
                    skipped_files += 1
                    continue
                if info.file_size > MAX_FILE_BYTES:
                    raise ProjectArchiveError(f"파일 하나의 크기는 2MB를 넘을 수 없습니다: {path}")

                candidates.append((info, path))
                total_size += info.file_size

            if not candidates:
                raise ProjectArchiveError("분석할 수 있는 소스 파일이 ZIP에 없습니다.")
            if len(candidates) > MAX_PROJECT_FILES:
                raise ProjectArchiveError(f"프로젝트 파일은 최대 {MAX_PROJECT_FILES}개까지 허용됩니다.")
            if total_size > MAX_PROJECT_BYTES:
                raise ProjectArchiveError("압축 해제된 프로젝트 크기는 최대 20MB까지 허용됩니다.")

            files_dir.mkdir(parents=True, exist_ok=False)

            for info, path in candidates:
                target = files_dir.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                content = archive.read(info)
                target.write_bytes(content)
                extracted_files.append(path.as_posix())

    except BadZipFile as exc:
        raise ProjectArchiveError("올바른 ZIP 파일이 아닙니다.") from exc
    except Exception:
        if project_dir.exists():
            shutil.rmtree(project_dir)
        raise

    metadata = {
        "id": project_id,
        "name": _safe_project_name(filename),
        "filename": Path(filename).name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(extracted_files),
        "skipped_count": skipped_files,
    }
    _write_metadata(project_dir, metadata)
    return metadata


def list_projects() -> list[dict]:
    projects = []
    for metadata_path in PROJECTS_DIR.glob("*/project.json"):
        try:
            projects.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(projects, key=lambda item: item.get("created_at", ""), reverse=True)


def get_project(project_id: str) -> dict:
    metadata_path = _project_dir(project_id) / "project.json"
    if not metadata_path.is_file():
        raise FileNotFoundError("프로젝트를 찾을 수 없습니다.")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def delete_project(project_id: str) -> None:
    project_dir = _project_dir(project_id)
    metadata_path = project_dir / "project.json"
    if not metadata_path.is_file():
        raise FileNotFoundError("프로젝트를 찾을 수 없습니다.")
    shutil.rmtree(project_dir)


def _tree_node(directory: Path, root: Path) -> list[dict]:
    nodes = []
    for item in sorted(directory.iterdir(), key=lambda path: (path.is_file(), path.name.lower())):
        relative = item.relative_to(root).as_posix()
        if item.is_dir():
            nodes.append({
                "type": "directory",
                "name": item.name,
                "path": relative,
                "children": _tree_node(item, root),
            })
        else:
            nodes.append({
                "type": "file",
                "name": item.name,
                "path": relative,
                "size": item.stat().st_size,
                "language": detect_language(item),
            })
    return nodes


def get_project_tree(project_id: str) -> list[dict]:
    files_dir = _project_dir(project_id) / "files"
    if not files_dir.is_dir():
        raise FileNotFoundError("프로젝트 파일을 찾을 수 없습니다.")
    return _tree_node(files_dir, files_dir)


def _resolve_project_file(project_id: str, relative_path: str) -> Path:
    files_dir = (_project_dir(project_id) / "files").resolve()
    requested = PurePosixPath((relative_path or "").replace("\\", "/"))
    if requested.is_absolute() or not requested.parts or ".." in requested.parts:
        raise FileNotFoundError("파일을 찾을 수 없습니다.")

    target = files_dir.joinpath(*requested.parts).resolve()
    if target == files_dir or files_dir not in target.parents or not target.is_file():
        raise FileNotFoundError("파일을 찾을 수 없습니다.")
    return target


def detect_language(path: Path) -> str:
    return LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text")


def read_project_file(project_id: str, relative_path: str) -> dict:
    target = _resolve_project_file(project_id, relative_path)
    payload = target.read_bytes()

    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            content = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = payload.decode("utf-8", errors="replace")

    return {
        "path": PurePosixPath(relative_path.replace("\\", "/")).as_posix(),
        "name": target.name,
        "content": content,
        "size": len(payload),
        "line_count": len(content.splitlines()) or 1,
        "language": detect_language(target),
    }
