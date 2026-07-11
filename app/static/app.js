const STORAGE_KEY = "python-debug-assistant.sessions";
const ACTIVE_SESSION_KEY = "python-debug-assistant.active-session";

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
let activeRequest = null;

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
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    sessions = Array.isArray(stored)
      ? stored
          .filter((session) => session && typeof session.id === "string")
          .map((session) => ({
            id: session.id,
            title: typeof session.title === "string" ? session.title : "이전 대화",
            createdAt: session.createdAt || new Date().toISOString(),
            updatedAt: session.updatedAt || session.createdAt || new Date().toISOString(),
            messages: Array.isArray(session.messages)
              ? session.messages.filter(
                  (message) =>
                    message &&
                    ["user", "assistant"].includes(message.role) &&
                    typeof message.content === "string",
                )
              : [],
          }))
      : [];
  } catch {
    sessions = [];
  }

  if (sessions.length === 0) {
    createSession();
  } else {
    const storedActiveId = localStorage.getItem(ACTIVE_SESSION_KEY);
    currentSessionId = sessions.some((session) => session.id === storedActiveId)
      ? storedActiveId
      : sessions[0].id;
  }

  renderChatList();
  renderMessages();
}

function saveSessions() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    if (currentSessionId) {
      localStorage.setItem(ACTIVE_SESSION_KEY, currentSessionId);
    }
  } catch (error) {
    console.warn("대화 기록을 브라우저에 저장하지 못했습니다.", error);
  }
}

function getCurrentSession() {
  return sessions.find((s) => s.id === currentSessionId);
}

function getSession(sessionId) {
  return sessions.find((session) => session.id === sessionId);
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
  if (!getSession(sessionId)) return;

  currentSessionId = sessionId;
  saveSessions();
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

function appendMessageToSession(sessionId, role, content) {
  const session = getSession(sessionId);
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

  if (sessionId === currentSessionId) {
    if (messagesEl.querySelector(".empty-state")) {
      messagesEl.innerHTML = "";
    }

    appendMessageToDOM(role, content);
    scrollMessagesToBottom();
  }
}

function replaceLastUserMessage(sessionId, content) {
  const session = getSession(sessionId);
  if (!session) return;

  for (let i = session.messages.length - 1; i >= 0; i--) {
    if (session.messages[i].role === "user") {
      session.messages[i].content = content;
      break;
    }
  }

  saveSessions();

  if (sessionId === currentSessionId) {
    renderMessages();
  }
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
      <div class="step-label">분석 시작</div>
      <div class="step-content">질문과 이전 대화를 확인하고 있습니다.</div>
    `;
  }

  if (type === "input_masked") {
    div.className = "step tool-result";
    div.innerHTML = `
      <div class="step-label">민감 정보 보호</div>
      <div class="step-content">입력에 포함된 민감 정보를 가렸습니다.</div>
    `;
  }

  if (type === "tool_call") {
    const meta = TOOL_META[data.tool] || TOOL_META.unknown;

    div.innerHTML = `
      <div class="step-label">${meta.icon} ${meta.label}</div>
      <div class="step-content">해결에 필요한 자료를 찾고 있습니다.</div>
    `;
  }

  if (type === "tool_result") {
    const meta = TOOL_META[data.tool] || TOOL_META.unknown;
    div.innerHTML = `
      <div class="step-label">${meta.icon} 자료 확인 완료</div>
      <div class="step-content">${meta.label} 결과를 답변에 반영합니다.</div>
    `;
  }

  if (type === "answer") {
    div.innerHTML = `
      <div class="step-label">답변 작성 완료</div>
      <div class="step-content">원인과 해결 방법을 정리했습니다.</div>
    `;
  }

  if (type === "error") {
    div.innerHTML = `
      <div class="step-label">처리 중단</div>
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

function finishRequest(requestState) {
  if (!requestState || requestState.finished) return false;

  requestState.finished = true;
  requestState.source.close();

  if (activeRequest === requestState) {
    activeRequest = null;
    currentEventSource = null;
    setRunning(false);
  }

  return true;
}

function showRequestStep(requestState, type, data) {
  if (requestState.sessionId === currentSessionId) {
    addStep(type, data);
  }
}

function sendMessage() {
  const message = inputEl.value.trim();

  if (!message) return;

  const session = getCurrentSession();

  if (!session) {
    createSession();
  }

  const requestSessionId = currentSessionId;

  appendMessageToSession(requestSessionId, "user", message);
  inputEl.value = "";
  clearSteps();
  setRunning(true);

  if (currentEventSource) {
    currentEventSource.close();
  }

  const url = `/api/agent/stream?session_id=${encodeURIComponent(requestSessionId)}&question=${encodeURIComponent(message)}`;

  const source = new EventSource(url);
  const requestState = {
    source,
    sessionId: requestSessionId,
    finished: false,
    finalAnswer: "",
  };

  activeRequest = requestState;
  currentEventSource = source;

  source.onmessage = (event) => {
    if (activeRequest !== requestState || requestState.finished) return;

    let data;

    try {
      data = JSON.parse(event.data);
    } catch {
      showRequestStep(requestState, "error", { message: "서버 응답을 읽지 못했습니다." });
      appendMessageToSession(requestSessionId, "assistant", "서버 응답 형식에 문제가 발생했습니다.");
      finishRequest(requestState);
      return;
    }

    if (data.type === "start") {
      showRequestStep(requestState, "start", data);
    }

    if (data.type === "input_masked") {
      showRequestStep(requestState, "input_masked", data);

      if (data.masked_question) {
        replaceLastUserMessage(requestSessionId, data.masked_question);
      }
    }

    if (data.type === "tool_call") {
      showRequestStep(requestState, "tool_call", data);
    }

    if (data.type === "tool_result") {
      showRequestStep(requestState, "tool_result", data);
    }

    if (data.type === "answer") {
      requestState.finalAnswer = data.content || requestState.finalAnswer;
      showRequestStep(requestState, "answer", data);
    }

    if (data.type === "done") {
      if (!finishRequest(requestState)) return;

      if (data.usage && requestSessionId === currentSessionId) {
        modelCallsEl.textContent = data.usage.model_calls ?? 0;
        toolCallsEl.textContent = data.usage.tool_calls ?? 0;
        totalCallsEl.textContent = data.usage.total_calls ?? 0;
      }

      const answer = requestState.finalAnswer || data.answer || "답변을 생성하지 못했습니다. 다시 질문해 주세요.";
      appendMessageToSession(requestSessionId, "assistant", answer);

      if (requestSessionId === currentSessionId) {
        agentStatusEl.textContent = "완료";
      }
    }

    if (data.type === "error") {
      if (!finishRequest(requestState)) return;

      showRequestStep(requestState, "error", data);
      appendMessageToSession(requestSessionId, "assistant", `오류가 발생했습니다.\n\n${data.message || "알 수 없는 오류"}`);

      if (requestSessionId === currentSessionId) {
        agentStatusEl.textContent = "오류";
      }
    }
  };

  source.onerror = () => {
    if (activeRequest !== requestState || requestState.finished) return;
    if (!finishRequest(requestState)) return;

    showRequestStep(requestState, "error", {
      message: "SSE 연결이 종료되었거나 서버 응답을 받을 수 없습니다.",
    });

    appendMessageToSession(requestSessionId, "assistant", "서버와의 연결 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.");

    if (requestSessionId === currentSessionId) {
      agentStatusEl.textContent = "연결 오류";
    }
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
