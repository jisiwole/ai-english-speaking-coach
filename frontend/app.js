const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const topicSelect = document.querySelector("#topic-select");
const newChatButton = document.querySelector("#new-chat-button");
const button = document.querySelector("#send-button");
const messages = document.querySelector("#messages");
const status = document.querySelector("#status");
let history = [];
let sending = false;

function startNewConversation() {
  if (sending) return;
  history = [];
  messages.replaceChildren();
  addMessage("assistant", "Hi! Tell me about your day, a hobby, or something you enjoy.");
  input.value = "";
  status.className = "";
  status.textContent = "";
  input.focus();
}

newChatButton.addEventListener("click", startNewConversation);

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

function addFeedback(article, feedback) {
  if (!feedback || feedback.has_error !== true) return;
  const fields = ["original", "corrected"];
  if (!fields.every((field) => typeof feedback[field] === "string" && feedback[field].trim())) return;
  const card = document.createElement("section");
  card.className = "feedback-card";
  card.setAttribute("aria-label", "Grammar correction and natural expression");
  const sections = [
    ["Correction", `${feedback.original} → ${feedback.corrected}`],
    ["Why", feedback.explanation],
    ["Natural Expression", feedback.natural_expression],
  ];
  for (const [title, content] of sections) {
    if (typeof content !== "string" || !content.trim()) continue;
    const heading = document.createElement("h2");
    heading.textContent = title;
    const text = document.createElement("p");
    text.textContent = content;
    card.append(heading, text);
  }
  article.append(card);
  messages.scrollTop = messages.scrollHeight;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (!content || sending) return;
  sending = true;
  button.disabled = true;
  input.disabled = true;
  topicSelect.disabled = true;
  newChatButton.disabled = true;
  status.className = "";
  status.textContent = "AI is thinking…";
  const userMessage = { role: "user", content };
  const pending = addMessage("user", content);
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [...history.slice(-20), userMessage], topic: topicSelect.value }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(typeof data?.detail === "string" ? data.detail : "消息格式不正确，请缩短内容后重试。");
    }
    if (typeof data?.reply !== "string" || !data.reply.trim()) {
      throw new Error("AI 没有返回文字，请重试。");
    }
    history = [...history, userMessage, { role: "assistant", content: data.reply }].slice(-20);
    const assistant = addMessage("assistant", data.reply);
    addFeedback(assistant, data.feedback);
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
    topicSelect.disabled = false;
    newChatButton.disabled = false;
    input.focus();
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    form.requestSubmit();
  }
});
