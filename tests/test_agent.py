"""Offline tool lifecycle tests; temporary records, no credentials or network."""
import json
import tempfile
import unittest
import httpx
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from openai.types.chat import ChatCompletion
from openai import APIConnectionError
import test_chat
from backend import tools


def tool_response(arguments, name="save_mistake", count=1):
    return ChatCompletion.model_validate({
        "id": "test", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"call_{i}", "type": "function", "function": {
                "name": name, "arguments": arguments,
            }} for i in range(count)],
        }}],
    })


class AgentTests(unittest.TestCase):
    # Reuse only the existing mock setup, without running inherited tests twice.
    setUp = test_chat.ChatTests.setUp
    mock_llm = test_chat.ChatTests.mock_llm

    def prepare(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "mistakes.json"
        override = patch.object(tools, "RECORDS_PATH", path)
        override.start()
        self.addCleanup(override.stop)
        self.body["messages"][0]["content"] = "I go to school yesterday."
        self.record = {"original": "I go to school yesterday.",
                       "corrected": "I went to school yesterday.", "error_type": "past tense"}
        create = self.mock_llm()
        final = create.return_value
        return path, create, final

    def test_error_executes_tool_returns_result_and_final_reply(self):
        path, create, final = self.prepare()
        create.side_effect = [tool_response(json.dumps(self.record)), final]
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), test_chat.VALID_RESPONSE)
        self.assertEqual(json.loads(path.read_text()), [self.record])
        first, second = [call.kwargs for call in create.call_args_list]
        self.assertEqual(first["tool_choice"], "auto")
        self.assertNotIn("tools", second)
        self.assertEqual(second["messages"][-2]["tool_calls"][0]["id"], "call_0")
        result = second["messages"][-1]
        self.assertEqual(result["role"], "tool")
        self.assertEqual(result["tool_call_id"], "call_0")
        self.assertTrue(json.loads(result["content"])["saved"])

    def test_correct_sentence_does_not_save(self):
        path, create, _ = self.prepare()
        self.body["messages"][0]["content"] = "I went to school yesterday."
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 200)
        self.assertFalse(path.exists())
        self.assertEqual(create.await_count, 1)

    def test_bad_arguments_unknown_tool_and_wrong_original_do_not_break_chat(self):
        path, create, final = self.prepare()
        for arguments, name in [("{bad", "save_mistake"), ("{}", "save_mistake"),
                                (json.dumps(self.record), "shell"),
                                (json.dumps({**self.record, "original": "old message"}), "save_mistake"),
                                (json.dumps({**self.record, "corrected": self.record["original"]}), "save_mistake")]:
            with self.subTest(arguments=arguments, name=name):
                create.side_effect = [tool_response(arguments, name), final]
                self.assertEqual(self.client.post("/chat", json=self.body).status_code, 200)
                self.assertFalse(path.exists())
                self.assertFalse(json.loads(create.call_args.kwargs["messages"][-1]["content"])["ok"])

    def test_storage_failure_is_reported_to_model_without_losing_reply(self):
        path, create, final = self.prepare()
        path.write_text("broken existing file")
        create.side_effect = [tool_response(json.dumps(self.record)), final]
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 200)
        self.assertEqual(path.read_text(), "broken existing file")
        self.assertEqual(json.loads(create.call_args.kwargs["messages"][-1]["content"])["error"], "storage_failed")

    def test_api_failure_after_save_keeps_record_and_existing_error_handling(self):
        path, create, _ = self.prepare()
        error = APIConnectionError(request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))
        create.side_effect = [tool_response(json.dumps(self.record)), error]
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 502)
        self.assertEqual(json.loads(path.read_text()), [self.record])
        self.assertEqual(create.await_count, 2)

    def test_topic_and_multi_turn_context_survive_tool_call(self):
        _, create, final = self.prepare()
        self.body["topic"] = "travel"
        self.body["messages"] = [
            {"role": "user", "content": "I like travel."},
            {"role": "assistant", "content": "Where did you go?"},
            self.body["messages"][0],
        ]
        create.side_effect = [tool_response(json.dumps(self.record)), final]
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 200)
        messages = create.call_args.kwargs["messages"]
        self.assertIn("travel English", messages[0]["content"])
        self.assertEqual(messages[1:4], self.body["messages"])

    def test_tool_round_is_bounded_and_fallback_preserves_results(self):
        path, create, final = self.prepare()
        final.choices[0].message.content = "Hello!"
        empty = tool_response("{}")
        empty.choices[0].message.tool_calls = None
        create.side_effect = [tool_response(json.dumps(self.record), count=2), empty, final]
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 200)
        self.assertEqual(create.await_count, 3)
        self.assertEqual(len(json.loads(path.read_text())), 1)
        last = create.call_args.kwargs
        self.assertNotIn("tools", last)
        self.assertNotIn("response_format", last)
        self.assertEqual(last["messages"][-1]["tool_call_id"], "call_1")

    def test_deduplication_concurrent_writes_and_sensitive_content(self):
        path, _, _ = self.prepare()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: tools.save_mistake(**{**self.record, "error_type": str(i)}), range(8)))
        self.assertEqual(len(json.loads(path.read_text())), 8)
        self.assertFalse(tools.save_mistake(**{**self.record, "error_type": "0"})["saved"])
        result = tools.save_mistake("My password is private.", "My password was private.", "tense")
        self.assertFalse(result["ok"])
        self.assertEqual(len(json.loads(path.read_text())), 8)


if __name__ == "__main__":
    unittest.main()
