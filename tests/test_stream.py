import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

os.environ["DATA_DIR"] = str(Path(__file__).resolve().parent.parent / "data" / "tests")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")

import app.server as server_module


def parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


class FakeStreamingGraph:
    def __init__(self, updates, recovered_answer=""):
        self.updates = updates
        self.recovered_answer = recovered_answer
        self.thread_ids = []

    async def astream(self, *args, **kwargs):
        self.thread_ids.append(kwargs["config"]["configurable"]["thread_id"])
        for update in self.updates:
            yield update

    async def aget_state(self, config):
        messages = []
        if self.recovered_answer:
            messages.append(AIMessage(content=self.recovered_answer))
        return SimpleNamespace(values={"messages": messages})


class FailingStreamingGraph(FakeStreamingGraph):
    async def astream(self, *args, **kwargs):
        raise RuntimeError("internal test detail")
        yield


class AgentStreamTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server_module.app)

    def test_stream_returns_one_answer_before_done(self):
        graph = FakeStreamingGraph([
            {"reasoning": {"messages": [AIMessage(content="테스트 답변")]}}
        ])

        async def fake_get_graph():
            return graph

        with patch.object(server_module, "get_graph", fake_get_graph):
            response = self.client.get(
                "/api/agent/stream",
                params={"session_id": "session-a", "question": "질문"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache, no-transform")

        events = parse_sse(response.text)
        self.assertEqual([event["type"] for event in events], ["start", "answer", "done"])
        self.assertEqual(events[-1]["answer"], "테스트 답변")

    def test_stream_recovers_missing_answer_from_graph_state(self):
        graph = FakeStreamingGraph([], recovered_answer="복구된 답변")

        async def fake_get_graph():
            return graph

        with patch.object(server_module, "get_graph", fake_get_graph):
            response = self.client.get(
                "/api/agent/stream",
                params={"session_id": "session-b", "question": "질문"},
            )

        events = parse_sse(response.text)
        self.assertEqual([event["type"] for event in events], ["start", "answer", "done"])
        self.assertEqual(events[-1]["answer"], "복구된 답변")

    def test_stream_rejects_blank_question(self):
        response = self.client.get(
            "/api/agent/stream",
            params={"session_id": "session-c", "question": "   "},
        )
        self.assertEqual(response.status_code, 422)

    def test_same_session_id_is_reused_as_graph_thread_id(self):
        graph = FakeStreamingGraph([
            {"reasoning": {"messages": [AIMessage(content="연속 답변")]}}
        ])

        async def fake_get_graph():
            return graph

        with patch.object(server_module, "get_graph", fake_get_graph):
            for question in ("첫 질문", "후속 질문"):
                response = self.client.get(
                    "/api/agent/stream",
                    params={"session_id": "same-session", "question": question},
                )
                self.assertEqual(response.status_code, 200)

        self.assertEqual(graph.thread_ids, ["same-session", "same-session"])

    def test_stream_hides_internal_error_details(self):
        graph = FailingStreamingGraph([])

        async def fake_get_graph():
            return graph

        with patch.object(server_module, "get_graph", fake_get_graph):
            response = self.client.get(
                "/api/agent/stream",
                params={"session_id": "session-error", "question": "질문"},
            )

        events = parse_sse(response.text)
        self.assertEqual([event["type"] for event in events], ["start", "error"])
        self.assertNotIn("internal test detail", response.text)


if __name__ == "__main__":
    unittest.main()
