const STORAGE_KEY = "python-debug-assistant.sessions";

const TOOL_META = {
  python_docs_search: {
    icon: "📘",
    label: "Python 공식문서 검색",
  },
  python_error_search: {
    icon: "🐞",
    label: "Python 에러 검색",
  },
  stackoverflow_search: {
    icon: "🧩",
    label: "StackOverflow 검색",
  },
  web_search: {
    icon: "🌐",
    label: "웹 검색",
  },
  unknown: {
    icon: "🔧",
    label: "Tool",
  },
};

let sessions = [];
let currentSessionId = null;
let currentEventSource = null;

const chatListEl = document.getElementById("chat-list");
const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat-btn");
const chatTitleEl = document.getElementById("chat-title");
const chatSubtitleEl = document.getElementById("chat-subtitle");

const stepsEl = document.getElementById("steps");
const agentStatusEl = document.getElementById("agent-status");
const clearStepsBtn = document.getElementById("clear-steps-btn");

const modelCallsEl = document.getElementById("model-calls");
const toolCallsEl = document.getElementById("tool-calls");
const totalCallsEl = document.getElementById("total-calls");

function nowText() {
  return new Date().toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function createId() {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function loadSessions() {
  try {
    sessions = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    sessions = [];
  }

  if (sessions.length === 0) {
    createSession();
  } else {
    currentSessionId = sessions[0].id;
  }

  renderChatList();
  renderMessages();
}

function saveSessions() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function getCurrentSession() {
  return sessions.find((s) => s.id === currentSessionId);
}

function createSession() {
  const session = {
    id: createId(),
    title: "새 채팅",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messages: [],
  };

  sessions.unshift(session);
  currentSessionId = session.id;

  saveSessions();
  renderChatList();
  renderMessages();
  clearSteps();

  return session;
}

function selectSession(sessionId) {
  currentSessionId = sessionId;
  renderChatList();
  renderMessages();
  clearSteps();
}

function updateSessionTitle(session, message) {
  if (session.title !== "새 채팅") return;

  const title = message
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 28);

  session.title = title || "새 채팅";
}

function renderChatList() {
  chatListEl.innerHTML = "";

  sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = `chat-item ${session.id === currentSessionId ? "active" : ""}`;

    item.innerHTML = `
      <div class="chat-item-title">${escapeHtml(session.title)}</div>
      <div class="chat-item-meta">${escapeHtml(nowTextFromIso(session.updatedAt))}</div>
    `;

    item.onclick = () => selectSession(session.id);

    chatListEl.appendChild(item);
  });
}

function nowTextFromIso(iso) {
  try {
    return new Date(iso).toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function renderMessages() {
  const session = getCurrentSession();

  if (!session) return;

  chatTitleEl.textContent = session.title;
  chatSubtitleEl.textContent = `Session ID: ${session.id}`;

  messagesEl.innerHTML = "";

  if (session.messages.length === 0) {
    messagesEl.innerHTML = `
      <div class="empty-state">
        <h3>Python Debug Assistant</h3>
        <p>Python 에러 로그, 문법 질문, 공식 문서 기반 검색을 요청해보세요.</p>
      </div>
    `;
    return;
  }

  session.messages.forEach((msg) => {
    appendMessageToDOM(msg.role, msg.content);
  });

  scrollMessagesToBottom();
}

function appendMessage(role, content) {
  const session = getCurrentSession();
  if (!session) return;

  session.messages.push({
    role,
    content,
    createdAt: new Date().toISOString(),
  });

  session.updatedAt = new Date().toISOString();

  if (role === "user") {
    updateSessionTitle(session, content);
  }

  saveSessions();
  renderChatList();

  if (messagesEl.querySelector(".empty-state")) {
    messagesEl.innerHTML = "";
  }

  appendMessageToDOM(role, content);
  scrollMessagesToBottom();
}

function replaceLastUserMessage(content) {
  const session = getCurrentSession();
  if (!session) return;

  for (let i = session.messages.length - 1; i >= 0; i--) {
    if (session.messages[i].role === "user") {
      session.messages[i].content = content;
      break;
    }
  }

  saveSessions();
  renderMessages();
}

function appendMessageToDOM(role, content) {
  const row = document.createElement("div");
  row.className = `msg-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = `msg ${role}`;
  bubble.textContent = content;

  row.appendChild(bubble);
  messagesEl.appendChild(row);
}

function scrollMessagesToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function clearSteps() {
  stepsEl.innerHTML = "";
  agentStatusEl.textContent = "대기 중";
  modelCallsEl.textContent = "0";
  toolCallsEl.textContent = "0";
  totalCallsEl.textContent = "0";
}

function addStep(type, data) {
  const div = document.createElement("div");
  div.className = `step ${type}`;

  if (type === "start") {
    div.innerHTML = `
      <div class="step-label">🤖 AGENT START</div>
      <div class="step-content">${escapeHtml(data.message || "Agent 시작")}</div>
    `;
  }

  if (type === "input_masked") {
    div.className = "step tool-result";
    div.innerHTML = `
      <div class="step-label">🛡 INPUT MASKED</div>
      <div class="step-content">개인정보 또는 욕설이 마스킹되었습니다.</div>
    `;
  }

  if (type === "tool_call") {
    const meta = TOOL_META[data.tool] || TOOL_META.unknown;

    div.innerHTML = `
      <div class="step-label">${meta.icon} TOOL CALL → ${escapeHtml(data.tool)}</div>
      <div class="step-args">${escapeHtml(JSON.stringify(data.args || {}, null, 2))}</div>
    `;
  }

  if (type === "tool_result") {
    const meta = TOOL_META[data.tool] || TOOL_META.unknown;
    const content = data.content || "";
    const preview = content.length > 360 ? content.slice(0, 360) + "..." : content;

    div.innerHTML = `
      <div class="step-label">✅ TOOL RESULT ← ${meta.label}</div>
      <div class="step-content">${escapeHtml(preview)}</div>
    `;
  }

  if (type === "answer") {
    div.innerHTML = `
      <div class="step-label">💬 FINAL ANSWER</div>
      <div class="step-content">최종 답변 생성 완료</div>
    `;
  }

  if (type === "error") {
    div.innerHTML = `
      <div class="step-label">❌ ERROR</div>
      <div class="step-content">${escapeHtml(data.message || "오류 발생")}</div>
    `;
  }

  stepsEl.appendChild(div);
  stepsEl.scrollTop = stepsEl.scrollHeight;
}

function setRunning(isRunning) {
  sendBtn.disabled = isRunning;
  inputEl.disabled = isRunning;
  agentStatusEl.textContent = isRunning ? "실행 중..." : "대기 중";
  sendBtn.textContent = isRunning ? "실행 중" : "전송";
}

function sendMessage() {
  const message = inputEl.value.trim();

  if (!message) return;

  const session = getCurrentSession();

  if (!session) {
    createSession();
  }

  appendMessage("user", message);
  inputEl.value = "";
  clearSteps();
  setRunning(true);

  if (currentEventSource) {
    currentEventSource.close();
  }

  const url = `/api/agent/stream?session_id=${encodeURIComponent(currentSessionId)}&question=${encodeURIComponent(message)}`;

  currentEventSource = new EventSource(url);

  let finalAnswer = "";

  currentEventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "start") {
      addStep("start", data);
    }

    if (data.type === "input_masked") {
      addStep("input_masked", data);

      if (data.masked_question) {
        replaceLastUserMessage(data.masked_question);
      }
    }

    if (data.type === "tool_call") {
      addStep("tool_call", data);
    }

    if (data.type === "tool_result") {
      addStep("tool_result", data);
    }

    if (data.type === "answer") {
      finalAnswer = data.content || "";
      addStep("answer", data);
    }

    if (data.type === "done") {
      currentEventSource.close();
      currentEventSource = null;

      if (data.usage) {
        modelCallsEl.textContent = data.usage.model_calls ?? 0;
        toolCallsEl.textContent = data.usage.tool_calls ?? 0;
        totalCallsEl.textContent = data.usage.total_calls ?? 0;
      }

      appendMessage("assistant", finalAnswer || data.answer || "답변을 생성하지 못했습니다.");
      setRunning(false);
      agentStatusEl.textContent = "완료";
    }

    if (data.type === "error") {
      currentEventSource.close();
      currentEventSource = null;

      addStep("error", data);
      appendMessage("assistant", `오류가 발생했습니다.\n\n${data.message || "알 수 없는 오류"}`);
      setRunning(false);
      agentStatusEl.textContent = "오류";
    }
  };

  currentEventSource.onerror = () => {
    if (currentEventSource) {
      currentEventSource.close();
      currentEventSource = null;
    }

    addStep("error", {
      message: "SSE 연결이 종료되었거나 서버 응답을 받을 수 없습니다.",
    });

    appendMessage("assistant", "서버와의 연결 중 문제가 발생했습니다.");
    setRunning(false);
    agentStatusEl.textContent = "연결 오류";
  };
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

newChatBtn.addEventListener("click", () => {
  createSession();
});

sendBtn.addEventListener("click", () => {
  sendMessage();
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.ctrlKey) {
    sendMessage();
  }
});

clearStepsBtn.addEventListener("click", () => {
  clearSteps();
});

document.querySelectorAll(".quick-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    inputEl.value = btn.textContent.trim();
    inputEl.focus();
  });
});

loadSessions();