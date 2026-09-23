"""Offline tests: never load .env or construct a real SDK client."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from openai import AuthenticationError, RateLimitError, APITimeoutError, APIConnectionError

with patch("dotenv.load_dotenv"):
    from backend import main


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.env = patch.dict(main.os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.body = {"messages": [{"role": "user", "content": "I like basketball."}]}

    def mock_llm(self, reply="How often do you play?", error=None):
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
        self.assertEqual(response.json(), {"reply": "How often do you play?"})
        self.factory.assert_called_once_with(
            api_key=self.key.strip.return_value, base_url="https://api.deepseek.com",
            timeout=30.0, max_retries=0,
        )
        main.os.getenv.assert_called_once_with("DEEPSEEK_API_KEY", "")
        create.assert_awaited_once_with(
            model="deepseek-flash",
            messages=[{"role": "system", "content": main.SYSTEM_PROMPT}] + self.body["messages"],
            extra_body={"thinking": {"type": "disabled"}},
        )

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
        ]
        create = self.mock_llm()
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                create.side_effect = error
                response = self.client.post("/chat", json=self.body)
                self.assertEqual(response.status_code, expected)
                self.assertNotIn("private upstream detail", response.text)


if __name__ == "__main__":
    unittest.main()
