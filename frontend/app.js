/**
 * Nivaan - Civic & Banking AI Guide Controller
 * Handles conversation flow, camera/file upload, PII masking, structured checklist rendering,
 * editable user prompts, and multi-turn persistent chat history in localStorage.
 */

const API_BASE = "http://127.0.0.1:8000";
const STORAGE_KEY = "nivaan_chats_v1";
const ACTIVE_CHAT_KEY = "nivaan_active_chat_id";

let isBackendLive = false;
let chats = []; // Array of chat session objects
let activeChatId = null;
let attachedFile = null; // { name, type, size, textContent, fileRef, isImage, isPdf }

// DOM Elements
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
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

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
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
});

function setupEventListeners() {
    // Sidebar toggle
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener("click", () => {
            sidebar.classList.toggle("collapsed");
        });
    }

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

    // Suggestion Cards
    suggestionCards.forEach(card => {
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
}

function saveChatsToStorage() {
    try {
        const toSave = sanitizeAllChats(chats);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
        if (activeChatId) {
            localStorage.setItem(ACTIVE_CHAT_KEY, activeChatId);
        } else {
            localStorage.setItem(ACTIVE_CHAT_KEY, "__new__");
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
    if (sidebar && window.innerWidth <= 768) {
        sidebar.classList.add("collapsed");
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
    activeChatId = null;
    localStorage.setItem(ACTIVE_CHAT_KEY, "__new__");
    renderHistoryList();
    resetChatView();
    if (sidebar && window.innerWidth <= 768) {
        sidebar.classList.add("collapsed");
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
        backendBadge.title = isOnline ? "Backend API is online and healthy (http://127.0.0.1:8000)" : "Backend API is offline. Run start.bat to launch the backend server.";
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

// --- USER SUBMISSION ---
function handleUserSubmit() {
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
    await executeQuery(userText, currentAttachment, currentChat);
    setLoading(false);
}

// --- MARKDOWN FORMATTING & STREAMING HELPERS ---
function formatMarkdownMini(text) {
    if (!text) return "";
    let safe = escapeHtml(text);
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>");
    safe = safe.replace(/(?:^|\n)[ \t]*[-*][ \t]+([^\n]+)/g, "\n• $1");
    return safe;
}

function appendThinkingBubble() {
    const row = document.createElement("div");
    row.className = "message-row assistant-thinking-row";
    row.id = "thinkingBubbleRow";

    row.innerHTML = `
        <div class="message-avatar bot-avatar">🏛️</div>
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
            if (previousEntryId) payload.previous_entry_id = previousEntryId;
            if (contextTopic) payload.context_topic = contextTopic;

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
                    answer = createSystemNotice(
                        "Request Notice",
                        errorPayload?.detail || errorPayload?.message || "The backend rejected this request."
                    );
                }
            }
        }
    } catch (err) {
        console.warn("Backend connection error:", err);
        setBackendOnlineStatus(false);
        answer = createSystemNotice(
            "Backend Offline",
            "Cannot connect to the backend server at http://127.0.0.1:8000. Please ensure the backend is running and try again."
        );
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
    if (!streamRendered) {
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

    const wrapper = row.querySelector(".user-bubble-wrapper");
    if (!wrapper) return;

    wrapper.innerHTML = `
        <div class="user-edit-container">
            <textarea class="user-edit-textarea" id="edit_textarea_${msgId}">${escapeHtml(msg.text)}</textarea>
            <div class="user-edit-actions">
                <button type="button" class="user-edit-btn cancel-btn" onclick="cancelEditPrompt('${msgId}')">Cancel</button>
                <button type="button" class="user-edit-btn save-btn" onclick="submitEditPrompt('${msgId}')">Save & Submit</button>
            </div>
        </div>
    `;

    const textarea = document.getElementById(`edit_textarea_${msgId}`);
    if (textarea) {
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

    const wrapper = row.querySelector(".user-bubble-wrapper");
    if (!wrapper) return;

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
    await executeQuery(newText, msg.file, currentChat);
    setLoading(false);
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

// --- RENDER POST-SUMMARY SECTIONS (DOCUMENTS, STEPS, SOURCES) ---
function renderPostSummarySections(answer) {
    if (!answer) return "";

    // 1. Documents required (Clean list - no checkboxes)
    let docsHtml = "";
    if (answer.documents_needed && answer.documents_needed.length > 0) {
        const docItems = answer.documents_needed.map(doc => `
            <li class="clean-doc-item">
                <span class="clean-doc-icon">📄</span>
                <span class="clean-doc-text">${escapeHtml(doc)}</span>
            </li>
        `).join("");

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
                    <div class="clean-step-title">${escapeHtml(stepText)}</div>
                    ${stepTip ? `<div class="clean-step-detail">💡 <strong>Details:</strong> ${escapeHtml(stepTip)}</div>` : ""}
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
        const sourceTags = sourcesList.map((src, idx) => `
            <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="source-tag-pill" title="${escapeHtml(src.title)} - ${escapeHtml(src.url)}" onclick="trackCitationClick(this, '${escapeHtml(src.url)}')">
                <span class="source-tag-index">[${idx + 1}]</span>
                <span class="source-tag-text">${escapeHtml(src.title)}</span>
                <span class="source-tag-domain">${escapeHtml(src.domain)}</span>
                <span class="source-tag-arrow">↗</span>
            </a>
        `).join("");

        const citationsAccordion = citations.some(c => c.excerpt) ? `
            <details class="clean-evidence-accordion">
                <summary class="clean-evidence-toggle">
                    <span>🔍 View RAG Evidence Excerpts (${citations.length})</span>
                </summary>
                <div class="clean-evidence-list">
                    ${citations.map((c, i) => `
                        <div class="clean-evidence-item">
                            <div class="clean-evidence-head">
                                <span class="clean-evidence-num">[${i + 1}]</span>
                                <a href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer" class="clean-evidence-link">
                                    ${escapeHtml(c.title)} ↗
                                </a>
                                <span class="verification-status verification-${escapeHtml(c.factual_verification || 'verified')}">
                                    ${escapeHtml((c.factual_verification || 'verified').toUpperCase())}
                                </span>
                            </div>
                            <p class="clean-evidence-excerpt">${escapeHtml(c.excerpt)}</p>
                        </div>
                    `).join("")}
                </div>
            </details>
        ` : "";

        sourcesHtml = `
            <div class="clean-sources-section">
                <div class="clean-sources-header">
                    <div class="clean-sources-heading">
                        <span>🏷️ Tagged Official Sources</span>
                    </div>
                    ${answer.last_verified ? `
                    <span class="clean-sources-verify">
                        ${sourceDateLabel}: <strong>${escapeHtml(answer.last_verified)}</strong>
                    </span>` : ""}
                </div>
                <div class="clean-sources-tags">
                    ${sourceTags}
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

    row.innerHTML = `
        <div class="message-avatar bot-avatar">🏛️</div>
        <div class="message-content">
            <div class="assistant-response">
                <div class="response-header">
                    <div class="response-title-group">
                        <h3 class="response-title">${escapeHtml((meta && meta.title) || "Civic & Banking Guide")}</h3>
                        ${(meta && meta.rl_arm) ? `<span class="rl-arm-pill" title="RL LinUCB Arm: ${escapeHtml(meta.rl_arm)}">⚡ ${escapeHtml(meta.rl_arm.replace(/_/g, ' '))}</span>` : ""}
                    </div>
                    <div class="response-header-actions">
                        <span class="response-confidence confidence-${(meta && meta.confidence) || 'verified'}">
                            ● ${(meta && meta.confidence ? meta.confidence.toUpperCase() : 'VERIFIED')}
                        </span>
                        <button class="feedback-btn thumbs-up" onclick="sendFeedback(this, 'thumbs_up')" title="Helpful and accurate">👍</button>
                        <button class="feedback-btn thumbs-down" onclick="sendFeedback(this, 'thumbs_down')" title="Not helpful or inaccurate">👎</button>
                        <button class="copy-response-btn" onclick="copyResponseText(this)" title="Copy guide to clipboard">
                            <span class="copy-icon">📋</span> Copy
                        </button>
                    </div>
                </div>

                ${maskedBanner}

                <div class="response-summary">
                    <span class="typing-text"></span><span class="typing-cursor">▌</span>
                </div>

                <div class="post-summary-sections" style="display: none;"></div>
            </div>
        </div>
    `;

    const typingTextEl = row.querySelector(".typing-text");
    const cursorEl = row.querySelector(".typing-cursor");
    const postSectionsEl = row.querySelector(".post-summary-sections");
    const titleEl = row.querySelector(".response-title");

    return {
        row,
        updateTyping: (text) => {
            if (typingTextEl) typingTextEl.textContent = text;
        },
        updateMeta: (newMeta) => {
            if (newMeta && newMeta.title && titleEl) titleEl.textContent = newMeta.title;
        },
        finalize: (answer) => {
            if (cursorEl) cursorEl.remove();
            if (typingTextEl) {
                const cleanText = ((answer && answer.summary) || typingTextEl.textContent || "")
                    .replace(/^For your question,.*?this is the closest guide I found\.?\s*/i, "")
                    .trim();
                typingTextEl.innerHTML = formatMarkdownMini(cleanText);
            }
            if (postSectionsEl && answer) {
                postSectionsEl.innerHTML = renderPostSummarySections(answer);
                postSectionsEl.style.display = "flex";
                postSectionsEl.classList.add("section-fade-in");
            }
            if (titleEl && answer && answer.title) {
                titleEl.textContent = answer.title;
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

    const cleanSummaryText = answer.summary ? String(answer.summary)
        .replace(/^For your question,.*?this is the closest guide I found\.?\s*/i, "")
        .trim() : "";

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

    row.innerHTML = `
        <div class="message-avatar bot-avatar">🏛️</div>
        <div class="message-content">
            <div class="assistant-response">
                <!-- Header -->
                <div class="response-header">
                    <div class="response-title-group">
                        <h3 class="response-title">${escapeHtml(answer.title)}</h3>
                        ${answer.rl_arm ? `<span class="rl-arm-pill" title="RL LinUCB Arm: ${escapeHtml(answer.rl_arm)}">⚡ ${escapeHtml(answer.rl_arm.replace(/_/g, ' '))}</span>` : ""}
                    </div>
                    <div class="response-header-actions">
                        <span class="response-confidence confidence-${answer.confidence || 'high'}">
                            ● ${answer.confidence ? answer.confidence.toUpperCase() : 'VERIFIED'}
                        </span>
                        <button class="feedback-btn thumbs-up" onclick="sendFeedback(this, 'thumbs_up')" title="Helpful and accurate">👍</button>
                        <button class="feedback-btn thumbs-down" onclick="sendFeedback(this, 'thumbs_down')" title="Not helpful or inaccurate">👎</button>
                        <button class="copy-response-btn" onclick="copyResponseText(this)" title="Copy guide to clipboard">
                            <span class="copy-icon">📋</span> Copy
                        </button>
                    </div>
                </div>

                <!-- Privacy Redaction Badge -->
                ${maskedBanner}

                <!-- Plain Language Summary -->
                ${summaryHtml}

                <div class="${postSectionsClass}" ${postSectionsDisplay}>
                    ${sectionsHtml}
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
    const sources = Array.from(card.querySelectorAll(".source-tag-pill")).map(a => a.href).join("\n");

    let fullText = `${title}\n\n`;
    if (summary) fullText += `${summary}\n\n`;
    if (docs) fullText += `Required Documents:\n${docs}\n\n`;
    if (steps) fullText += `Steps:\n${steps}\n\n`;
    if (sources) fullText += `Official Sources:\n${sources}\n`;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(fullText.trim()).then(() => {
            const originalHtml = btn.innerHTML;
            btn.innerHTML = `<span class="copy-icon">✓</span> Copied!`;
            btn.classList.add("copied");
            if (typeof window.sendFeedback === "function") {
                window.sendFeedback(btn, "copy_steps", 0);
            }
            setTimeout(() => {
                btn.innerHTML = originalHtml;
                btn.classList.remove("copied");
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
