# AI English Speaking Coach

用于 GitHub 作品集与 AI/Agent 开发实习求职的英语陪练项目。当前是第一阶段 MVP：通过文字与 AI 自然对话，尚未实现 Agent 或语音功能。

## 当前功能

- 输入英文，点击 Send 或按 Enter 发送（Shift + Enter 换行）。
- 区分 User / AI Coach 消息，AI 简短回复并鼓励继续表达。
- 多轮上下文：每次发送最近 10 轮完整对话和当前问题。
- 发送期间防止重复提交，失败时保留输入供重试。
- 对话仅保存在当前页面，刷新清空，没有数据库或长期 Memory。
- 单条输入最多 4000 字符。

## 技术栈与流程

Python 3.10+、FastAPI、OpenAI Python SDK、python-dotenv、原生 HTML / CSS / JavaScript。

浏览器 → POST /chat → FastAPI → DeepSeek Chat Completions API → 显示回复。

FastAPI 同时提供前端页面，只启动一个服务即可，不需要 Node.js 或前端构建工具。API Key 仅由后端使用。保留 OpenAI Python SDK，通过兼容接口调用 DeepSeek，`base_url` 固定为 `https://api.deepseek.com`。

截至 2026-09-23，已核对 [DeepSeek 官方模型列表](https://api-docs.deepseek.com/quick_start/pricing/)，本项目使用 `deepseek-flash`（DeepSeek-V4.1-Flash）。后端通过 `extra_body={"thinking": {"type": "disabled"}}` 使用非思考模式，适合本版的简短自然对话。参数说明见 [官方思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)。

## 项目结构

```text
backend/
  __init__.py       Python 包标记
  main.py           页面路由、输入校验、陪练提示词、LLM 调用
frontend/
  index.html        聊天页面
  styles.css        页面样式与手机布局
  app.js            请求接口、显示消息、管理上下文
tests/
  test_chat.py      不使用真实 Key 的接口测试
.env.example       环境变量模板，Key 留空
.gitignore         忽略密钥、虚拟环境和缓存
requirements.txt   运行依赖
README.md          安装和使用说明
```

## 安装与启动（Windows PowerShell）

### 1. 准备 Python

安装 Python 3.10 或更高版本，安装时勾选 **Add python.exe to PATH**，然后重新打开终端。运行 `python --version` 确认安装成功。如果系统仅支持 `py` 命令，下方创建虚拟环境的命令可将 `python` 换成 `py`。

### 2. 进入项目并安装依赖

```powershell
cd "C:\Users\张学友\ai-english-speaking-coach"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

直接使用虚拟环境的 Python，无需激活脚本或修改 PowerShell 执行策略。如果 `.venv` 已创建，可以跳过创建步骤。

### 3. 配置环境变量

仅在 `.env` 不存在时复制模板，避免覆盖已有配置：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

`.env.example` 内容只有一行：

```dotenv
DEEPSEEK_API_KEY=
```

自行在记事本中把你的 DeepSeek API Key 填到 `.env` 的 `DEEPSEEK_API_KEY=` 后面并保存，不要发送给 AI 或提交到 GitHub。如果已有旧版 `.env`，请自行将旧的 `OPENAI_API_KEY`、`OPENAI_MODEL` 配置替换为这一行；程序不再使用旧配置。模型名固定在后端，无需填写模型环境变量。已有同名系统环境变量优先于 `.env`，修改配置后需重启服务。`.env` 仍由 `.gitignore` 忽略。

模板中的 Key 故意留空。没有 Key 也可以打开网页，发送时会提示配置。真实对话需要可用的 DeepSeek API Key、DeepSeek 账户额度及网络连接。

### 4. 启动项目

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

保持终端打开，在浏览器访问 http://127.0.0.1:8000 ，不要双击 HTML 文件。输入 `I like playing basketball.`，点击 Send，收到回复后继续回答以验证多轮对话。按 Ctrl + C 停止服务。

接口文档：http://127.0.0.1:8000/docs 。本版用于本地练习，不包含公网访问控制。

## 接口

`POST /chat` 请求示例：

```json
{"messages": [{"role": "user", "content": "I like playing basketball."}]}
```

成功返回 `{"reply": "..."}`。继续聊天时把之前的 user / assistant 消息一起传入；必须交替排列，以 user 开头并结尾。系统提示词由后端设置，前端不能传入 system 角色。

## 基础检查

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall backend tests
```

测试屏蔽 `.env` 加载并替换 LLM 客户端，不读取真实 Key、不发送网络请求。模拟回复仅用于测试，不用于实际聊天。真实模型效果需自行配置 Key 后验证。

## 常见问题

- 找不到 python：安装 Python 并加入 PATH，重新打开终端，或使用 `py`。
- 认证失败：在本地检查 `.env` 并重启服务。
- 请求受限：检查 API 账户额度，或稍后重试。
- 连接失败 / 超时：检查网络和后端终端是否仍在运行。
- 模型请求失败：检查 DeepSeek 服务状态和账户权限，并对照官方模型列表确认 `deepseek-flash` 可用。
- 8000 端口被占用：启动命令改用 `--port 8001`，浏览器也改用对应端口。

第一版没有登录、数据库、长期 Memory、Tool Calling、LangChain、LangGraph、RAG、语音识别、TTS、评分、个性化训练、React、Next.js 或 Docker。
