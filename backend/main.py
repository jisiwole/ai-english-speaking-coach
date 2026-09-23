import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
SYSTEM_PROMPT = """You are a friendly English speaking practice teacher.
Communicate mainly in clear, everyday English. Keep replies short, usually
1–3 sentences. Encourage the learner to express themselves by asking one
relevant follow-up question. Focus on natural conversation. Do not score,
grade, or give long grammar lectures. If asked for help, explain briefly
and gently, then return to the conversation."""

app = FastAPI(title="AI English Speaking Coach")
app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


class Message(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=21)

    @model_validator(mode="after")
    def validate_turns(self):
        for index, message in enumerate(self.messages):
            if message.role != ("user" if index % 2 == 0 else "assistant"):
                raise ValueError("Messages must alternate user and assistant, starting with user.")
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user.")
        return self


class ChatResponse(BaseModel):
    reply: str


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "请在项目根目录的 .env 中填写 DEEPSEEK_API_KEY，然后重启服务。")
    try:
        async with AsyncOpenAI(
            api_key=api_key, base_url="https://api.deepseek.com",
            timeout=30.0, max_retries=0,
        ) as client:
            response = await client.chat.completions.create(
                model="deepseek-flash",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}]
                + [message.model_dump() for message in body.messages],
                extra_body={"thinking": {"type": "disabled"}},
            )
    except AuthenticationError:
        raise HTTPException(502, "API 认证失败，请在本地检查 .env 中的 API Key。") from None
    except RateLimitError:
        raise HTTPException(429, "API 请求受限，请检查账户额度或稍后重试。") from None
    except APITimeoutError:
        raise HTTPException(504, "AI 回复超时，请稍后重试。") from None
    except APIConnectionError:
        raise HTTPException(502, "暂时无法连接 AI 服务，请检查网络后重试。") from None
    except APIStatusError:
        raise HTTPException(502, "AI 服务请求失败，请检查模型配置或稍后重试。") from None
    reply = (response.choices[0].message.content or "").strip() if response.choices else ""
    if not reply:
        raise HTTPException(502, "AI 没有返回文字，请重试。")
    return ChatResponse(reply=reply)
