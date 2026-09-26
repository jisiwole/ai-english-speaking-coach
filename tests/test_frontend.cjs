// Minimal DOM stand-in: exercise rendering and chat state without a browser or API.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor() { this.children = []; this.listeners = {}; this.value = ""; }
  append(...children) {
    for (const child of children) { child.parent = this; this.children.push(child); }
  }
  setAttribute() {}
  replaceChildren(...children) { this.children = []; this.append(...children); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  focus() {}
  remove() { this.parent.children = this.parent.children.filter((child) => child !== this); }
}

function setup() {
  const elements = Object.fromEntries(
    ["chat-form", "topic-select", "new-chat-button", "message-input", "send-button", "messages", "status"].map((id) => [`#${id}`, new Element()])
  );
  elements["#topic-select"].value = "daily";
  const context = vm.createContext({
    document: { querySelector: (id) => elements[id], createElement: () => new Element() },
  });
  vm.runInContext(readFileSync(require.resolve("../frontend/app.js"), "utf8"), context);
  return { context, elements };
}

const feedback = {
  has_error: true, original: "I am very like basketball.", corrected: "I really like basketball.",
  explanation: "Use really like.", natural_expression: "I'm really into basketball.",
};

test("feedback card displays all sections as text", () => {
  const { context } = setup();
  const article = new Element();
  context.addFeedback(article, { ...feedback, explanation: "<script>example</script>" });
  assert.equal(article.children.length, 1);
  const children = article.children[0].children;
  assert.deepEqual(children.map((child) => child.textContent), [
    "Correction", `${feedback.original} → ${feedback.corrected}`,
    "Why", "<script>example</script>", "Natural Expression", feedback.natural_expression,
  ]);
});

test("correct or malformed feedback creates no empty card", () => {
  const { context } = setup();
  for (const value of [null, undefined, {}, { has_error: false }, { has_error: true },
                       { ...feedback, corrected: null }, { ...feedback, has_error: "true" }]) {
    const article = new Element();
    context.addFeedback(article, value);
    assert.equal(article.children.length, 0);
  }
});

test("partial feedback displays correction without empty optional sections", () => {
  const { context } = setup();
  const article = new Element();
  context.addFeedback(article, { has_error: true, original: "She go.", corrected: "She goes." });
  assert.deepEqual(article.children[0].children.map((child) => child.textContent), [
    "Correction", "She go. → She goes.",
  ]);
});

test("multi-turn requests contain replies but not feedback", async () => {
  const { context, elements } = setup();
  const requests = [];
  context.fetch = async (url, options) => {
    assert.equal(url, "/chat");
    requests.push(JSON.parse(options.body));
    return { ok: true, json: async () => ({ reply: "How often do you play?", feedback }) };
  };
  const input = elements["#message-input"];
  const submit = elements["#chat-form"].listeners.submit;
  input.value = feedback.original;
  await submit({ preventDefault() {} });
  input.value = "Every Sunday.";
  await submit({ preventDefault() {} });
  assert.deepEqual(requests[1].messages, [
    { role: "user", content: feedback.original },
    { role: "assistant", content: "How often do you play?" },
    { role: "user", content: "Every Sunday." },
  ]);
  assert.equal(elements["#messages"].children.length, 4);
  assert.equal(input.value, "");
});

test("format errors keep input and do not add broken history", async () => {
  const { context, elements } = setup();
  context.fetch = async () => ({ ok: false, json: async () => ({ detail: "Please retry." }) });
  elements["#message-input"].value = "She go swimming.";
  await elements["#chat-form"].listeners.submit({ preventDefault() {} });
  assert.equal(elements["#message-input"].value, "She go swimming.");
  assert.equal(elements["#messages"].children.length, 0);
  assert.equal(elements["#status"].textContent, "Please retry.");
  assert.equal(elements["#send-button"].disabled, false);
  assert.equal(vm.runInContext("history.length", context), 0);
});
