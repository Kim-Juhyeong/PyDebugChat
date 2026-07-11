const STORAGE_KEY = "python-debug-assistant.sessions";
const ACTIVE_SESSION_KEY = "python-debug-assistant.active-session";
const ACTIVE_PROJECT_KEY = "python-debug-assistant.active-project";
const ACTIVE_FILE_KEY = "python-debug-assistant.active-file";
const SIMPLE_CODE_LIMIT = 6000;

const TOOL_META = {
  project_code_search: { icon: "⌕", label: "프로젝트 코드 검색" },
  python_docs_search: { icon: "▤", label: "Python 공식문서 검색" },
  python_error_search: { icon: "⚠", label: "Python 오류 검색" },
  stackoverflow_search: { icon: "◈", label: "Stack Overflow 검색" },
  web_search: { icon: "◎", label: "웹 검색" },
  unknown: { icon: "◇", label: "자료 검색" },
};

let sessions = [];
let projects = [];
let currentSessionId = null;
let currentProjectId = null;
let currentFilePath = null;
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
const agentPanelEl = document.getElementById("agent-panel");
const modelCallsEl = document.getElementById("model-calls");
const toolCallsEl = document.getElementById("tool-calls");
const totalCallsEl = document.getElementById("total-calls");

const activityButtons = document.querySelectorAll(".activity-btn[data-sidebar-view]");
const sideTitleEl = document.getElementById("side-title");
const projectUploadEl = document.getElementById("project-upload");
const uploadStatusEl = document.getElementById("upload-status");
const projectCountEl = document.getElementById("project-count");
const projectListEl = document.getElementById("project-list");
const projectFileCountEl = document.getElementById("project-file-count");
const fileTreeEl = document.getElementById("file-tree");

const editorProjectNameEl = document.getElementById("editor-project-name");
const editorLanguageEl = document.getElementById("editor-language");
const editorTabsEl = document.getElementById("editor-tabs");
const editorEmptyEl = document.getElementById("editor-empty");
const simpleCodeEditorEl = document.getElementById("simple-code-editor");
const codeViewEl = document.getElementById("code-view");
const editorFileStatusEl = document.getElementById("editor-file-status");
const editorLineStatusEl = document.getElementById("editor-line-status");

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function createId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso() {
  return new Date().toISOString();
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

function getSession(sessionId) {
  return sessions.find((session) => session.id === sessionId);
}

function getCurrentSession() {
  return getSession(currentSessionId);
}

function saveSessions() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    if (currentSessionId) localStorage.setItem(ACTIVE_SESSION_KEY, currentSessionId);
  } catch (error) {
    console.warn("디버깅 작업을 브라우저에 저장하지 못했습니다.", error);
  }
}

function loadSessions() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    sessions = Array.isArray(stored)
      ? stored
          .filter((session) => session && typeof session.id === "string")
          .map((session) => ({
            id: session.id,
            mode: session.mode === "project" ? "project" : "simple",
            projectId: session.projectId || null,
            title: typeof session.title === "string" ? session.title : "이전 디버깅",
            code: typeof session.code === "string" ? session.code : "",
            language: session.language || "text",
            createdAt: session.createdAt || nowIso(),
            updatedAt: session.updatedAt || session.createdAt || nowIso(),
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

  const storedActiveId = localStorage.getItem(ACTIVE_SESSION_KEY);
  currentSessionId = sessions.some((session) => session.id === storedActiveId)
    ? storedActiveId
    : sessions[0]?.id || null;
}

function createSimpleSession() {
  const session = {
    id: createId(),
    mode: "simple",
    projectId: null,
    title: "새 코드 디버깅",
    code: "",
    language: "text",
    createdAt: nowIso(),
    updatedAt: nowIso(),
    messages: [],
  };
  sessions.unshift(session);
  currentSessionId = session.id;
  saveSessions();
  selectSimpleSession(session.id);
  return session;
}

function ensureProjectSession(project) {
  const sessionId = `project-${project.id}`;
  let session = getSession(sessionId);
  if (!session) {
    session = {
      id: sessionId,
      mode: "project",
      projectId: project.id,
      title: project.name,
      code: "",
      language: "project",
      createdAt: project.created_at || nowIso(),
      updatedAt: nowIso(),
      messages: [],
    };
    sessions.push(session);
  } else {
    session.mode = "project";
    session.projectId = project.id;
    session.title = project.name;
  }
  return session;
}

function setSidebarView(view) {
  document.querySelectorAll(".sidebar-view").forEach((element) => {
    element.classList.toggle("active", element.id === `${view}-sidebar-view`);
  });
  activityButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.sidebarView === view);
  });
  sideTitleEl.textContent = view === "projects" ? "프로젝트 디버깅" : "단순 코드 디버깅";
}

function renderChatList() {
  const simpleSessions = sessions.filter((session) => session.mode === "simple");
  chatListEl.innerHTML = "";

  if (simpleSessions.length === 0) {
    chatListEl.innerHTML = '<div class="sidebar-empty">단순 코드 디버깅 작업이 없습니다.</div>';
    return;
  }

  simpleSessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = `chat-item ${session.id === currentSessionId ? "active" : ""}`;
    item.innerHTML = `
      <div class="chat-item-title">${escapeHtml(session.title)}</div>
      <div class="chat-item-meta">${escapeHtml(nowTextFromIso(session.updatedAt))}</div>
      <button class="chat-delete" type="button" aria-label="${escapeHtml(session.title)} 삭제" title="디버깅 작업 삭제">×</button>
    `;
    item.onclick = () => selectSimpleSession(session.id);
    item.querySelector(".chat-delete").onclick = (event) => {
      event.stopPropagation();
      deleteSimpleSession(session.id);
    };
    chatListEl.appendChild(item);
  });
}

function renderProjectList() {
  projectListEl.innerHTML = "";
  projectCountEl.textContent = String(projects.length);

  if (projects.length === 0) {
    projectListEl.innerHTML = '<div class="sidebar-empty">업로드한 프로젝트가 없습니다.</div>';
    return;
  }

  projects.forEach((project) => {
    const item = document.createElement("div");
    item.className = `project-item ${project.id === currentProjectId && getCurrentSession()?.mode === "project" ? "active" : ""}`;
    item.innerHTML = `
      <div class="chat-item-title">${escapeHtml(project.name)}</div>
      <div class="chat-item-meta">파일 ${project.file_count}개 · ${escapeHtml(nowTextFromIso(project.created_at))}</div>
      <button class="chat-delete" type="button" aria-label="${escapeHtml(project.name)} 삭제" title="프로젝트와 채팅 삭제">×</button>
    `;
    item.onclick = () => selectProject(project.id);
    item.querySelector(".chat-delete").onclick = (event) => {
      event.stopPropagation();
      deleteProjectWork(project.id);
    };
    projectListEl.appendChild(item);
  });
}

function renderMessages() {
  const session = getCurrentSession();
  if (!session) {
    messagesEl.innerHTML = "";
    return;
  }

  chatTitleEl.textContent = session.title;
  chatSubtitleEl.textContent = session.mode === "project"
    ? "선택 프로젝트의 코드와 연결된 전용 채팅"
    : "중앙 코드 입력창과 연결된 전용 채팅";
  messagesEl.innerHTML = "";

  if (session.messages.length === 0) {
    messagesEl.innerHTML = `
      <div class="empty-state">
        <h3>${session.mode === "project" ? "프로젝트를 함께 살펴볼까요?" : "코드를 입력하고 질문해 보세요"}</h3>
        <p>${session.mode === "project" ? "현재 파일과 프로젝트 전체를 직접 검색해 오류를 분석합니다." : "중앙에 코드를 입력하면 Agent에게 자동으로 전달됩니다."}</p>
      </div>
    `;
    return;
  }

  session.messages.forEach((message) => appendMessageToDOM(message.role, message.content));
  scrollMessagesToBottom();
}

function appendMessageToDOM(role, content) {
  const row = document.createElement("div");
  const bubble = document.createElement("div");
  row.className = `msg-row ${role}`;
  bubble.className = `msg ${role}`;
  bubble.textContent = content;
  row.appendChild(bubble);
  messagesEl.appendChild(row);
}

function appendMessageToSession(sessionId, role, content) {
  const session = getSession(sessionId);
  if (!session) return;
  session.messages.push({ role, content, createdAt: nowIso() });
  session.updatedAt = nowIso();

  if (role === "user" && session.mode === "simple" && session.title === "새 코드 디버깅") {
    session.title = content.replace(/\s+/g, " ").trim().slice(0, 28) || session.title;
  }

  saveSessions();
  renderChatList();
  renderProjectList();

  if (sessionId === currentSessionId) {
    if (messagesEl.querySelector(".empty-state")) messagesEl.innerHTML = "";
    appendMessageToDOM(role, content);
    scrollMessagesToBottom();
  }
}

function replaceLastUserMessage(sessionId, content) {
  const session = getSession(sessionId);
  if (!session) return;
  for (let index = session.messages.length - 1; index >= 0; index -= 1) {
    if (session.messages[index].role === "user") {
      session.messages[index].content = content;
      break;
    }
  }
  saveSessions();
  if (sessionId === currentSessionId) renderMessages();
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

function setRunning(isRunning) {
  sendBtn.disabled = isRunning;
  inputEl.disabled = isRunning;
  agentStatusEl.textContent = isRunning ? "실행 중..." : "대기 중";
  sendBtn.textContent = isRunning ? "실행 중" : "전송";
  if (isRunning) agentPanelEl.open = true;
}

function addStep(type, data) {
  const div = document.createElement("div");
  div.className = `step ${type}`;

  if (type === "start") {
    div.innerHTML = '<div class="step-label">분석 시작</div><div class="step-content">연결된 코드와 이전 대화를 확인하고 있습니다.</div>';
  } else if (type === "progress") {
    div.innerHTML = `<div class="step-label">${escapeHtml(data.stage_label || "분석 진행")}</div><div class="step-content">${escapeHtml(data.message || "다음 단계를 처리하고 있습니다.")}</div>`;
  } else if (type === "input_masked") {
    div.innerHTML = '<div class="step-label">민감 정보 보호</div><div class="step-content">입력에 포함된 민감 정보를 가렸습니다.</div>';
  } else if (type === "tool_call") {
    const meta = TOOL_META[data.tool] || TOOL_META.unknown;
    const args = data.args || {};
    const query = args.query || args.error_message || args.input || JSON.stringify(args);
    const preview = String(query).length > 240 ? `${String(query).slice(0, 240)}...` : String(query);
    div.innerHTML = `<div class="step-label">${meta.icon} ${meta.label}</div><div class="step-content">검색어: ${escapeHtml(preview || "현재 코드 기반 검색")}</div>`;
  } else if (type === "tool_result") {
    const meta = TOOL_META[data.tool] || TOOL_META.unknown;
    const result = String(data.content || "").replace(/\s+/g, " ").trim();
    const preview = result.length > 260 ? `${result.slice(0, 260)}...` : result;
    div.innerHTML = `<div class="step-label">${meta.icon} 자료 확인 완료</div><div class="step-content">${escapeHtml(preview || `${meta.label} 결과를 반영합니다.`)}</div>`;
  } else if (type === "answer") {
    div.innerHTML = '<div class="step-label">답변 작성 완료</div><div class="step-content">원인과 해결 방법을 정리했습니다.</div>';
  } else if (type === "error") {
    div.innerHTML = `<div class="step-label">처리 중단</div><div class="step-content">${escapeHtml(data.message || "오류가 발생했습니다.")}</div>`;
  }

  stepsEl.appendChild(div);
  stepsEl.scrollTop = stepsEl.scrollHeight;
}

function detectCodeLanguage(code) {
  const value = code || "";
  if (/\b(public\s+class|System\.out|private\s+static)\b/.test(value)) return "java";
  if (/#include\s*[<"]|\bstd::|\bcout\s*<</.test(value)) return "cpp";
  if (/\b(def|import|from|print)\b|:\s*(#.*)?$/m.test(value)) return "python";
  return "text";
}

function renderSimpleEditor(session) {
  editorEmptyEl.hidden = true;
  codeViewEl.hidden = true;
  simpleCodeEditorEl.hidden = false;
  simpleCodeEditorEl.value = session.code || "";
  session.language = detectCodeLanguage(session.code);
  editorProjectNameEl.textContent = session.title;
  editorLanguageEl.textContent = session.language.toUpperCase();
  editorTabsEl.innerHTML = '<div class="editor-tab">직접 입력 코드</div>';
  const lines = (session.code || "").split(/\r?\n/).length;
  editorFileStatusEl.textContent = `직접 입력 · ${lines} lines`;
  editorLineStatusEl.textContent = "편집 가능";
}

function resetProjectEditor() {
  currentFilePath = null;
  simpleCodeEditorEl.hidden = true;
  codeViewEl.hidden = true;
  editorEmptyEl.hidden = false;
  codeViewEl.innerHTML = "";
  editorProjectNameEl.textContent = "프로젝트를 열어주세요";
  editorLanguageEl.textContent = "TEXT";
  editorTabsEl.innerHTML = '<div class="editor-tab muted">열린 파일 없음</div>';
  editorFileStatusEl.textContent = "파일 없음";
  editorLineStatusEl.textContent = "Ln 1, Col 1";
  projectFileCountEl.textContent = "0";
  fileTreeEl.innerHTML = '<div class="sidebar-empty">프로젝트를 선택하면 파일 구조가 표시됩니다.</div>';
}

function selectSimpleSession(sessionId) {
  const session = getSession(sessionId);
  if (!session || session.mode !== "simple") return;
  currentSessionId = sessionId;
  setSidebarView("simple");
  saveSessions();
  renderChatList();
  renderProjectList();
  renderMessages();
  renderSimpleEditor(session);
  clearSteps();
}

async function deleteSimpleSession(sessionId) {
  const session = getSession(sessionId);
  if (!session || session.mode !== "simple") return;
  if (activeRequest?.sessionId === sessionId) {
    window.alert("답변 생성이 끝난 후 작업을 삭제해 주세요.");
    return;
  }
  if (!window.confirm(`“${session.title}” 디버깅 작업을 삭제할까요?`)) return;

  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    if (!response.ok) throw new Error("작업 삭제 요청이 실패했습니다.");
    sessions = sessions.filter((item) => item.id !== sessionId);
    const next = sessions.find((item) => item.mode === "simple");
    saveSessions();
    if (next) selectSimpleSession(next.id);
    else createSimpleSession();
  } catch (error) {
    console.error(error);
    window.alert("디버깅 작업을 삭제하지 못했습니다.");
  }
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
  simpleCodeEditorEl.hidden = true;
  codeViewEl.hidden = false;
  codeViewEl.innerHTML = "";
  const fragment = document.createDocumentFragment();
  const lines = file.content.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");

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
  editorLineStatusEl.textContent = "읽기 전용";
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
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
  if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
  const data = await response.json();
  currentProjectId = data.project.id;
  localStorage.setItem(ACTIVE_PROJECT_KEY, currentProjectId);
  editorProjectNameEl.textContent = data.project.name;
  projectFileCountEl.textContent = String(countTreeFiles(data.tree));
  renderProjectList();
  renderFileTree(data.tree);
  const firstFile = findFirstFile(data.tree);
  const fileToOpen = preferredFile && treeHasFile(data.tree, preferredFile)
    ? preferredFile
    : firstFile?.path;
  if (fileToOpen) await openProjectFile(fileToOpen);
}

async function selectProject(projectId, preferredFile = null) {
  const project = projects.find((item) => item.id === projectId);
  if (!project) return;
  const session = ensureProjectSession(project);
  currentSessionId = session.id;
  currentProjectId = project.id;
  setSidebarView("projects");
  saveSessions();
  renderChatList();
  renderMessages();
  clearSteps();
  try {
    await loadProject(project.id, preferredFile || localStorage.getItem(ACTIVE_FILE_KEY));
  } catch (error) {
    console.error(error);
    resetProjectEditor();
    uploadStatusEl.textContent = "프로젝트를 불러오지 못했습니다.";
    uploadStatusEl.className = "error";
  }
}

async function loadProjects() {
  try {
    const response = await fetch("/api/projects");
    if (!response.ok) throw new Error("프로젝트 목록을 불러오지 못했습니다.");
    const data = await response.json();
    projects = data.projects || [];
    projects.forEach(ensureProjectSession);
    sessions = sessions.filter(
      (session) => session.mode !== "project" || projects.some((project) => project.id === session.projectId),
    );
    renderProjectList();
    renderChatList();

    let active = getCurrentSession();
    if (active?.mode === "project" && projects.some((project) => project.id === active.projectId)) {
      await selectProject(active.projectId);
    } else {
      active = active?.mode === "simple" ? active : sessions.find((session) => session.mode === "simple");
      if (active) selectSimpleSession(active.id);
      else if (projects.length > 0) await selectProject(projects[0].id);
      else createSimpleSession();
    }
    saveSessions();
  } catch (error) {
    console.error(error);
    uploadStatusEl.textContent = "프로젝트 목록을 불러오지 못했습니다.";
    uploadStatusEl.className = "error";
  }
}

async function uploadProject(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  uploadStatusEl.textContent = "프로젝트를 업로드하고 있습니다...";
  uploadStatusEl.className = "";
  projectUploadEl.disabled = true;

  try {
    const response = await fetch("/api/projects", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.message || "프로젝트 업로드에 실패했습니다.");
    uploadStatusEl.textContent = `${data.project.file_count}개 파일을 불러왔습니다.`;
    uploadStatusEl.className = "success";
    currentSessionId = `project-${data.project.id}`;
    localStorage.setItem(ACTIVE_PROJECT_KEY, data.project.id);
    localStorage.removeItem(ACTIVE_FILE_KEY);
    await loadProjects();
  } catch (error) {
    console.error(error);
    uploadStatusEl.textContent = error.message;
    uploadStatusEl.className = "error";
  } finally {
    projectUploadEl.disabled = false;
    projectUploadEl.value = "";
  }
}

async function deleteProjectWork(projectId) {
  const project = projects.find((item) => item.id === projectId);
  if (!project) return;
  const sessionId = `project-${project.id}`;
  if (activeRequest?.sessionId === sessionId) {
    window.alert("답변 생성이 끝난 후 프로젝트를 삭제해 주세요.");
    return;
  }
  if (!window.confirm(`“${project.name}” 프로젝트와 연결된 채팅을 모두 삭제할까요?`)) return;

  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.id)}`, { method: "DELETE" });
    if (!response.ok) throw new Error("프로젝트 삭제 요청이 실패했습니다.");
    projects = projects.filter((item) => item.id !== project.id);
    sessions = sessions.filter((session) => session.id !== sessionId);
    localStorage.removeItem(ACTIVE_PROJECT_KEY);
    localStorage.removeItem(ACTIVE_FILE_KEY);
    saveSessions();
    renderProjectList();

    if (projects.length > 0) await selectProject(projects[0].id);
    else {
      resetProjectEditor();
      const simple = sessions.find((session) => session.mode === "simple");
      if (simple) selectSimpleSession(simple.id);
      else createSimpleSession();
    }
  } catch (error) {
    console.error(error);
    window.alert("프로젝트를 삭제하지 못했습니다.");
  }
}

function showRequestStep(requestState, type, data) {
  if (requestState.sessionId === currentSessionId) addStep(type, data);
}

function finishRequest(requestState) {
  if (!requestState || requestState.finished) return false;
  requestState.finished = true;
  requestState.source.close();
  if (activeRequest === requestState) {
    activeRequest = null;
    setRunning(false);
  }
  return true;
}

function sendMessage() {
  const message = inputEl.value.trim();
  const session = getCurrentSession();
  if (!message || !session) return;

  const requestSessionId = session.id;
  appendMessageToSession(requestSessionId, "user", message);
  inputEl.value = "";
  clearSteps();
  setRunning(true);

  if (activeRequest) {
    activeRequest.finished = true;
    activeRequest.source.close();
  }

  const params = new URLSearchParams({
    session_id: requestSessionId,
    question: message,
  });

  if (session.mode === "project") {
    params.set("project_id", session.projectId);
    if (currentFilePath) params.set("file_path", currentFilePath);
  } else if (session.code.trim()) {
    params.set("code", session.code.slice(0, SIMPLE_CODE_LIMIT));
    params.set("language", session.language || detectCodeLanguage(session.code));
  }

  const source = new EventSource(`/api/agent/stream?${params.toString()}`);
  const requestState = {
    source,
    sessionId: requestSessionId,
    finished: false,
    finalAnswer: "",
  };
  activeRequest = requestState;

  source.onmessage = (event) => {
    if (activeRequest !== requestState || requestState.finished) return;
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      appendMessageToSession(requestSessionId, "assistant", "서버 응답 형식에 문제가 발생했습니다.");
      finishRequest(requestState);
      return;
    }

    if (data.type === "start") {
      showRequestStep(requestState, "start", data);
      agentStatusEl.textContent = "연결 코드 확인 중";
    } else if (data.type === "progress") {
      const labels = {
        context: "코드·대화 맥락 확인",
        reasoning: "질문 유형 분석",
        tools: "검색 자료 정리",
        stackoverflow_fallback: "보완 사례 검색",
        final_answer: "최종 답변 구성",
      };
      data.stage_label = labels[data.stage] || "분석 진행";
      showRequestStep(requestState, "progress", data);
      agentStatusEl.textContent = data.stage_label;
    } else if (data.type === "input_masked") {
      showRequestStep(requestState, "input_masked", data);
      if (data.masked_question) replaceLastUserMessage(requestSessionId, data.masked_question);
    } else if (data.type === "tool_call") {
      showRequestStep(requestState, "tool_call", data);
      agentStatusEl.textContent = `${(TOOL_META[data.tool] || TOOL_META.unknown).label} 중`;
    } else if (data.type === "tool_result") {
      showRequestStep(requestState, "tool_result", data);
      agentStatusEl.textContent = "검색 결과 정리 중";
    } else if (data.type === "answer") {
      requestState.finalAnswer = data.content || requestState.finalAnswer;
      showRequestStep(requestState, "answer", data);
    } else if (data.type === "done") {
      if (!finishRequest(requestState)) return;
      if (data.usage && requestSessionId === currentSessionId) {
        modelCallsEl.textContent = data.usage.model_calls ?? 0;
        toolCallsEl.textContent = data.usage.tool_calls ?? 0;
        totalCallsEl.textContent = data.usage.total_calls ?? 0;
      }
      appendMessageToSession(
        requestSessionId,
        "assistant",
        requestState.finalAnswer || data.answer || "답변을 생성하지 못했습니다. 다시 질문해 주세요.",
      );
      if (requestSessionId === currentSessionId) agentStatusEl.textContent = "완료";
    } else if (data.type === "error") {
      if (!finishRequest(requestState)) return;
      showRequestStep(requestState, "error", data);
      appendMessageToSession(requestSessionId, "assistant", `오류가 발생했습니다.\n\n${data.message || "알 수 없는 오류"}`);
      if (requestSessionId === currentSessionId) agentStatusEl.textContent = "오류";
    }
  };

  source.onerror = () => {
    if (activeRequest !== requestState || requestState.finished) return;
    if (!finishRequest(requestState)) return;
    showRequestStep(requestState, "error", { message: "서버 연결이 종료되었습니다." });
    appendMessageToSession(requestSessionId, "assistant", "서버와의 연결 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.");
    if (requestSessionId === currentSessionId) agentStatusEl.textContent = "연결 오류";
  };
}

simpleCodeEditorEl.addEventListener("input", () => {
  const session = getCurrentSession();
  if (!session || session.mode !== "simple") return;
  session.code = simpleCodeEditorEl.value;
  session.language = detectCodeLanguage(session.code);
  session.updatedAt = nowIso();
  editorLanguageEl.textContent = session.language.toUpperCase();
  editorFileStatusEl.textContent = `직접 입력 · ${session.code.split(/\r?\n/).length} lines`;
  saveSessions();
});

newChatBtn.addEventListener("click", createSimpleSession);
sendBtn.addEventListener("click", sendMessage);
inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.ctrlKey) sendMessage();
});
clearStepsBtn.addEventListener("click", clearSteps);
activityButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const view = button.dataset.sidebarView;
    setSidebarView(view);
    if (view === "simple") {
      const simple = getCurrentSession()?.mode === "simple"
        ? getCurrentSession()
        : sessions.find((session) => session.mode === "simple");
      if (simple) selectSimpleSession(simple.id);
      else createSimpleSession();
    } else if (projects.length > 0) {
      const projectId = getCurrentSession()?.mode === "project"
        ? getCurrentSession().projectId
        : currentProjectId || projects[0].id;
      selectProject(projectId);
    } else {
      resetProjectEditor();
      renderProjectList();
    }
  });
});
projectUploadEl.addEventListener("change", () => uploadProject(projectUploadEl.files?.[0]));
document.querySelectorAll(".quick-btn").forEach((button) => {
  button.addEventListener("click", () => {
    inputEl.value = button.textContent.trim();
    inputEl.focus();
  });
});

loadSessions();
loadProjects();
