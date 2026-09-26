# AI English Speaking Coach

一个用 DeepSeek API 驱动的英语口语练习 Web 应用。用户可以进行多轮英语对话，并获得独立的语法纠错和更自然表达建议。

**个人作品集项目 · MVP · Python / FastAPI / 原生 JavaScript**

当前仅支持文字聊天，在本地运行；没有托管演示地址。项目重点是清晰的前后端请求流程、结构化模型输出和异常容错。

## 当前功能

- 输入英文，点击 Send 或按 Enter 发送（Shift + Enter 换行）。
- 区分 User / AI Coach 消息，AI 简短回复并鼓励继续表达。
- Grammar Correction + Natural Expression：只针对明显语法或表达错误，在 AI 回复下显示原句、修正句、简短解释和不改变原意的自然表达。正确句子不强行纠错、不显示空卡片。
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
  test_frontend.cjs 前端反馈展示和多轮聊天逻辑测试（可选 Node.js）
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

在项目根目录启动 FastAPI：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

也可以直接运行后端文件（使用项目虚拟环境）：

```powershell
.\.venv\Scripts\python.exe backend\main.py
```

VS Code 的解释器和 Code Runner 属于本机编辑器设置，未包含在项目中；请按自己的 Python 安装路径选择解释器。

保持终端打开，在浏览器访问 http://127.0.0.1:8000 ，不要双击 HTML 文件。输入 `I like playing basketball.`，点击 Send，收到回复后继续回答以验证多轮对话。按 Ctrl + C 停止服务。

接口文档：http://127.0.0.1:8000/docs 。本版用于本地练习，不包含公网访问控制。

## 接口

`POST /chat` 请求示例：

```json
{"messages": [{"role": "user", "content": "I like playing basketball."}]}
```

成功返回结构化 JSON，例如：

```json
{
  "reply": "That's great! How often do you play basketball?",
  "feedback": {
    "has_error": true,
    "original": "I am very like playing basketball.",
    "corrected": "I really like playing basketball.",
    "explanation": "Use 'really like', not 'am very like', to express enjoyment.",
    "natural_expression": "I'm really into basketball."
  }
}
```

没有明显错误时，`feedback.has_error` 为 `false`，其余四个字符串字段为空。前端在 `has_error` 为 `true` 且原句、修正句有效时显示卡片；可选解释或自然表达缺失时，不显示相应小节。所有内容作为纯文本展示。

后端使用 [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)，兼容正常 JSON、Markdown JSON 代码块和首尾空白。回复和反馈分开校验：有效的 `reply` 会保留；反馈缺失或格式错误时使用 `has_error=false` 和四个空字符串的安全默认值。`has_error=false` 时允许省略空字段；有效修正缺少解释或自然表达时以空字符串补齐，不编造内容。反馈降级不代表用户句子一定正确。

模型返回普通聊天文本时也可直接使用；JSON 后半部分损坏时，尝试提取完整的 `reply` 字符串，不将残缺 JSON 显示为聊天。只有没有可用回复时，才额外请求一次普通文本回复（关闭 JSON 输出约束，保留上下文）。第二次仍无可用回复才返回 HTTP 502。此降级最多增加一次 API 请求，可能增加等待时间和调用费用。认证、限流、连接、超时等 API 异常不会触发此重试；分别给出安全错误提示。失败时页面保留输入且不写入聊天历史。

### 服务端诊断日志

启动后在 Terminal 查看 `coach stage=...`：

- `api_call`：API 调用异常，包含固定错误类别及 HTTP 状态（如可用）。
- `api_response`：API 已返回，记录 choices 数量、content 类型和长度、finish reason、是否存在 reasoning_content。
- `content`：没有可用 content 或类型不受支持。
- `json_parse`：JSON 解析失败，随后尝试保留普通文本或可恢复的 reply。
- `field_validation`：reply 或 feedback 字段校验问题；`defaulted` 表示反馈已安全降级。
- `fallback`：开始普通文本重试，或两次均无有效回复。

日志不打印 API Key、请求头、原始响应、聊天内容或异常原文。DeepSeek 文档规定 `message.content` 为字符串或 null；`reasoning_content` 是独立的思考内容，不会当作聊天回复显示。官方说明 JSON 模式偶尔可能返回空 content，但应结合实际日志定位，不能仅凭 502 判断原因。

继续聊天时仅把之前的 user / assistant 正常对话一起传入，不发送反馈卡片；必须交替排列，以 user 开头并结尾。只纠正最新用户消息，系统提示词由后端设置，前端不能传入 system 角色。

## 基础检查

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall backend tests
```

测试屏蔽 `.env` 加载并替换 LLM 客户端，不读取真实 Key、不发送网络请求。模拟回复仅用于测试，不用于实际聊天。真实模型效果需自行配置 Key 后验证。

如已安装 Node.js，还可以运行前端逻辑测试（运行网站本身不需要 Node.js）：

```powershell
node --test tests/test_frontend.cjs
```

更新代码后停止旧服务并重新执行启动命令，浏览器按 Ctrl + F5 刷新。可分别发送 `I am very like playing basketball.`、`She go to school every day.`、`I really like playing basketball.`；前两句应出现反馈卡片，第三句应只有正常回复。具体措辞由模型生成，离线测试只验证结构和程序行为，不保证真实模型每次都判断正确。

## 常见问题

- 找不到 python：安装 Python 并加入 PATH，重新打开终端，或使用 `py`。
- 认证失败：在本地检查 `.env` 并重启服务。
- 请求受限：检查 API 账户额度，或稍后重试。
- 连接失败 / 超时：检查网络和后端终端是否仍在运行。
- 模型请求失败：检查 DeepSeek 服务状态和账户权限，并对照官方模型列表确认 `deepseek-flash` 可用。
- 8000 端口被占用：启动命令改用 `--port 8001`，浏览器也改用对应端口。

第一版没有登录、数据库、长期 Memory、Tool Calling、LangChain、LangGraph、RAG、语音识别、TTS、评分、个性化训练、React、Next.js 或 Docker。
