const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const button = document.querySelector("#send-button");
const messages = document.querySelector("#messages");
const status = document.querySelector("#status");
let history = [];
let sending = false;

function addMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const label = document.createElement("strong");
  label.textContent = role === "user" ? "User" : "AI Coach";
  const text = document.createElement("p");
  text.textContent = content;
  article.append(label, text);
  messages.append(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (!content || sending) return;
  sending = true;
  button.disabled = true;
  input.disabled = true;
  status.className = "";
  status.textContent = "AI is thinking…";
  const userMessage = { role: "user", content };
  const pending = addMessage("user", content);
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [...history.slice(-20), userMessage] }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data.detail === "string" ? data.detail : "消息格式不正确，请缩短内容后重试。");
    }
    if (typeof data.reply !== "string" || !data.reply.trim()) {
      throw new Error("AI 没有返回文字，请重试。");
    }
    history = [...history, userMessage, { role: "assistant", content: data.reply }].slice(-20);
    addMessage("assistant", data.reply);
    input.value = "";
    status.textContent = "";
  } catch (error) {
    pending.remove();
    status.className = "error";
    status.textContent = error instanceof TypeError || error instanceof SyntaxError
      ? "无法连接后端，请确认服务正在运行后重试。" : error.message;
  } finally {
    sending = false;
    button.disabled = false;
    input.disabled = false;
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});
