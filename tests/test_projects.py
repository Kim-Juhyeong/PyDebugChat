import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

os.environ["DATA_DIR"] = str(Path(__file__).resolve().parent.parent / "data" / "tests")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")

from fastapi.testclient import TestClient

import app.projects as projects_module
import app.server as server_module


def make_zip(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


class ProjectServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        self.projects_dir.mkdir()
        self.projects_patch = patch.object(projects_module, "PROJECTS_DIR", self.projects_dir)
        self.projects_patch.start()

    def tearDown(self):
        self.projects_patch.stop()
        self.temp_dir.cleanup()

    def test_zip_is_extracted_and_source_file_can_be_read(self):
        payload = make_zip({
            "demo/main.py": "print('hello')\n",
            "demo/App.java": "class App {}\n",
            "demo/image.png": "not-a-real-image",
        })

        project = projects_module.create_project_from_zip("demo.zip", payload)
        tree = projects_module.get_project_tree(project["id"])
        file_data = projects_module.read_project_file(project["id"], "demo/main.py")

        self.assertEqual(project["file_count"], 2)
        self.assertEqual(project["skipped_count"], 1)
        self.assertEqual(tree[0]["name"], "demo")
        self.assertEqual(file_data["language"], "python")
        self.assertIn("hello", file_data["content"])

    def test_zip_path_traversal_is_rejected(self):
        payload = make_zip({"../outside.py": "print('unsafe')"})
        with self.assertRaises(projects_module.ProjectArchiveError):
            projects_module.create_project_from_zip("unsafe.zip", payload)

    def test_env_files_are_not_extracted(self):
        payload = make_zip({
            ".env": "OPENAI_API_KEY=secret",
            "main.py": "print('safe')",
        })
        project = projects_module.create_project_from_zip("safe.zip", payload)
        self.assertEqual(project["file_count"], 1)
        self.assertFalse((self.projects_dir / project["id"] / "files" / ".env").exists())


class ProjectApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.projects_dir = Path(self.temp_dir.name) / "projects"
        self.projects_dir.mkdir()
        self.projects_patch = patch.object(projects_module, "PROJECTS_DIR", self.projects_dir)
        self.projects_patch.start()
        self.client = TestClient(server_module.app)

    def tearDown(self):
        self.projects_patch.stop()
        self.temp_dir.cleanup()

    def test_upload_list_and_read_file(self):
        payload = make_zip({"src/main.py": "value = 42\n"})
        upload = self.client.post(
            "/api/projects",
            files={"file": ("sample.zip", payload, "application/zip")},
        )

        self.assertEqual(upload.status_code, 201)
        project_id = upload.json()["project"]["id"]

        projects = self.client.get("/api/projects")
        file_response = self.client.get(
            f"/api/projects/{project_id}/file",
            params={"path": "src/main.py"},
        )

        self.assertEqual(len(projects.json()["projects"]), 1)
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response.json()["line_count"], 1)

    def test_delete_session_calls_checkpoint_cleanup(self):
        cleanup = AsyncMock()
        with patch.object(server_module, "delete_thread", cleanup):
            response = self.client.delete("/api/sessions/session-to-delete")

        self.assertEqual(response.status_code, 204)
        cleanup.assert_awaited_once_with("session-to-delete")


if __name__ == "__main__":
    unittest.main()
