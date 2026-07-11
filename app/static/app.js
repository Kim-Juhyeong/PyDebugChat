const STORAGE_KEY = "python-debug-assistant.sessions";
const ACTIVE_SESSION_KEY = "python-debug-assistant.active-session";
const ACTIVE_PROJECT_KEY = "python-debug-assistant.active-project";
const ACTIVE_FILE_KEY = "python-debug-assistant.active-file";

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
let projects = [];
let currentProjectId = null;
let currentFilePath = null;

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
const agentPanelEl = document.getElementById("agent-panel");

const modelCallsEl = document.getElementById("model-calls");
const toolCallsEl = document.getElementById("tool-calls");
const totalCallsEl = document.getElementById("total-calls");

const activityButtons = document.querySelectorAll(".activity-btn[data-sidebar-view]");
const sideTitleEl = document.getElementById("side-title");
const projectUploadEl = document.getElementById("project-upload");
const uploadStatusEl = document.getElementById("upload-status");
const projectPickerEl = document.getElementById("project-picker");
const deleteProjectBtn = document.getElementById("delete-project-btn");
const projectFileCountEl = document.getElementById("project-file-count");
const fileTreeEl = document.getElementById("file-tree");
const editorProjectNameEl = document.getElementById("editor-project-name");
const editorLanguageEl = document.getElementById("editor-language");
const editorTabsEl = document.getElementById("editor-tabs");
const editorEmptyEl = document.getElementById("editor-empty");
const codeViewEl = document.getElementById("code-view");
const editorFileStatusEl = document.getElementById("editor-file-status");
const editorLineStatusEl = document.getElementById("editor-line-status");

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
      <button class="chat-delete" type="button" aria-label="${escapeHtml(session.title)} 대화 삭제" title="대화 삭제">×</button>
    `;

    item.onclick = () => selectSession(session.id);

    const deleteButton = item.querySelector(".chat-delete");
    deleteButton.onclick = (event) => {
      event.stopPropagation();
      deleteConversation(session.id);
    };

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
        <h3>디버깅을 시작해볼까요?</h3>
        <p>오류 로그를 붙여 넣거나, 현재 코드에서 이해되지 않는 부분을 질문해보세요.</p>
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

async function deleteConversation(sessionId) {
  const session = getSession(sessionId);
  if (!session) return;

  if (activeRequest?.sessionId === sessionId) {
    window.alert("답변 생성이 끝난 후 대화를 삭제해 주세요.");
    return;
  }

  if (!window.confirm(`“${session.title}” 대화를 삭제할까요?`)) return;

  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      throw new Error("대화 삭제 요청이 실패했습니다.");
    }

    sessions = sessions.filter((item) => item.id !== sessionId);

    if (currentSessionId === sessionId) {
      currentSessionId = sessions[0]?.id || null;
    }

    if (sessions.length === 0) {
      createSession();
      return;
    }

    saveSessions();
    renderChatList();
    renderMessages();
    clearSteps();
  } catch (error) {
    console.error(error);
    window.alert("대화를 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.");
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

  if (type === "progress") {
    div.innerHTML = `
      <div class="step-label">${escapeHtml(data.stage_label || "분석 진행")}</div>
      <div class="step-content">${escapeHtml(data.message || "다음 단계를 처리하고 있습니다.")}</div>
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
    const args = data.args || {};
    const query = args.query || args.error_message || args.input || JSON.stringify(args);
    const queryPreview = String(query).length > 240 ? `${String(query).slice(0, 240)}...` : String(query);

    div.innerHTML = `
      <div class="step-label">${meta.icon} ${meta.label}</div>
      <div class="step-content">검색어: ${escapeHtml(queryPreview || "질문 내용 기반 검색")}</div>
    `;
  }

  if (type === "tool_result") {
    const meta = TOOL_META[data.tool] || TOOL_META.unknown;
    const result = String(data.content || "").replace(/\s+/g, " ").trim();
    const resultPreview = result.length > 260 ? `${result.slice(0, 260)}...` : result;
    div.innerHTML = `
      <div class="step-label">${meta.icon} 자료 확인 완료</div>
      <div class="step-content">${escapeHtml(resultPreview || `${meta.label} 결과를 답변에 반영합니다.`)}</div>
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

  if (isRunning) {
    agentPanelEl.open = true;
  }
}

function setSidebarView(view) {
  document.querySelectorAll(".sidebar-view").forEach((element) => {
    element.classList.toggle("active", element.id === `${view}-sidebar-view`);
  });

  activityButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.sidebarView === view);
  });

  sideTitleEl.textContent = view === "files" ? "탐색기" : "대화 기록";
}

function setUploadStatus(message, type = "") {
  uploadStatusEl.textContent = message;
  uploadStatusEl.className = type;
}

function countTreeFiles(nodes) {
  return nodes.reduce(
    (count, node) => count + (node.type === "file" ? 1 : countTreeFiles(node.children || [])),
    0,
  );
}

function findFirstFile(nodes) {
  for (const node of nodes) {
    if (node.type === "file") return node;
    const child = findFirstFile(node.children || []);
    if (child) return child;
  }
  return null;
}

function treeHasFile(nodes, path) {
  return nodes.some(
    (node) =>
      (node.type === "file" && node.path === path) ||
      (node.type === "directory" && treeHasFile(node.children || [], path)),
  );
}

function renderProjectPicker() {
  projectPickerEl.innerHTML = "";

  if (projects.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "업로드된 프로젝트 없음";
    projectPickerEl.appendChild(option);
    projectPickerEl.disabled = true;
    deleteProjectBtn.disabled = true;
    return;
  }

  projectPickerEl.disabled = false;
  deleteProjectBtn.disabled = false;
  projects.forEach((project) => {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = `${project.name} (${project.file_count})`;
    option.selected = project.id === currentProjectId;
    projectPickerEl.appendChild(option);
  });
}

function resetEditor() {
  currentFilePath = null;
  editorEmptyEl.hidden = false;
  codeViewEl.hidden = true;
  codeViewEl.innerHTML = "";
  editorProjectNameEl.textContent = "프로젝트를 열어주세요";
  editorLanguageEl.textContent = "TEXT";
  editorTabsEl.innerHTML = '<div class="editor-tab muted">열린 파일 없음</div>';
  editorFileStatusEl.textContent = "파일 없음";
  editorLineStatusEl.textContent = "Ln 1, Col 1";
  projectFileCountEl.textContent = "0";
  fileTreeEl.innerHTML = '<div class="sidebar-empty">ZIP 프로젝트를 업로드하면 파일 목록이 표시됩니다.</div>';
}

async function deleteCurrentProject() {
  const project = projects.find((item) => item.id === currentProjectId);
  if (!project) return;

  if (!window.confirm(`“${project.name}” 프로젝트와 업로드된 파일을 모두 삭제할까요?`)) return;

  deleteProjectBtn.disabled = true;

  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error("프로젝트 삭제 요청이 실패했습니다.");

    currentProjectId = null;
    currentFilePath = null;
    localStorage.removeItem(ACTIVE_PROJECT_KEY);
    localStorage.removeItem(ACTIVE_FILE_KEY);
    resetEditor();
    setUploadStatus("프로젝트를 삭제했습니다.", "success");
    await loadProjects();
  } catch (error) {
    console.error(error);
    setUploadStatus("프로젝트를 삭제하지 못했습니다.", "error");
    deleteProjectBtn.disabled = false;
  }
}

function renderFileTree(nodes) {
  fileTreeEl.innerHTML = "";
  const fragment = document.createDocumentFragment();

  function appendNodes(items, parent, depth) {
    items.forEach((node) => {
      if (node.type === "directory") {
        const wrapper = document.createElement("div");
        const button = document.createElement("button");
        const children = document.createElement("div");

        button.type = "button";
        button.className = "tree-node";
        button.style.paddingLeft = `${8 + depth * 14}px`;
        button.innerHTML = `<span class="tree-icon">⌄</span><span>${escapeHtml(node.name)}</span>`;
        children.className = "tree-children";

        button.onclick = () => {
          const collapsed = children.classList.toggle("collapsed");
          button.querySelector(".tree-icon").textContent = collapsed ? "›" : "⌄";
        };

        wrapper.appendChild(button);
        appendNodes(node.children || [], children, depth + 1);
        wrapper.appendChild(children);
        parent.appendChild(wrapper);
        return;
      }

      const button = document.createElement("button");
      button.type = "button";
      button.className = `tree-node ${node.path === currentFilePath ? "active" : ""}`;
      button.dataset.filePath = node.path;
      button.style.paddingLeft = `${8 + depth * 14}px`;
      button.innerHTML = `<span class="tree-icon">◇</span><span>${escapeHtml(node.name)}</span>`;
      button.onclick = () => openProjectFile(node.path);
      parent.appendChild(button);
    });
  }

  appendNodes(nodes, fragment, 0);
  fileTreeEl.appendChild(fragment);
}

function renderCodeFile(file) {
  editorEmptyEl.hidden = true;
  codeViewEl.hidden = false;
  codeViewEl.innerHTML = "";

  const lines = file.content.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const fragment = document.createDocumentFragment();

  lines.forEach((line, index) => {
    const row = document.createElement("div");
    const number = document.createElement("span");
    const content = document.createElement("span");

    row.className = "code-line";
    row.dataset.line = String(index + 1);
    number.className = "line-number";
    number.textContent = String(index + 1);
    content.className = "line-content";
    content.textContent = line || " ";

    row.append(number, content);
    fragment.appendChild(row);
  });

  codeViewEl.appendChild(fragment);
  editorTabsEl.innerHTML = `<div class="editor-tab">${escapeHtml(file.name)}</div>`;
  editorLanguageEl.textContent = file.language.toUpperCase();
  editorFileStatusEl.textContent = `${file.path} · ${file.line_count} lines`;
  editorLineStatusEl.textContent = "Ln 1, Col 1";
}

async function openProjectFile(path) {
  if (!currentProjectId || !path) return;

  try {
    editorFileStatusEl.textContent = "파일을 여는 중...";
    const response = await fetch(
      `/api/projects/${encodeURIComponent(currentProjectId)}/file?path=${encodeURIComponent(path)}`,
    );

    if (!response.ok) throw new Error("파일을 불러오지 못했습니다.");

    const file = await response.json();
    currentFilePath = file.path;
    localStorage.setItem(ACTIVE_FILE_KEY, currentFilePath);
    renderCodeFile(file);

    document.querySelectorAll(".tree-node[data-file-path]").forEach((button) => {
      button.classList.toggle("active", button.dataset.filePath === currentFilePath);
    });
  } catch (error) {
    console.error(error);
    editorFileStatusEl.textContent = "파일 열기 실패";
  }
}

async function loadProject(projectId, preferredFile = null) {
  if (!projectId) return;

  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");

    const data = await response.json();
    currentProjectId = data.project.id;
    localStorage.setItem(ACTIVE_PROJECT_KEY, currentProjectId);
    editorProjectNameEl.textContent = data.project.name;
    projectFileCountEl.textContent = String(countTreeFiles(data.tree));
    renderProjectPicker();
    renderFileTree(data.tree);

    const firstFile = findFirstFile(data.tree);
    const fileToOpen = preferredFile && treeHasFile(data.tree, preferredFile)
      ? preferredFile
      : firstFile?.path;
    if (fileToOpen) await openProjectFile(fileToOpen);
  } catch (error) {
    console.error(error);
    setUploadStatus("프로젝트를 불러오지 못했습니다.", "error");
  }
}

async function loadProjects() {
  try {
    const response = await fetch("/api/projects");
    if (!response.ok) throw new Error("프로젝트 목록을 불러오지 못했습니다.");

    const data = await response.json();
    projects = data.projects || [];
    const storedProjectId = localStorage.getItem(ACTIVE_PROJECT_KEY);
    currentProjectId = projects.some((project) => project.id === storedProjectId)
      ? storedProjectId
      : projects[0]?.id || null;
    renderProjectPicker();

    if (currentProjectId) {
      await loadProject(currentProjectId, localStorage.getItem(ACTIVE_FILE_KEY));
    } else {
      resetEditor();
    }
  } catch (error) {
    console.error(error);
    setUploadStatus("프로젝트 목록을 불러오지 못했습니다.", "error");
  }
}

async function uploadProject(file) {
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);
  setUploadStatus("프로젝트를 업로드하고 있습니다...");
  projectUploadEl.disabled = true;

  try {
    const response = await fetch("/api/projects", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || data.message || "프로젝트 업로드에 실패했습니다.");
    }

    setUploadStatus(`${data.project.file_count}개 파일을 불러왔습니다.`, "success");
    currentProjectId = data.project.id;
    currentFilePath = null;
    localStorage.setItem(ACTIVE_PROJECT_KEY, currentProjectId);
    localStorage.removeItem(ACTIVE_FILE_KEY);
    await loadProjects();
  } catch (error) {
    console.error(error);
    setUploadStatus(error.message, "error");
  } finally {
    projectUploadEl.disabled = false;
    projectUploadEl.value = "";
  }
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
      agentStatusEl.textContent = "입력 확인 중";
    }

    if (data.type === "progress") {
      const stageLabels = {
        context: "대화 맥락 확인",
        reasoning: "질문 유형 분석",
        tools: "검색 자료 정리",
        stackoverflow_fallback: "보완 사례 검색",
        final_answer: "최종 답변 구성",
      };
      data.stage_label = stageLabels[data.stage] || "분석 진행";
      showRequestStep(requestState, "progress", data);
      agentStatusEl.textContent = data.stage_label;
    }

    if (data.type === "input_masked") {
      showRequestStep(requestState, "input_masked", data);

      if (data.masked_question) {
        replaceLastUserMessage(requestSessionId, data.masked_question);
      }
    }

    if (data.type === "tool_call") {
      showRequestStep(requestState, "tool_call", data);
      agentStatusEl.textContent = `${(TOOL_META[data.tool] || TOOL_META.unknown).label} 중`;
    }

    if (data.type === "tool_result") {
      showRequestStep(requestState, "tool_result", data);
      agentStatusEl.textContent = "검색 결과 정리 중";
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

activityButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setSidebarView(button.dataset.sidebarView);
  });
});

projectUploadEl.addEventListener("change", () => {
  uploadProject(projectUploadEl.files?.[0]);
});

projectPickerEl.addEventListener("change", () => {
  currentFilePath = null;
  localStorage.removeItem(ACTIVE_FILE_KEY);
  loadProject(projectPickerEl.value);
});

deleteProjectBtn.addEventListener("click", () => {
  deleteCurrentProject();
});

document.querySelectorAll(".quick-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    inputEl.value = btn.textContent.trim();
    inputEl.focus();
  });
});

loadSessions();
loadProjects();
