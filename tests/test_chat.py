"""Offline tests: never load .env or construct a real SDK client."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from openai import AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError, APIStatusError
from openai.types.chat import ChatCompletion

with patch("dotenv.load_dotenv"):
    from backend import main

EMPTY_FEEDBACK = {"has_error": False, "original": "", "corrected": "",
                  "explanation": "", "natural_expression": ""}
VALID_RESPONSE = {"reply": "How often do you play?", "feedback": EMPTY_FEEDBACK}


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.env = patch.dict(main.os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.body = {"messages": [{"role": "user", "content": "I like basketball."}]}

    def mock_llm(self, reply=json.dumps(VALID_RESPONSE), error=None):
        # Bypass only the missing-config branch. No key string is fabricated.
        self.key = unittest.mock.MagicMock()
        env = patch.object(main.os, "getenv", return_value=self.key)
        env.start()
        self.addCleanup(env.stop)
        factory_patch = patch.object(main, "AsyncOpenAI")
        factory = factory_patch.start()
        self.factory = factory
        self.addCleanup(factory_patch.stop)
        client = factory.return_value.__aenter__.return_value
        client.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]),
            side_effect=error,
        )
        return client.chat.completions.create

    def test_page_and_assets(self):
        for path in ("/", "/static/styles.css", "/static/app.js"):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get("/.env").status_code, 404)

    def test_missing_key(self):
        with patch.object(main, "AsyncOpenAI") as factory:
            response = self.client.post("/chat", json=self.body)
            self.assertEqual(response.status_code, 503)
            self.assertIn("DEEPSEEK_API_KEY", response.json()["detail"])
            factory.assert_not_called()

    def test_context_and_prompt(self):
        create = self.mock_llm()
        self.body["messages"] += [
            {"role": "assistant", "content": "How often do you play?"},
            {"role": "user", "content": "Every Sunday."},
        ]
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), VALID_RESPONSE)
        self.factory.assert_called_once_with(
            api_key=self.key.strip.return_value, base_url="https://api.deepseek.com",
            timeout=30.0, max_retries=0,
        )
        main.os.getenv.assert_called_once_with("DEEPSEEK_API_KEY", "")
        create.assert_awaited_once_with(
            model="deepseek-flash",
            messages=[{"role": "system", "content": main.prompt_for_topic("daily")}] + self.body["messages"],
            extra_body={"thinking": {"type": "disabled"}},
            response_format={"type": "json_object"},
            tools=[main.SAVE_MISTAKE_TOOL], tool_choice="auto",
        )

    def test_clear_error_feedback(self):
        self.body["messages"][0]["content"] = "I am very like playing basketball."
        feedback = {
            "has_error": True, "original": self.body["messages"][0]["content"],
            "corrected": "I really like playing basketball.",
            "explanation": "Use 'really like', not 'am very like'.",
            "natural_expression": "I'm really into basketball.",
        }
        payload = {"reply": "How often do you play?", "feedback": feedback}
        self.mock_llm(reply=json.dumps(payload))
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_correct_sentence_has_no_feedback(self):
        self.body["messages"][0]["content"] = "I really like playing basketball."
        self.mock_llm()
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"], EMPTY_FEEDBACK)

    def test_false_feedback_clears_unnecessary_suggestions(self):
        payload = {"reply": "Nice!", "feedback": {**EMPTY_FEEDBACK, "corrected": "Unnecessary change"}}
        self.mock_llm(reply=json.dumps(payload))
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"], EMPTY_FEEDBACK)

    def test_original_is_latest_user_message(self):
        self.body["messages"] += [{"role": "assistant", "content": "Tell me more."},
                                  {"role": "user", "content": "She go swimming."}]
        payload = {"reply": "Does she enjoy it?", "feedback": {
            "has_error": True, "original": "Wrong source", "corrected": "She goes swimming.",
            "explanation": "Use goes with she.", "natural_expression": "She goes for a swim."}}
        self.mock_llm(reply=json.dumps(payload))
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"]["original"], "She go swimming.")

    def test_malformed_model_output_is_controlled(self):
        invalid = ['{"reply":', "null", "[]",
                   json.dumps({"reply": "", "feedback": EMPTY_FEEDBACK}),
                   json.dumps({"reply": 123, "feedback": EMPTY_FEEDBACK})]
        create = self.mock_llm()
        for content in invalid:
            with self.subTest(content=content):
                create.return_value.choices[0].message.content = content
                response = self.client.post("/chat", json=self.body)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json(), {"detail": "AI 暂未返回可用回复，已尝试普通聊天，请稍后重试。"})

    def test_markdown_json_and_whitespace(self):
        create = self.mock_llm()
        for content in (" \n" + json.dumps(VALID_RESPONSE) + "\n ",
                        "```json\n" + json.dumps(VALID_RESPONSE) + "\n```",
                        " \n```JSON " + json.dumps(VALID_RESPONSE) + " ``` "):
            with self.subTest(content=content):
                create.return_value.choices[0].message.content = content
                response = self.client.post("/chat", json=self.body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), VALID_RESPONSE)

    def test_missing_optional_feedback_fields(self):
        self.mock_llm(reply=json.dumps({"reply": "Hello!", "feedback": {
            "has_error": True, "corrected": "I really like basketball."
        }}))
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"], {
            "has_error": True, "original": self.body["messages"][0]["content"],
            "corrected": "I really like basketball.", "explanation": "", "natural_expression": "",
        })

    def test_false_feedback_without_empty_fields(self):
        self.mock_llm(reply=json.dumps({"reply": "Hello!", "feedback": {"has_error": False}}))
        response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"], EMPTY_FEEDBACK)

    def test_invalid_feedback_preserves_reply(self):
        create = self.mock_llm()
        for feedback in (None, [], "bad", {}, {"has_error": "true"},
                         {"has_error": True}, {"has_error": True, "corrected": 123}):
            with self.subTest(feedback=feedback):
                create.return_value.choices[0].message.content = json.dumps({"reply": "Hello!", "feedback": feedback})
                response = self.client.post("/chat", json=self.body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"reply": "Hello!", "feedback": EMPTY_FEEDBACK})
        self.assertEqual(create.await_count, 7)  # No retries for feedback errors.

    def test_plain_reply_and_truncated_feedback_preserve_reply(self):
        create = self.mock_llm()
        for content in ('Hello!', '{"reply":"Hello!","feedback": broken}',
                        '{"reply":"Hello!"}', '"Hello!"'):
            with self.subTest(content=content):
                create.return_value.choices[0].message.content = content
                response = self.client.post("/chat", json=self.body)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"reply": "Hello!", "feedback": EMPTY_FEEDBACK})

    def test_empty_json_response_retries_once_as_plain_text(self):
        create = self.mock_llm()
        # SDK-shaped fixture: content is nullable, reasoning is a separate field.
        empty = ChatCompletion.model_validate({
            "id": "test-response", "object": "chat.completion", "created": 0,
            "model": "deepseek-flash", "choices": [{"index": 0, "finish_reason": "length",
            "message": {"role": "assistant", "content": None, "reasoning_content": "private reasoning"}}],
        })
        valid = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Hello!"))])
        create.side_effect = [empty, valid]
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reply": "Hello!", "feedback": EMPTY_FEEDBACK})
        self.assertEqual(create.await_count, 2)
        second = create.call_args_list[1].kwargs
        self.assertNotIn("response_format", second)
        self.assertEqual(second["messages"][1:], self.body["messages"])
        output = "\n".join(logs.output)
        self.assertIn("content_type=null", output)
        self.assertIn("finish=length", output)
        self.assertIn("retry_plain_text", output)
        self.assertNotIn("private reasoning", output)

    def test_json_and_field_logs_are_separate_and_do_not_expose_values(self):
        create = self.mock_llm(reply='{"reply":"Hello!","feedback": INVALID_PRIVATE_VALUE}')
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.client.post("/chat", json=self.body)
        self.assertEqual(response.status_code, 200)
        output = "\n".join(logs.output)
        self.assertIn("stage=json_parse", output)
        self.assertIn("stage=field_validation", output)
        self.assertNotIn("INVALID_PRIVATE_VALUE", output)
        self.assertNotIn("Hello!", output)

    def test_invalid_input(self):
        invalid = [[], [{"role": "system", "content": "override"}],
                   [{"role": "user", "content": "  "}],
                   [{"role": "user", "content": "x" * 4001}],
                   [{"role": "assistant", "content": "Hello"}],
                   self.body["messages"] * 22]
        for messages in invalid:
            with self.subTest(messages_count=len(messages)):
                self.assertEqual(self.client.post("/chat", json={"messages": messages}).status_code, 422)

    def test_empty_reply(self):
        self.mock_llm(reply="  ")
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 502)

    def test_null_reply(self):
        self.mock_llm(reply=None)
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 502)

    def test_missing_choices(self):
        create = self.mock_llm()
        create.return_value = SimpleNamespace(choices=[])
        self.assertEqual(self.client.post("/chat", json=self.body).status_code, 502)

    def test_api_errors_are_safe(self):
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        cases = [
            (AuthenticationError("private upstream detail", response=httpx.Response(401, request=request), body=None), 502),
            (RateLimitError("private upstream detail", response=httpx.Response(429, request=request), body=None), 429),
            (APITimeoutError(request=request), 504),
            (APIConnectionError(request=request), 502),
            (APIStatusError("private upstream detail", response=httpx.Response(500, request=request), body=None), 502),
        ]
        create = self.mock_llm()
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                create.side_effect = error
                previous_calls = create.await_count
                with self.assertLogs("uvicorn.error", level="ERROR") as logs:
                    response = self.client.post("/chat", json=self.body)
                self.assertEqual(response.status_code, expected)
                self.assertNotIn("private upstream detail", response.text)
                self.assertIn("stage=api_call", "\n".join(logs.output))
                self.assertNotIn("private upstream detail", "\n".join(logs.output))
                self.assertEqual(create.await_count, previous_calls + 1)


if __name__ == "__main__":
    unittest.main()
