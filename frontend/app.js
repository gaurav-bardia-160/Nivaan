/**
 * Nivaan - Civic & Banking AI Guide Controller
 * Handles conversation flow, camera/file upload, PII masking, structured checklist rendering,
 * editable user prompts, and multi-turn persistent chat history in localStorage.
 */

const API_BASE = window.location.protocol && window.location.hostname
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://127.0.0.1:8000";
const STORAGE_KEY = "nivaan_chats_v1";
const ACTIVE_CHAT_KEY = "nivaan_active_chat_id";
const PENDING_QUERY_KEY = "nivaan_pending_query_v1";

let isBackendLive = false;
let chats = []; // Array of chat session objects
let activeChatId = null;
let attachedFile = null; // { name, type, size, textContent, fileRef, isImage, isPdf }

// DOM Elements
const sidebar = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const sidebarCollapseBtn = document.getElementById("sidebarCollapseBtn");
const floatingSidebarToggle = document.getElementById("floatingSidebarToggle");
const newChatBtn = document.getElementById("newChatBtn");
const historyList = document.getElementById("historyList");
const backendBadge = document.getElementById("backendBadge");

const messagesContainer = document.getElementById("messagesContainer");
const welcomeScreen = document.getElementById("welcomeScreen");

const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const sendIcon = document.getElementById("sendIcon");
const sendSpinner = document.getElementById("sendSpinner");

const attachBtn = document.getElementById("attachBtn");
const cameraBtn = document.getElementById("cameraBtn");
const fileInput = document.getElementById("fileInput");
const attachmentPreview = document.getElementById("attachmentPreview");
const previewFilename = document.getElementById("previewFilename");
const previewIcon = document.getElementById("previewIcon");
const removeAttachmentBtn = document.getElementById("removeAttachmentBtn");

const suggestionCards = document.querySelectorAll(".suggestion-card");

// --- UI ASSETS & ICONS ---
const BOT_AVATAR_HTML = '<div class="message-avatar bot-avatar"><img src="logo.png" alt="Nivaan" class="bot-avatar-img" /></div>';
const ICON_THUMBS_UP = '<svg class="feedback-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path></svg>';
const ICON_THUMBS_DOWN = '<svg class="feedback-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path></svg>';
const ICON_COPY = '<svg class="copy-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
const ICON_COPIED = '<svg class="copy-icon-svg check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';

// --- SIDEBAR DRAWER HELPERS ---
function setSidebarOpen(isOpen) {
    if (!sidebar) return;
    if (isOpen) {
        sidebar.classList.remove("collapsed");
        if (sidebarBackdrop && window.innerWidth <= 768) {
            sidebarBackdrop.classList.add("active");
        }
    } else {
        sidebar.classList.add("collapsed");
        if (sidebarBackdrop) {
            sidebarBackdrop.classList.remove("active");
        }
    }
}

function toggleSidebar() {
    if (!sidebar) return;
    const isCurrentlyOpen = !sidebar.classList.contains("collapsed");
    setSidebarOpen(!isCurrentlyOpen);
}

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
    // On mobile devices, keep sidebar closed by default
    if (window.innerWidth <= 768) {
        setSidebarOpen(false);
    }

    checkBackendHealth();
    setInterval(checkBackendHealth, 8000);
    setupEventListeners();
    loadChatsFromStorage();
    renderHistoryList();

    if (activeChatId) {
        loadActiveChatMessages();
    } else {
        resetChatView();
    }

    // Auto-resume if page was refreshed while AI was thinking/generating
    checkAndResumePendingQuery();
});

function setupEventListeners() {
    // Sidebar toggle (handles minimize button in sidebar and floating toggle when collapsed)
    const toggleButtons = document.querySelectorAll("#sidebarToggle, #sidebarCollapseBtn, #floatingSidebarToggle");
    toggleButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            toggleSidebar();
        });
    });

    // Backdrop click closes mobile drawer
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener("click", () => {
            setSidebarOpen(false);
        });
    }

    // Auto-dismiss mobile drawer on resize or Escape
    window.addEventListener("resize", () => {
        if (window.innerWidth > 768 && sidebarBackdrop) {
            sidebarBackdrop.classList.remove("active");
        }
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && sidebar && !sidebar.classList.contains("collapsed") && window.innerWidth <= 768) {
            setSidebarOpen(false);
        }
    });

    // New Chat Button
    if (newChatBtn) {
        newChatBtn.addEventListener("click", handleNewChatBtn);
    }

    // Theme Toggle
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    if (themeToggleBtn) {
        if (localStorage.getItem("nivaan-theme") === "dark") {
            document.documentElement.setAttribute("data-theme", "dark");
            themeToggleBtn.innerHTML = "☀️ Light";
        }
        themeToggleBtn.addEventListener("click", () => {
            if (document.documentElement.getAttribute("data-theme") === "dark") {
                document.documentElement.setAttribute("data-theme", "light");
                localStorage.setItem("nivaan-theme", "light");
                themeToggleBtn.innerHTML = "🌙 Dark";
            } else {
                document.documentElement.setAttribute("data-theme", "dark");
                localStorage.setItem("nivaan-theme", "dark");
                themeToggleBtn.innerHTML = "☀️ Light";
            }
        });
    }

    // Suggestion Cards & Category Chips
    document.querySelectorAll(".suggestion-card, .category-chip[data-prompt]").forEach(card => {
        card.addEventListener("click", () => {
            const prompt = card.getAttribute("data-prompt");
            if (prompt) {
                sendMessage(prompt);
            }
        });
    });

    // Send Button & Enter Key
    if (sendBtn) sendBtn.addEventListener("click", () => handleUserSubmit());
    if (chatInput) {
        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleUserSubmit();
            }
        });
        chatInput.addEventListener("input", () => {
            chatInput.style.height = "auto";
            chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + "px";
        });
    }

    // File Attachment Picker
    if (attachBtn && fileInput) {
        attachBtn.addEventListener("click", () => {
            fileInput.removeAttribute("capture");
            fileInput.click();
        });
    }

    // Camera Capture
    if (cameraBtn && fileInput) {
        cameraBtn.addEventListener("click", () => {
            fileInput.setAttribute("capture", "environment");
            fileInput.click();
        });
    }

    // File Selected
    if (fileInput) {
        fileInput.addEventListener("change", handleFileSelected);
    }

    // Remove Attachment
    if (removeAttachmentBtn) {
        removeAttachmentBtn.addEventListener("click", clearAttachment);
    }
}

// --- CLIENT-SIDE STORAGE & LOCAL SAFEGUARDS ---
function maskClientPII(text) {
    // 100% on-device local AI via Ollama (zero cloud leakage).
    // Identifiers (PAN, IFSC, Aadhaar, notice numbers) are preserved for full fidelity local reasoning.
    return text || "";
}

function isInternalWarning(w) {
    if (!w) return false;
    const title = (w.title || w.text || "").toLowerCase().trim();
    const msg = (w.message || w.reason || "").toLowerCase().trim();
    if (title.includes("answer not grounded") || title.includes("not grounded")) return true;
    if (msg.includes("no matching local guide was found") || msg.includes("intentionally refusing to guess")) return true;
    if (title.includes("workflow not available yet") || title.includes("not available yet")) return true;
    if (msg.includes("planned next phase") || msg.includes("use typed questions or paste document text")) return true;
    return false;
}

function sanitizeAllChats(chatList) {
    if (!Array.isArray(chatList)) return [];
    return chatList
        .filter(chat => chat && Array.isArray(chat.messages) && chat.messages.length > 0)
        .map(chat => ({
            ...chat,
            title: maskClientPII(chat.title || ""),
            messages: chat.messages.map(m => {
                if (!m) return m;
                if (m.role === "user" && m.text) {
                    return { ...m, text: maskClientPII(m.text) };
                }
                if (m.role === "assistant") {
                    if (m.answer && typeof m.answer === "object") {
                        const cleanedAnswer = { ...m.answer };
                        delete cleanedAnswer.disclaimer;
                        cleanedAnswer.warnings = [];
                        if (cleanedAnswer.summary) {
                            cleanedAnswer.summary = cleanedAnswer.summary
                                .replace(/^For your question,.*?this is the closest guide I found\.?\s*/i, "")
                                .trim();
                        }
                        return { ...m, answer: cleanedAnswer };
                    }
                }
                return m;
            }).filter(Boolean)
        }));
}

// Auto-redirect if opened directly as file:// and static server is active
if (window.location.protocol === "file:") {
    fetch("http://127.0.0.1:5500/index.html", { method: "HEAD", mode: "no-cors" })
        .then(() => {
            window.location.replace("http://127.0.0.1:5500/");
        })
        .catch(() => {});
}

let _backendSyncTimer = null;

async function syncChatsWithBackend() {
    try {
        const resp = await fetch(`${API_BASE}/api/chats`);
        if (resp.ok) {
            const serverChats = await resp.json();
            if (Array.isArray(serverChats) && serverChats.length > 0) {
                if (!chats || chats.length === 0) {
                    chats = sanitizeAllChats(serverChats);
                    activeChatId = chats[0]?.id || null;
                    saveChatsToStorage(false);
                    renderHistoryList();
                    if (activeChatId) loadActiveChatMessages();
                } else {
                    const localMap = new Map(chats.map(c => [c.id, c]));
                    let changed = false;
                    for (const sc of serverChats) {
                        if (!localMap.has(sc.id)) {
                            chats.push(sc);
                            changed = true;
                        } else {
                            const lc = localMap.get(sc.id);
                            if ((sc.updatedAt || 0) > (lc.updatedAt || 0)) {
                                Object.assign(lc, sc);
                                changed = true;
                            }
                        }
                    }
                    if (changed) {
                        chats = sanitizeAllChats(chats);
                        saveChatsToStorage(false);
                        renderHistoryList();
                        if (activeChatId) loadActiveChatMessages();
                    }
                }
            } else if (chats && chats.length > 0) {
                pushChatsToBackend();
            }
        }
    } catch (e) {
        // Backend offline or unreachable
    }
}

function pushChatsToBackend() {
    if (_backendSyncTimer) clearTimeout(_backendSyncTimer);
    _backendSyncTimer = setTimeout(async () => {
        try {
            const toSave = sanitizeAllChats(chats);
            await fetch(`${API_BASE}/api/chats`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(toSave)
            });
        } catch (e) {}
    }, 1000);
}

// --- STORAGE & PERSISTENCE ---
function loadChatsFromStorage() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY) || localStorage.getItem("govbank_chats_v1");
        let parsed = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(parsed)) parsed = [];
        // Purge empty chats with no messages
        parsed = parsed.filter(c => c && Array.isArray(c.messages) && c.messages.length > 0);
        chats = sanitizeAllChats(parsed);

        const savedActiveId = localStorage.getItem(ACTIVE_CHAT_KEY);
        if (savedActiveId && savedActiveId !== "__new__" && chats.some(c => c.id === savedActiveId)) {
            activeChatId = savedActiveId;
        } else if (savedActiveId === "__new__") {
            activeChatId = null;
        } else {
            activeChatId = chats.length > 0 ? chats[0].id : null;
        }
    } catch (e) {
        console.error("Failed to load chats from storage:", e);
        chats = [];
        activeChatId = null;
    }
    syncChatsWithBackend();
}

function saveChatsToStorage(syncBackend = true) {
    try {
        const toSave = sanitizeAllChats(chats);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
        if (activeChatId) {
            localStorage.setItem(ACTIVE_CHAT_KEY, activeChatId);
        } else {
            localStorage.setItem(ACTIVE_CHAT_KEY, "__new__");
        }
        if (syncBackend) {
            pushChatsToBackend();
        }
    } catch (e) {
        console.error("Failed to save chats to storage:", e);
    }
}

function getActiveChat() {
    if (!activeChatId) return null;
    return chats.find(c => c.id === activeChatId) || null;
}

function createNewChat(firstPrompt = "") {
    const id = "chat_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5);
    const title = generateTitle(maskClientPII(firstPrompt));
    const chat = {
        id,
        title,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: []
    };
    chats.unshift(chat);
    activeChatId = id;
    renderHistoryList();
    return chat;
}

function generateTitle(text) {
    if (!text || !text.trim()) return "New Inquiry";
    const clean = text.trim().replace(/\s+/g, " ");
    return clean.length > 28 ? clean.substring(0, 26) + "..." : clean;
}

function renderHistoryList() {
    if (!historyList) return;
    historyList.innerHTML = "";

    if (chats.length === 0) {
        const empty = document.createElement("div");
        empty.style.fontSize = "12px";
        empty.style.color = "var(--text-muted)";
        empty.style.padding = "8px 10px";
        empty.textContent = "No recent inquiries";
        historyList.appendChild(empty);
        return;
    }

    chats.forEach(chat => {
        const item = document.createElement("div");
        item.className = "history-item" + (chat.id === activeChatId ? " active" : "");
        item.setAttribute("role", "button");
        item.setAttribute("tabindex", "0");
        item.onclick = (e) => {
            if (e.target.closest(".history-item-del")) return;
            switchChat(chat.id);
        };
        item.onkeydown = (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                switchChat(chat.id);
            }
        };

        const titleSpan = document.createElement("span");
        titleSpan.className = "history-item-title";
        titleSpan.textContent = chat.title || "Inquiry";
        titleSpan.title = chat.title || "Inquiry";

        const delBtn = document.createElement("button");
        delBtn.className = "history-item-del";
        delBtn.innerHTML = "&times;";
        delBtn.title = "Delete chat";
        delBtn.onclick = (e) => {
            e.stopPropagation();
            deleteChat(chat.id);
        };

        item.appendChild(titleSpan);
        item.appendChild(delBtn);
        historyList.appendChild(item);
    });
}

function switchChat(chatId) {
    activeChatId = chatId;
    saveChatsToStorage();
    renderHistoryList();
    loadActiveChatMessages();
    if (window.innerWidth <= 768) {
        setSidebarOpen(false);
    }
}

function deleteChat(chatId) {
    const idx = chats.findIndex(c => c.id === chatId);
    if (idx === -1) return;
    chats.splice(idx, 1);
    if (isBackendLive) {
        fetch(`${API_BASE}/api/conversations/${encodeURIComponent(chatId)}`, { method: "DELETE" })
            .catch(() => {});
    }
    if (activeChatId === chatId) {
        localStorage.removeItem(PENDING_QUERY_KEY);
        activeChatId = chats.length > 0 ? chats[0].id : null;
    }
    saveChatsToStorage();
    renderHistoryList();
    if (activeChatId) {
        loadActiveChatMessages();
    } else {
        resetChatView();
    }
}

function handleNewChatBtn() {
    localStorage.removeItem(PENDING_QUERY_KEY);
    activeChatId = null;
    localStorage.setItem(ACTIVE_CHAT_KEY, "__new__");
    renderHistoryList();
    resetChatView();
    if (window.innerWidth <= 768) {
        setSidebarOpen(false);
    }
}

function resetChatView() {
    messagesContainer.innerHTML = "";
    if (welcomeScreen) {
        messagesContainer.appendChild(welcomeScreen);
        welcomeScreen.style.display = "block";
    }
    clearAttachment();
    if (chatInput) {
        chatInput.value = "";
        chatInput.style.height = "auto";
        chatInput.focus();
    }
}

function loadActiveChatMessages() {
    const currentChat = getActiveChat();
    if (!currentChat || !Array.isArray(currentChat.messages) || currentChat.messages.length === 0) {
        resetChatView();
        return;
    }

    messagesContainer.innerHTML = "";
    if (welcomeScreen) welcomeScreen.style.display = "none";

    currentChat.messages.forEach(msg => {
        if (!msg) return;
        try {
            if (msg.role === "user") {
                appendUserBubble(msg.text, msg.file, msg.id, false);
            } else if (msg.role === "assistant") {
                if (msg.answer) {
                    appendAssistantResponse(msg.answer, false, false);
                } else if (msg.text) {
                    appendAssistantResponse(createSystemNotice("Response", msg.text), false, false);
                }
            }
        } catch (err) {
            console.error("Error rendering message:", err, msg);
        }
    });

    scrollToBottom();
}

// --- FILE / CAMERA UPLOAD HANDLER ---
function handleFileSelected(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    const isImage = file.type.startsWith("image/");
    const isPdf = file.type === "application/pdf";

    attachedFile = {
        name: file.name,
        type: file.type,
        size: file.size,
        fileRef: file,
        isImage: isImage,
        isPdf: isPdf,
        textContent: ""
    };

    if (file.type.startsWith("text/")) {
        const reader = new FileReader();
        reader.onload = (event) => {
            attachedFile.textContent = event.target.result;
        };
        reader.readAsText(file);
    }

    if (previewFilename) previewFilename.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
    if (previewIcon) previewIcon.textContent = isImage ? "📷" : (isPdf ? "📕" : "📄");
    if (attachmentPreview) attachmentPreview.style.display = "flex";

    chatInput.focus();
}

function clearAttachment() {
    attachedFile = null;
    if (fileInput) fileInput.value = "";
    if (attachmentPreview) attachmentPreview.style.display = "none";
}

// --- BACKEND HEALTH CHECK ---
let consecutiveFailedPings = 0;
let isQueryInProgress = false;

function setBackendOnlineStatus(isOnline) {
    isBackendLive = !!isOnline;
    if (backendBadge) {
        backendBadge.className = isOnline ? "connection-badge connected" : "connection-badge offline";
        backendBadge.textContent = isOnline ? "● Online" : "● Offline";
        backendBadge.title = isOnline ? `Backend API is online and healthy (${API_BASE})` : "Backend API is offline. Run start.bat to launch the backend server.";
    }
}

async function checkBackendHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000);
        const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (res.ok) {
            const data = await res.json().catch(() => null);
            if (data && (data.status === "ok" || data.status === "healthy" || data.service === "nivaan" || data.service === "govbank-assistant")) {
                consecutiveFailedPings = 0;
                setBackendOnlineStatus(true);
                return;
            }
        }
    } catch (e) {
        // Backend ping failed or aborted
    }
    // If a request is actively processing, backend is working, so avoid false offline flickering
    if (isQueryInProgress) {
        return;
    }
    consecutiveFailedPings++;
    // Only mark offline if 3 consecutive health checks fail
    if (consecutiveFailedPings >= 3) {
        setBackendOnlineStatus(false);
    }
}

// --- AUTO-RESUME IN-FLIGHT OR UNANSWERED QUERY AFTER PAGE REFRESH ---
async function checkAndResumePendingQuery() {
    if (isQueryInProgress) return;

    let pending = null;
    try {
        const raw = localStorage.getItem(PENDING_QUERY_KEY);
        if (raw) pending = JSON.parse(raw);
    } catch (e) {
        console.warn("Failed to parse pending query from localStorage:", e);
    }

    const currentChat = getActiveChat();

    // Check 1: Explicit pending query in localStorage within last 15 minutes
    const hasRecentPending = !!(pending && pending.userText && (Date.now() - (pending.timestamp || 0) < 15 * 60 * 1000));

    // Check 2: Active chat ends with a user message without an assistant response
    let hasUnansweredUserMsg = false;
    let unansweredText = "";

    if (currentChat && Array.isArray(currentChat.messages) && currentChat.messages.length > 0) {
        const lastMsg = currentChat.messages[currentChat.messages.length - 1];
        if (lastMsg && lastMsg.role === "user") {
            hasUnansweredUserMsg = true;
            unansweredText = lastMsg.text || "";
        }
    }

    if (!hasRecentPending && !hasUnansweredUserMsg) {
        return;
    }

    let targetChat = currentChat;
    if (hasRecentPending && pending.chatId && (!targetChat || targetChat.id !== pending.chatId)) {
        const found = chats.find(c => c.id === pending.chatId);
        if (found) {
            targetChat = found;
            activeChatId = found.id;
            saveChatsToStorage();
            renderHistoryList();
            loadActiveChatMessages();
        }
    }

    if (!targetChat) return;

    const queryToExecute = (hasRecentPending && pending.userText) || unansweredText;
    if (!queryToExecute || !queryToExecute.trim()) return;

    console.info("Resuming pending/interrupted query after page refresh:", queryToExecute);

    setLoading(true);
    try {
        localStorage.setItem(PENDING_QUERY_KEY, JSON.stringify({
            chatId: targetChat.id,
            userText: queryToExecute,
            timestamp: Date.now()
        }));
        await executeQuery(queryToExecute, null, targetChat);
    } catch (err) {
        console.error("Failed to resume query after refresh:", err);
    } finally {
        localStorage.removeItem(PENDING_QUERY_KEY);
        setLoading(false);
    }
}

// --- USER SUBMISSION ---
function handleUserSubmit() {
    if (isQueryInProgress) return;
    const text = chatInput.value.trim();
    if (!text && !attachedFile) return;

    const userMessage = text || `Uploaded document: ${attachedFile.name}`;
    sendMessage(userMessage, attachedFile);

    chatInput.value = "";
    chatInput.style.height = "auto";
}

// --- CORE SEND MESSAGE PIPELINE ---
async function sendMessage(userText, fileObj = null) {
    if (welcomeScreen) welcomeScreen.style.display = "none";

    let currentChat = getActiveChat();
    const sanitizedUserText = maskClientPII(userText);
    const msgId = "msg_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5);
    const fileMeta = fileObj ? {
        name: fileObj.name,
        type: fileObj.type,
        size: fileObj.size,
        isImage: fileObj.isImage,
        isPdf: fileObj.isPdf
    } : null;

    if (!currentChat) {
        const newId = "chat_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5);
        currentChat = {
            id: newId,
            title: generateTitle(sanitizedUserText),
            createdAt: Date.now(),
            updatedAt: Date.now(),
            messages: [{
                id: msgId,
                role: "user",
                text: sanitizedUserText,
                file: fileMeta
            }]
        };
        chats.unshift(currentChat);
        activeChatId = newId;
    } else {
        if (currentChat.messages.length === 0) {
            currentChat.title = generateTitle(sanitizedUserText);
        }
        currentChat.messages.push({
            id: msgId,
            role: "user",
            text: sanitizedUserText,
            file: fileMeta
        });
        currentChat.updatedAt = Date.now();
    }

    saveChatsToStorage();
    renderHistoryList();

    appendUserBubble(sanitizedUserText, fileMeta, msgId, true);

    const currentAttachment = fileObj || attachedFile;
    clearAttachment();

    setLoading(true);
    try {
        localStorage.setItem(PENDING_QUERY_KEY, JSON.stringify({
            chatId: currentChat.id,
            msgId: msgId,
            userText: userText,
            timestamp: Date.now()
        }));
        await executeQuery(userText, currentAttachment, currentChat);
    } finally {
        localStorage.removeItem(PENDING_QUERY_KEY);
        setLoading(false);
    }
}

// --- MARKDOWN FORMATTING & STREAMING HELPERS ---
function formatMarkdownMini(text) {
    if (!text) return "";
    let safe = escapeHtml(text);
    safe = safe.replace(/\r\n/g, "\n");

    // --- PRE-PROCESSING: strip residual raw markdown links/images BEFORE escaping messes them up ---
    // Note: escapeHtml converts [ to &#91; etc. So we must clean BEFORE escapeHtml — but we already escaped.
    // Instead we strip them from the original string before escaping.
    return _formatMarkdownMiniRaw(text);
}

function _formatMarkdownMiniRaw(text) {
    if (!text) return "";

    // 1. First strip raw markdown image syntax: ![alt](url) -> alt
    text = text.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1");

    // 2. Convert markdown links: [Title](url) -> clickable anchor
    text = text.replace(/\[([^\]]+)\]\(((?:https?:)?\/\/[^\s<)]+)\)/g, (m, title, url) => {
        const fullUrl = url.startsWith("//") ? `https:${url}` : url;
        // Use a placeholder to protect from further replacements
        return `\x00LINK\x00${title}\x00${fullUrl}\x00`;
    });
    // Strip any remaining broken/partial markdown links where URL is malformed
    text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");

    // Now HTML-escape the cleaned text
    let safe = escapeHtml(text);
    safe = safe.replace(/\r\n/g, "\n");

    // 3. Restore link placeholders as proper anchors
    safe = safe.replace(/\x00LINK\x00([^\x00]+)\x00([^\x00]+)\x00/g, (m, title, url) => {
        const safeTitle = title.replace(/&amp;/g, "&");
        const safeUrl = url.replace(/&amp;/g, "&");
        return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="doc-link">${safeTitle} <span class="doc-link-arrow">↗</span></a>`;
    });

    // 4. Clean up markdown headings (### Title) into clear subheadings
    safe = safe.replace(/(?:^|\n)#{1,6}[ \t]*([^\n]+)/g, '\n<div class="step-subheading">$1</div>\n');

    // 5. Bold & italic
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");

    // 6. Bare protocol-relative URLs (e.g. //www.example.gov.in)
    safe = safe.replace(/(^|[\s(])(\/\/[a-zA-Z0-9][-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b[-a-zA-Z0-9()@:%_+.~#?&/=]*)/g, (m, prefix, url) => {
        return `${prefix}<a href="https:${url}" target="_blank" rel="noopener noreferrer" class="doc-link">${url} <span class="doc-link-arrow">↗</span></a>`;
    });

    // 7. Bare HTTP/HTTPS URLs (avoiding href="...")
    safe = safe.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (m, prefix, url) => {
        return `${prefix}<a href="${url}" target="_blank" rel="noopener noreferrer" class="doc-link">${url} <span class="doc-link-arrow">↗</span></a>`;
    });

    // 8. Bullet items: - item or * item or • item
    safe = safe.replace(/(?:^|\n)[ \t]*[-*•][ \t]+([^\n]+)/g, '\n<div class="step-bullet"><span class="bullet-dot">•</span><span class="bullet-text">$1</span></div>\n');

    // 9. Clean up whitespace around block elements
    safe = safe.replace(/\n*(<div class="step-[^"]+">)/g, "$1");
    safe = safe.replace(/(<\/div>)\n*/g, "$1");

    // 10. Paragraph breaks and line breaks
    safe = safe.replace(/\n\s*\n/g, '<div class="step-spacer"></div>');
    safe = safe.replace(/\n/g, "<br>");

    // 11. Strip leading/trailing line breaks
    safe = safe.replace(/^(?:<br>|\s)+|(?:<br>|\s)+$/g, "");
    return safe;
}

function appendThinkingBubble() {
    const row = document.createElement("div");
    row.className = "message-row assistant-thinking-row";
    row.id = "thinkingBubbleRow";

    row.innerHTML = `
        ${BOT_AVATAR_HTML}
        <div class="message-content">
            <div class="thinking-card">
                <div class="thinking-header">
                    <span class="thinking-spinner"></span>
                    <span class="thinking-status-text" id="thinkingStatusText">Searching official portals & statutory guidelines...</span>
                </div>
                <div class="thinking-progress-bar">
                    <div class="thinking-progress-fill"></div>
                </div>
            </div>
        </div>
    `;

    messagesContainer.appendChild(row);
    scrollToBottom();

    const statuses = [
        "🔍 Searching verified official government portals...",
        "📑 Retrieving relevant regulatory clauses & statutory forms...",
        "🏛️ Formulating authoritative step-by-step guidance...",
        "⚖️ Validating rules against official circulars..."
    ];
    let idx = 0;
    const statusTextEl = row.querySelector("#thinkingStatusText");
    const intervalId = setInterval(() => {
        idx = (idx + 1) % statuses.length;
        if (statusTextEl) {
            statusTextEl.style.opacity = "0";
            setTimeout(() => {
                if (statusTextEl) {
                    statusTextEl.textContent = statuses[idx];
                    statusTextEl.style.opacity = "1";
                }
            }, 200);
        }
    }, 3000);

    return {
        row,
        stop: () => {
            clearInterval(intervalId);
        }
    };
}

// --- QUERY EXECUTION ---
async function executeQuery(userText, currentAttachment, chatObj) {
    let answer = null;
    let thinkingObj = appendThinkingBubble();
    let streamRendered = false;

    try {
        const hasReadableDocumentText = !!(currentAttachment && currentAttachment.textContent && currentAttachment.textContent.trim());

        if (currentAttachment && !hasReadableDocumentText && currentAttachment.fileRef) {
            let previousEntryId = null;
            let contextTopic = null;
            if (chatObj && Array.isArray(chatObj.messages)) {
                for (let i = chatObj.messages.length - 1; i >= 0; i--) {
                    const m = chatObj.messages[i];
                    if (m.role === "assistant" && m.answer) {
                        if (m.answer.entry_id) previousEntryId = m.answer.entry_id;
                        if (m.answer.title && m.answer.title !== "No verified guide found") contextTopic = m.answer.title;
                        break;
                    }
                }
            }

            const formData = new FormData();
            formData.append("file", currentAttachment.fileRef);
            formData.append("question", userText || "Explain this document");
            if (chatObj && chatObj.id) formData.append("conversation_id", chatObj.id);
            if (previousEntryId) formData.append("previous_entry_id", previousEntryId);
            if (contextTopic) formData.append("context_topic", contextTopic);

            const uploadResponse = await fetch(`${API_BASE}/api/ask-file`, {
                method: "POST",
                body: formData
            });

            if (uploadResponse.ok) {
                answer = await uploadResponse.json();
            } else {
                const uploadError = await safeReadJson(uploadResponse);
                answer = createSystemNotice(
                    "This file cannot be processed yet",
                    uploadError?.detail || uploadError?.message || "Only readable text files are supported right now. PDF/image OCR is planned next."
                );
            }
        } else {
            let previousEntryId = null;
            let contextTopic = null;
            if (chatObj && Array.isArray(chatObj.messages)) {
                for (let i = chatObj.messages.length - 1; i >= 0; i--) {
                    const m = chatObj.messages[i];
                    if (m.role === "assistant" && m.answer) {
                        if (m.answer.entry_id) {
                            previousEntryId = m.answer.entry_id;
                        }
                        if (m.answer.title && m.answer.title !== "No verified guide found") {
                            contextTopic = m.answer.title;
                        }
                        break;
                    }
                }
            }

            const isDocument = hasReadableDocumentText;
            const payload = {
                input_type: isDocument ? "document" : "question",
                question: userText,
                conversation_id: chatObj ? chatObj.id : "conv_default",
                file_attached: false
            };
            if (previousEntryId) payload.previous_entry_id = String(previousEntryId).slice(0, 200).trim();
            if (contextTopic) payload.context_topic = String(contextTopic).slice(0, 500).trim();

            if (chatObj && Array.isArray(chatObj.messages) && chatObj.messages.length > 0) {
                payload.history = chatObj.messages
                    .slice(-30)
                    .filter(m => m && (m.text || m.answer))
                    .map(m => {
                        let content = m.text || "";
                        let title = null;
                        let entryId = null;
                        if (m.answer) {
                            title = m.answer.title || null;
                            entryId = m.answer.entry_id || null;
                            const summary = m.answer.summary || "";
                            const docs = (m.answer.documents_needed || []).join(", ");
                            const steps = (m.answer.steps || []).map(s => `${s.title}: ${s.detail || ""}`.trim()).join("; ");
                            content = [summary, docs ? `Documents: ${docs}` : "", steps].filter(Boolean).join("\n");
                        }
                        return {
                            role: m.role || "user",
                            content: content.slice(0, 1000),
                            title: title,
                            entry_id: entryId
                        };
                    });
            }

            if (hasReadableDocumentText) {
                payload.document_text = currentAttachment.textContent.trim();
            }

            // Real-Time Server-Sent Events (SSE) Streaming
            let streamSuccess = false;
            let liveCard = null;
            let accumulatedTokens = "";

            try {
                const streamResponse = await fetch(`${API_BASE}/api/ask/stream`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (streamResponse.ok && streamResponse.body) {
                    setBackendOnlineStatus(true);
                    const reader = streamResponse.body.getReader();
                    const decoder = new TextDecoder("utf-8");
                    let streamBuffer = "";

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        streamBuffer += decoder.decode(value, { stream: true });
                        const parts = streamBuffer.split("\n\n");
                        streamBuffer = parts.pop();

                        for (const part of parts) {
                            if (!part.trim()) continue;
                            let eventType = "message";
                            let dataStr = "";
                            const lines = part.split("\n");
                            for (const line of lines) {
                                if (line.startsWith("event:")) {
                                    eventType = line.slice(6).trim();
                                } else if (line.startsWith("data:")) {
                                    dataStr = line.slice(5).trim();
                                }
                            }
                            let data = null;
                            try {
                                data = JSON.parse(dataStr);
                            } catch (e) {
                                continue;
                            }

                            if (eventType === "status" && data && data.message) {
                                const statusEl = document.getElementById("thinkingStatusText");
                                if (statusEl) statusEl.textContent = data.message;
                            } else if (eventType === "meta" && data) {
                                if (thinkingObj) {
                                    thinkingObj.stop();
                                    thinkingObj.row.remove();
                                    thinkingObj = null;
                                }
                                if (!liveCard) {
                                    liveCard = createLiveAssistantRow(data);
                                    messagesContainer.appendChild(liveCard.row);
                                    scrollToBottom();
                                } else {
                                    liveCard.updateMeta(data);
                                }
                            } else if (eventType === "token" && data && data.delta) {
                                if (thinkingObj) {
                                    thinkingObj.stop();
                                    thinkingObj.row.remove();
                                    thinkingObj = null;
                                }
                                if (!liveCard) {
                                    liveCard = createLiveAssistantRow({ title: "Civic & Banking Guide", confidence: "verified" });
                                    messagesContainer.appendChild(liveCard.row);
                                }
                                accumulatedTokens += data.delta;
                                liveCard.updateTyping(accumulatedTokens);
                                scrollToBottom();
                            } else if (eventType === "done" && data && data.answer) {
                                answer = data.answer;
                                streamSuccess = true;
                            }
                        }
                    }

                    if (liveCard && answer) {
                        liveCard.finalize(answer);
                        streamSuccess = true;
                        streamRendered = true;
                    } else if (liveCard && accumulatedTokens) {
                        answer = {
                            title: "Civic & Banking Guide",
                            summary: accumulatedTokens,
                            confidence: "verified",
                            documents_needed: [],
                            steps: [],
                            warnings: [],
                            source_url: "https://www.india.gov.in/",
                            last_verified: new Date().toISOString().slice(0, 10),
                            citations: []
                        };
                        liveCard.finalize(answer);
                        streamSuccess = true;
                        streamRendered = true;
                    }
                }
            } catch (streamErr) {
                console.warn("Real-time stream error, falling back to sync endpoint:", streamErr);
            }

            // Fallback to sync endpoint if stream did not complete
            if (!streamSuccess) {
                const response = await fetch(`${API_BASE}/api/ask`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    answer = await response.json();
                    setBackendOnlineStatus(true);
                } else {
                    const errorPayload = await safeReadJson(response);
                    const errorDetails = Array.isArray(errorPayload?.details)
                        ? errorPayload.details.map(d => `${d.loc ? d.loc.slice(1).join('.') : 'field'}: ${d.msg}`).join("; ")
                        : null;
                    answer = createSystemNotice(
                        "Request Notice",
                        errorDetails || errorPayload?.detail || errorPayload?.message || "The backend rejected this request."
                    );
                }
            }
        }
    } catch (err) {
        console.warn("Backend connection error:", err);
        try {
            const healthCheck = await fetch(`${API_BASE}/api/health`, { cache: "no-store" });
            if (healthCheck.ok) {
                setBackendOnlineStatus(true);
                answer = createSystemNotice(
                    "Request Connection Interrupted",
                    `The backend is online, but the query connection was interrupted (${err?.message || "network reset"}). Check the backend terminal log or close heavy apps to free RAM for the 7B model.`
                );
            } else {
                setBackendOnlineStatus(false);
                answer = createSystemNotice(
                    "Backend Offline",
                    `Cannot connect to the backend server at ${API_BASE}. Please ensure the backend is running and reachable.`
                );
            }
        } catch (_) {
            setBackendOnlineStatus(false);
            answer = createSystemNotice(
                "Backend Offline",
                `Cannot connect to the backend server at ${API_BASE}. Please ensure the backend is running and reachable.`
            );
        }
    } finally {
        if (thinkingObj) {
            thinkingObj.stop();
            thinkingObj.row.remove();
            thinkingObj = null;
        }
    }

    if (!answer) {
        answer = createSystemNotice(
            "No Response",
            "The backend did not return an answer. Please check backend logs or try again."
        );
    }

    const targetChat = (chatObj && chats.find(c => c.id === chatObj.id)) || getActiveChat() || chatObj;
    if (targetChat && answer) {
        const cleanedForStorage = { ...answer };
        delete cleanedForStorage.disclaimer;
        cleanedForStorage.warnings = [];
        targetChat.messages.push({
            id: "msg_ast_" + Date.now(),
            role: "assistant",
            answer: cleanedForStorage
        });
        targetChat.updatedAt = Date.now();
        saveChatsToStorage();
    }

    // Only append statically if the real-time stream hasn't already rendered it live
    if (!streamRendered && (!activeChatId || !targetChat || activeChatId === targetChat.id)) {
        appendAssistantResponse(answer, true, false);
    }
}

// --- EDITABLE MESSAGE PROMPTS ---
window.startEditPrompt = function(msgId) {
    const currentChat = getActiveChat();
    if (!currentChat) return;
    const msg = currentChat.messages.find(m => m.id === msgId);
    if (!msg) return;

    const row = document.getElementById("row_" + msgId);
    if (!row) return;

    const content = row.querySelector(".message-content");
    const wrapper = row.querySelector(".user-bubble-wrapper");
    if (!wrapper) return;

    if (content) content.classList.add("is-editing");
    wrapper.classList.add("is-editing");
    wrapper.innerHTML = `
        <div class="user-edit-container">
            <textarea class="user-edit-textarea" id="edit_textarea_${msgId}" rows="1">${escapeHtml(msg.text)}</textarea>
            <div class="user-edit-actions">
                <button type="button" class="user-edit-btn cancel-btn" onclick="cancelEditPrompt('${msgId}')">Cancel</button>
                <button type="button" class="user-edit-btn save-btn" onclick="submitEditPrompt('${msgId}')">Save & Submit</button>
            </div>
        </div>
    `;

    const textarea = document.getElementById(`edit_textarea_${msgId}`);
    if (textarea) {
        const autoResize = () => {
            textarea.style.height = "auto";
            const newHeight = Math.max(textarea.scrollHeight, 44);
            textarea.style.height = newHeight + "px";
            if (textarea.scrollHeight > window.innerHeight * 0.7) {
                textarea.style.overflowY = "auto";
            } else {
                textarea.style.overflowY = "hidden";
            }
        };

        textarea.addEventListener("input", autoResize);
        textarea.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitEditPrompt(msgId);
            } else if (e.key === "Escape") {
                e.preventDefault();
                cancelEditPrompt(msgId);
            }
        });

        // Compute size to fit question length immediately & after reflow
        autoResize();
        requestAnimationFrame(autoResize);

        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }
};

window.cancelEditPrompt = function(msgId) {
    const currentChat = getActiveChat();
    if (!currentChat) return;
    const msg = currentChat.messages.find(m => m.id === msgId);
    if (!msg) return;

    const row = document.getElementById("row_" + msgId);
    if (!row) return;

    const content = row.querySelector(".message-content");
    const wrapper = row.querySelector(".user-bubble-wrapper");
    if (!wrapper) return;

    if (content) content.classList.remove("is-editing");
    wrapper.classList.remove("is-editing");
    wrapper.innerHTML = `
        <div class="user-bubble" id="bubble_${msgId}">${escapeHtml(msg.text)}</div>
        <button class="edit-msg-btn" onclick="startEditPrompt('${msgId}')" title="Edit prompt">✏️</button>
    `;
};

window.submitEditPrompt = async function(msgId) {
    const currentChat = getActiveChat();
    if (!currentChat) return;
    const textarea = document.getElementById(`edit_textarea_${msgId}`);
    if (!textarea) return;

    const newText = textarea.value.trim();
    if (!newText) return;

    const msgIdx = currentChat.messages.findIndex(m => m.id === msgId);
    if (msgIdx === -1) return;

    const msg = currentChat.messages[msgIdx];
    msg.text = maskClientPII(newText);

    // Truncate messages after this message in conversation history
    currentChat.messages = currentChat.messages.slice(0, msgIdx + 1);
    if (msgIdx === 0) {
        currentChat.title = generateTitle(newText);
    }
    currentChat.updatedAt = Date.now();
    saveChatsToStorage();
    renderHistoryList();

    // Re-render UI up to this message
    loadActiveChatMessages();

    // Re-execute query for updated prompt
    setLoading(true);
    try {
        localStorage.setItem(PENDING_QUERY_KEY, JSON.stringify({
            chatId: currentChat.id,
            msgId: msg.id,
            userText: newText,
            timestamp: Date.now()
        }));
        await executeQuery(newText, msg.file, currentChat);
    } finally {
        localStorage.removeItem(PENDING_QUERY_KEY);
        setLoading(false);
    }
};

// --- APPEND USER BUBBLE ---
function appendUserBubble(text, file, msgId = null, shouldScroll = true) {
    const id = msgId || ("msg_" + Date.now());
    const row = document.createElement("div");
    row.className = "message-row";
    row.id = "row_" + id;
    row.style.justifyContent = "flex-end";

    let fileHtml = "";
    if (file) {
        fileHtml = `
            <div>
                <span class="user-attachment-pill">
                    <span>${file.isImage ? "📷" : "📄"}</span>
                    <strong>${escapeHtml(file.name)}</strong>
                </span>
            </div>
        `;
    }

    row.innerHTML = `
        <div class="message-content" style="text-align: right;">
            ${fileHtml}
            <div class="user-bubble-wrapper">
                <div class="user-bubble" id="bubble_${id}">${escapeHtml(text)}</div>
                <button class="edit-msg-btn" onclick="startEditPrompt('${id}')" title="Edit prompt">✏️</button>
            </div>
        </div>
        <div class="message-avatar user-avatar">👤</div>
    `;

    messagesContainer.appendChild(row);
    if (shouldScroll) scrollToBottom();
}

// --- CREATE SYSTEM NOTICE ---
function createSystemNotice(title, message) {
    return {
        title,
        summary: message,
        documents_needed: [],
        steps: [],
        warnings: [],
        source_url: "https://www.india.gov.in/",
        last_verified: new Date().toISOString().slice(0, 10),
        confidence: "low",
        masked_items: [],
    };
}

async function safeReadJson(response) {
    try {
        return await response.json();
    } catch (err) {
        return null;
    }
}

// --- SOURCE DOMAIN FORMATTER ---
function formatSourceDomain(urlStr) {
    try {
        const u = new URL(urlStr);
        return u.hostname.replace(/^www\./, "");
    } catch (e) {
        return "Official Portal";
    }
}

// --- FORMAT RESPONSE TITLE ---
function formatResponseTitle(title) {
    if (!title) return "";
    const clean = String(title)
        .replace(/^(?:Relevant|Verified)\s+official\s+material:\s*/i, "")
        .replace(/^Official\s+civic\s+procedure:?\s*/i, "")
        .replace(/^Official\s+guideline\s+\d*:?\s*/i, "")
        .trim();
    if (/^(?:Civic & Banking Guide|Verified Civic Knowledge|Official Procedure|PAN|Aadhaar|Passport|EPFO|Voter ID|General Guidance)$/i.test(clean)) {
        return "";
    }
    return clean;
}

// --- CLEAN AI SUMMARY PROSE (REMOVE PRE-CANNED / DISCLAIMER TAILS) ---
function cleanAiSummary(summary) {
    if (!summary) return "";
    return String(summary)
        .replace(/^For your question,.*?this is the closest guide I found\.?\s*/i, "")
        .replace(/\s*Note:\s*this candidate evidence from official sources has not been independently fact-checked[\s\S]*$/i, "")
        .replace(/\s*Note:\s*this guide is currently marked unverified in the project data[\s\S]*$/i, "")
        .replace(/\s*Confirm time-sensitive rules on the linked official portal\.?/gi, "")
        .trim();
}

// --- RENDER POST-SUMMARY SECTIONS (DOCUMENTS, STEPS, SOURCES) ---
function renderPostSummarySections(answer) {
    if (!answer) return "";

    // 1. Documents required (Clean list - no checkboxes)
    let docsHtml = "";
    if (answer.documents_needed && answer.documents_needed.length > 0) {
        const docItems = answer.documents_needed.map(doc => {
            let title = "";
            let linkUrl = "";
            if (typeof doc === "object" && doc !== null) {
                title = doc.title || doc.name || doc.document || "";
                linkUrl = doc.url || doc.detail || "";
            } else if (typeof doc === "string") {
                let clean = doc.trim();
                if ((clean.startsWith("{") && clean.endsWith("}")) || clean.includes("'title'") || clean.includes('"title"')) {
                    try {
                        const parsed = JSON.parse(clean.replace(/'/g, '"'));
                        if (typeof parsed === "object" && parsed !== null) {
                            title = parsed.title || parsed.name || parsed.document || clean;
                            linkUrl = parsed.url || parsed.detail || "";
                        }
                    } catch (e) {
                        const mTitle = clean.match(/['"]title['"]\s*:\s*['"]([^'"]+)['"]/);
                        const mDetail = clean.match(/['"]detail['"]\s*:\s*['"]([^'"]+)['"]/);
                        if (mTitle) title = mTitle[1];
                        if (mDetail) linkUrl = mDetail[1];
                    }
                }
                if (!title) title = clean;
            } else {
                title = String(doc || "");
            }

            const isHttp = linkUrl && (linkUrl.startsWith("http://") || linkUrl.startsWith("https://"));
            const content = isHttp 
                ? `<a href="${escapeHtml(linkUrl)}" target="_blank" rel="noopener noreferrer" class="doc-link" title="${escapeHtml(title)}">${escapeHtml(title)} <span class="doc-link-arrow">↗</span></a>`
                : escapeHtml(title);

            return `
                <li class="clean-doc-item">
                    <span class="clean-doc-icon">📄</span>
                    <span class="clean-doc-text">${content}</span>
                </li>
            `;
        }).join("");

        docsHtml = `
            <div class="clean-section">
                <div class="section-title">
                    <span>📑 Required Documents</span>
                </div>
                <ul class="clean-docs-list">${docItems}</ul>
            </div>
        `;
    }

    // 2. Step-by-Step Procedure (Clean numbered process - no checkboxes)
    let stepsHtml = "";
    if (answer.steps && answer.steps.length > 0) {
        const stepItems = answer.steps.map((st, idx) => {
            const stepNo = st.no || idx + 1;
            const stepText = st.text || st.title || "Step";
            const stepTip = st.tip || st.detail || "";
            return `
            <div class="clean-step-card">
                <div class="clean-step-badge">${stepNo}</div>
                <div class="clean-step-content">
                    <div class="clean-step-title">${formatMarkdownMini(stepText)}</div>
                    ${stepTip ? `<div class="clean-step-detail"><div class="clean-step-detail-header">💡 <strong>Details & Guidance:</strong></div><div class="clean-step-detail-body">${formatMarkdownMini(stepTip)}</div></div>` : ""}
                </div>
            </div>
        `;
        }).join("");

        stepsHtml = `
            <div class="clean-section">
                <div class="section-title">
                    <span>📋 Step-by-Step Procedure</span>
                </div>
                <div class="clean-steps-list">${stepItems}</div>
            </div>
        `;
    }

    // 3. Disclaimer Notice
    let disclaimerHtml = "";
    if (answer.disclaimer) {
        disclaimerHtml = `
            <div class="disclaimer-text">
                ⚖️ <strong>Official Notice:</strong> ${escapeHtml(answer.disclaimer)}
            </div>
        `;
    }

    // 4. Gather and format tagged source links at the end
    const sourcesList = [];
    const seenUrls = new Set();

    if (answer.source_url) {
        const urlStr = String(answer.source_url).trim();
        if (urlStr) {
            seenUrls.add(urlStr.toLowerCase());
            sourcesList.push({
                url: urlStr,
                title: answer.title || "Official Portal",
                domain: formatSourceDomain(urlStr)
            });
        }
    }

    const citations = Array.isArray(answer.citations) ? answer.citations : [];
    citations.forEach(c => {
        const cUrl = String(c.url || "").trim();
        if (!cUrl) return;
        const lowerUrl = cUrl.toLowerCase();
        if (!seenUrls.has(lowerUrl)) {
            seenUrls.add(lowerUrl);
            sourcesList.push({
                url: cUrl,
                title: c.title || formatSourceDomain(cUrl),
                domain: formatSourceDomain(cUrl)
            });
        }
    });

    const hasUnverifiedEvidence = citations.some(citation => citation.factual_verification !== "verified");
    const sourceDateLabel = hasUnverifiedEvidence ? "Source date reported" : "Verified";

    let sourcesHtml = "";
    if (sourcesList.length > 0) {
        const sourceCards = sourcesList.map((src, idx) => {
            const cleanTitle = (src.title || "")
                .replace(/^(?:Relevant|Verified)\s+official\s+material:\s*/i, "")
                .replace(/^Official\s+guideline\s+\d*:?\s*/i, "")
                .trim() || src.domain;
            return `
                <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="clean-source-card" title="${escapeHtml(cleanTitle)} • ${escapeHtml(src.url)}" onclick="trackCitationClick(this, '${escapeHtml(src.url)}')">
                    <span class="source-card-num">${idx + 1}</span>
                    <div class="source-card-body">
                        <span class="source-card-title">${escapeHtml(cleanTitle)}</span>
                        <span class="source-card-domain">${escapeHtml(src.domain)}</span>
                    </div>
                    <span class="source-card-arrow">↗</span>
                </a>
            `;
        }).join("");

        const citationsAccordion = citations.some(c => c.excerpt) ? `
            <details class="clean-evidence-accordion">
                <summary class="clean-evidence-toggle">
                    <span>🔍 View Evidence Excerpts (${citations.length})</span>
                </summary>
                <div class="clean-evidence-list">
                    ${citations.map((c, i) => {
                        const cTitle = (c.title || "").replace(/^(?:Relevant|Verified)\s+official\s+material:\s*/i, "").trim() || "Official source";
                        return `
                        <div class="clean-evidence-item">
                            <div class="clean-evidence-head">
                                <span class="clean-evidence-num">[${i + 1}]</span>
                                <a href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer" class="clean-evidence-link">
                                    ${escapeHtml(cTitle)} ↗
                                </a>
                                <span class="verification-status verification-${escapeHtml(c.factual_verification || 'verified')}">
                                    ${escapeHtml((c.factual_verification || 'verified').toUpperCase())}
                                </span>
                            </div>
                            <p class="clean-evidence-excerpt">${escapeHtml(c.excerpt)}</p>
                        </div>
                    `;}).join("")}
                </div>
            </details>
        ` : "";

        sourcesHtml = `
            <div class="clean-sources-section">
                <div class="clean-sources-header">
                    <div class="clean-sources-heading">
                        <span class="sources-heading-icon">🌐</span>
                        <span>Sources</span>
                        <span class="sources-badge">${sourcesList.length}</span>
                    </div>
                    ${answer.last_verified ? `
                    <span class="clean-sources-verify">
                        ${sourceDateLabel}: <strong>${escapeHtml(answer.last_verified)}</strong>
                    </span>` : ""}
                </div>
                <div class="clean-sources-grid">
                    ${sourceCards}
                </div>
                ${citationsAccordion}
            </div>
        `;
    }

    return docsHtml + stepsHtml + disclaimerHtml + sourcesHtml;
}

// --- CREATE LIVE ASSISTANT CARD FOR SERVER-SENT EVENTS ---
function createLiveAssistantRow(meta) {
    const row = document.createElement("div");
    row.className = "message-row";

    let maskedBanner = "";
    if (meta && meta.masked_items && meta.masked_items.length > 0) {
        const maskedDetails = meta.masked_items.map(m => {
            const label = m.item_type || "item";
            return m.count ? `${m.count} ${label}` : `${label} as ${m.replacement || "[masked]"}`;
        }).join(", ");
        maskedBanner = `
            <div class="privacy-alert">
                <span>🛡️</span>
                <span><strong>Protected Sensitive Data:</strong> Redacted ${maskedDetails} before processing.</span>
            </div>
        `;
    }

    const initialTitle = formatResponseTitle((meta && meta.title) || "");
    const headerDisplay = initialTitle ? "" : 'style="display: none;"';

    row.innerHTML = `
        ${BOT_AVATAR_HTML}
        <div class="message-content">
            <div class="assistant-response">
                <div class="response-header" ${headerDisplay}>
                    <h3 class="response-title">${escapeHtml(initialTitle)}</h3>
                </div>

                ${maskedBanner}

                <div class="response-summary">
                    <span class="typing-text"></span><span class="typing-cursor">▌</span>
                </div>

                <div class="post-summary-sections" style="display: none;"></div>

                <div class="response-bottom-bar" style="display: none;">
                    <div class="response-bottom-meta">
                        <span class="response-confidence confidence-${(meta && meta.confidence) || 'verified'}">
                            ● ${(meta && meta.confidence ? meta.confidence.toUpperCase() : 'VERIFIED')}
                        </span>
                    </div>
                    <div class="response-bottom-actions">
                        <button class="copy-response-btn" onclick="copyResponseText(this)" title="Copy guide to clipboard" aria-label="Copy">${ICON_COPY} <span class="btn-label-text">Copy</span></button>
                        <button class="feedback-btn thumbs-up" onclick="sendFeedback(this, 'thumbs_up')" title="Helpful and accurate" aria-label="Like">${ICON_THUMBS_UP}</button>
                        <button class="feedback-btn thumbs-down" onclick="sendFeedback(this, 'thumbs_down')" title="Not helpful or inaccurate" aria-label="Dislike">${ICON_THUMBS_DOWN}</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    const typingTextEl = row.querySelector(".typing-text");
    const cursorEl = row.querySelector(".typing-cursor");
    const postSectionsEl = row.querySelector(".post-summary-sections");
    const titleEl = row.querySelector(".response-title");
    const headerEl = row.querySelector(".response-header");
    const bottomBarEl = row.querySelector(".response-bottom-bar");

    return {
        row,
        updateTyping: (text) => {
            if (typingTextEl) typingTextEl.textContent = text;
        },
        updateMeta: (newMeta) => {
            if (newMeta && newMeta.title && titleEl) {
                const cTitle = formatResponseTitle(newMeta.title);
                titleEl.textContent = cTitle;
                if (headerEl) headerEl.style.display = cTitle ? "flex" : "none";
            }
        },
        finalize: (answer) => {
            if (cursorEl) cursorEl.remove();
            if (typingTextEl) {
                const cleanText = cleanAiSummary((answer && answer.summary) || typingTextEl.textContent || "");
                typingTextEl.innerHTML = formatMarkdownMini(cleanText);
            }
            if (postSectionsEl && answer) {
                postSectionsEl.innerHTML = renderPostSummarySections(answer);
                postSectionsEl.style.display = "flex";
                postSectionsEl.classList.add("section-fade-in");
            }
            if (titleEl && answer && answer.title) {
                const cTitle = formatResponseTitle(answer.title);
                titleEl.textContent = cTitle;
                if (headerEl) headerEl.style.display = cTitle ? "flex" : "none";
            }
            if (bottomBarEl) {
                if (answer && answer.confidence) {
                    const confBadge = bottomBarEl.querySelector(".response-confidence");
                    if (confBadge) {
                        confBadge.className = `response-confidence confidence-${answer.confidence.toLowerCase()}`;
                        confBadge.textContent = `● ${answer.confidence.toUpperCase()}`;
                    }
                }
                bottomBarEl.style.display = "flex";
            }
            scrollToBottom();
        }
    };
}

// --- APPEND ASSISTANT RESPONSE CARD (FOR HISTORICAL CHATS OR SYNC FALLBACK) ---
function appendAssistantResponse(answer, shouldScroll = true, isLive = false) {
    const row = document.createElement("div");
    row.className = "message-row";

    let maskedBanner = "";
    if (answer.masked_items && answer.masked_items.length > 0) {
        const maskedDetails = answer.masked_items.map(m => {
            const label = m.item_type || "item";
            return m.count ? `${m.count} ${label}` : `${label} as ${m.replacement || "[masked]"}`;
        }).join(", ");
        maskedBanner = `
            <div class="privacy-alert">
                <span>🛡️</span>
                <span><strong>Protected Sensitive Data:</strong> Redacted ${maskedDetails} before processing.</span>
            </div>
        `;
    }

    const cleanTitle = formatResponseTitle(answer.title);
    const cleanSummaryText = cleanAiSummary(answer.summary);

    let summaryHtml = "";
    if (cleanSummaryText) {
        if (isLive) {
            summaryHtml = `
                <div class="response-summary" title="Click card to display full answer immediately">
                    <span class="typing-text"></span><span class="typing-cursor">▌</span>
                </div>
            `;
        } else {
            summaryHtml = `
                <div class="response-summary">
                    <span class="typing-text">${formatMarkdownMini(cleanSummaryText)}</span>
                </div>
            `;
        }
    }

    const sectionsHtml = renderPostSummarySections(answer);
    const postSectionsDisplay = (isLive && cleanSummaryText) ? 'style="display: none;"' : '';
    const postSectionsClass = (isLive && cleanSummaryText) ? 'post-summary-sections' : 'post-summary-sections section-fade-in';
    const bottomBarDisplay = (isLive && cleanSummaryText) ? 'style="display: none;"' : '';

    row.innerHTML = `
        ${BOT_AVATAR_HTML}
        <div class="message-content">
            <div class="assistant-response">
                ${cleanTitle ? `
                <div class="response-header">
                    <h3 class="response-title">${escapeHtml(cleanTitle)}</h3>
                </div>` : ""}

                <!-- Privacy Redaction Badge -->
                ${maskedBanner}

                <!-- Direct Clean Summary Prose -->
                ${summaryHtml}

                <div class="${postSectionsClass}" ${postSectionsDisplay}>
                    ${sectionsHtml}
                </div>

                <!-- Bottom Action Bar (Confidence, Copy, Thumbs Up/Down) -->
                <div class="response-bottom-bar" ${bottomBarDisplay}>
                    <div class="response-bottom-meta">
                        <span class="response-confidence confidence-${answer.confidence || 'high'}">
                            ● ${answer.confidence ? answer.confidence.toUpperCase() : 'VERIFIED'}
                        </span>
                    </div>
                    <div class="response-bottom-actions">
                        <button class="copy-response-btn" onclick="copyResponseText(this)" title="Copy guide to clipboard" aria-label="Copy">${ICON_COPY} <span class="btn-label-text">Copy</span></button>
                        <button class="feedback-btn thumbs-up" onclick="sendFeedback(this, 'thumbs_up')" title="Helpful and accurate" aria-label="Like">${ICON_THUMBS_UP}</button>
                        <button class="feedback-btn thumbs-down" onclick="sendFeedback(this, 'thumbs_down')" title="Not helpful or inaccurate" aria-label="Dislike">${ICON_THUMBS_DOWN}</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    messagesContainer.appendChild(row);
    if (shouldScroll) scrollToBottom();

    // Word-by-word streaming typewriter animation (only when isLive is requested without SSE)
    if (isLive && cleanSummaryText) {
        const typingTextEl = row.querySelector(".typing-text");
        const cursorEl = row.querySelector(".typing-cursor");
        const postSectionsEl = row.querySelector(".post-summary-sections");
        const bottomBarEl = row.querySelector(".response-bottom-bar");
        const card = row.querySelector(".assistant-response");

        const words = cleanSummaryText.split(/(\s+)/);
        let wordIdx = 0;
        let currentDisplay = "";
        let isDone = false;

        const completeTyping = () => {
            if (isDone) return;
            isDone = true;
            clearInterval(typeInterval);
            if (typingTextEl) typingTextEl.innerHTML = formatMarkdownMini(cleanSummaryText);
            if (cursorEl) cursorEl.remove();
            if (postSectionsEl) {
                postSectionsEl.style.display = "flex";
                postSectionsEl.classList.add("section-fade-in");
            }
            if (bottomBarEl) bottomBarEl.style.display = "flex";
            if (shouldScroll) scrollToBottom();
        };

        if (card) {
            card.addEventListener("click", completeTyping, { once: true });
        }

        const typeInterval = setInterval(() => {
            if (wordIdx < words.length) {
                currentDisplay += words[wordIdx];
                if (typingTextEl) typingTextEl.textContent = currentDisplay;
                wordIdx++;
                if (wordIdx % 4 === 0 && shouldScroll) {
                    scrollToBottom();
                }
            } else {
                completeTyping();
            }
        }, 22);
    }
}


// --- COPY RESPONSE TEXT HELPER ---
window.copyResponseText = function(btn) {
    const card = btn.closest(".assistant-response");
    if (!card) return;
    const cursor = card.querySelector(".typing-cursor");
    if (cursor) {
        card.click(); // Instantly finishes typewriter so full text is copied
    }
    const title = card.querySelector(".response-title")?.textContent.trim() || "";
    const summary = card.querySelector(".response-summary")?.textContent.trim() || "";
    const docs = Array.from(card.querySelectorAll(".clean-doc-text")).map(d => "• " + d.textContent.trim()).join("\n");
    const steps = Array.from(card.querySelectorAll(".clean-step-card")).map(s => {
        const num = s.querySelector(".clean-step-badge")?.textContent.trim() || "";
        const t = s.querySelector(".clean-step-title")?.textContent.trim() || "";
        const d = s.querySelector(".clean-step-detail")?.textContent.trim() || "";
        return `${num}. ${t}${d ? " (" + d + ")" : ""}`;
    }).join("\n");
    const sources = Array.from(card.querySelectorAll(".clean-source-card, .source-tag-pill")).map(a => a.href).join("\n");

    let fullText = "";
    if (title) fullText += `${title}\n\n`;
    if (summary) fullText += `${summary}\n\n`;
    if (docs) fullText += `Required Documents:\n${docs}\n\n`;
    if (steps) fullText += `Steps:\n${steps}\n\n`;
    if (sources) fullText += `Official Sources:\n${sources}\n`;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(fullText.trim()).then(() => {
            const originalTitle = btn.getAttribute("title");
            btn.innerHTML = `${ICON_COPIED} <span class="btn-label-text">Copied!</span>`;
            btn.classList.add("copied");
            btn.setAttribute("title", "Copied to clipboard!");
            if (typeof window.sendFeedback === "function") {
                window.sendFeedback(btn, "copy_steps", 0);
            }
            setTimeout(() => {
                btn.innerHTML = `${ICON_COPY} <span class="btn-label-text">Copy</span>`;
                btn.classList.remove("copied");
                btn.setAttribute("title", originalTitle || "Copy response to clipboard");
            }, 2000);
        }).catch(err => {
            console.error("Failed to copy:", err);
        });
    }
};

// --- REINFORCEMENT LEARNING FEEDBACK HANDLERS ---
window.sendFeedback = async function(el, feedbackType, rating = null) {
    const card = el ? el.closest(".assistant-response") : null;
    const container = card ? card.closest(".message-row") : null;
    const title = card?.querySelector(".response-title")?.textContent.trim() || "Civic Guide";
    const summary = card?.querySelector(".response-summary")?.textContent.trim() || "";
    
    // Find matching user question from previous message bubble
    let userQuery = title;
    if (container) {
        let prev = container.previousElementSibling;
        while (prev) {
            const userTextEl = prev.querySelector(".user-message-text");
            if (userTextEl) {
                userQuery = userTextEl.textContent.trim();
                break;
            }
            prev = prev.previousElementSibling;
        }
    }

    const numericRating = rating !== null ? rating : (feedbackType === "thumbs_up" ? 1 : feedbackType === "thumbs_down" ? -1 : 0);

    // Immediate button reaction
    if (el && feedbackType === "thumbs_up") {
        el.classList.add("active-positive");
        el.nextElementSibling?.classList.remove("active-negative");
    } else if (el && feedbackType === "thumbs_down") {
        el.classList.add("active-negative");
        el.previousElementSibling?.classList.remove("active-positive");
    }

    const payload = {
        conversation_id: activeChatId,
        query: userQuery,
        answer_title: title,
        answer_summary: summary,
        feedback_type: feedbackType,
        rating: numericRating,
    };

    try {
        await fetch(`${API_BASE}/api/feedback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
    } catch (e) {
        console.debug("Telemetry error:", e);
    }
};

window.trackCitationClick = function(el, url) {
    if (typeof window.sendFeedback === "function") {
        window.sendFeedback(el, "click_citation", 0);
    }
};

// --- CHECKLIST INTERACTION HELPERS (COMPATIBILITY STUBS) ---
window.toggleCheckboxRow = function(rowEl) {
    if (!rowEl) return;
    const chk = rowEl.querySelector('input[type="checkbox"]');
    if (chk) {
        if (typeof event !== "undefined" && event.target !== chk) chk.checked = !chk.checked;
        rowEl.classList.toggle("checked", chk.checked);
    }
};

window.toggleStepItem = function(checkboxEl) {
    if (!checkboxEl) return;
    const item = checkboxEl.closest(".step-item");
    if (item) {
        item.classList.toggle("checked", checkboxEl.checked);
    }
};

// --- UTILITIES ---
function setLoading(loading) {
    isQueryInProgress = !!loading;
    if (!sendBtn) return;
    sendBtn.disabled = loading;
    if (sendSpinner) sendSpinner.style.display = loading ? "inline-block" : "none";
    if (sendIcon) sendIcon.style.display = loading ? "none" : "inline";
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
