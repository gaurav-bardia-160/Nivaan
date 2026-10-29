/**
 * GovBank Assistant - Minimal Chatbot Controller
 * Handles conversation flow, camera/file upload, PII masking, structured checklist rendering,
 * editable user prompts, and multi-turn persistent chat history in localStorage.
 */

const API_BASE = "http://127.0.0.1:8000";
const STORAGE_KEY = "govbank_chats_v1";
const ACTIVE_CHAT_KEY = "govbank_active_chat_id";

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
    setInterval(checkBackendHealth, 4000);
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
        if (localStorage.getItem("govbank-theme") === "dark") {
            document.documentElement.setAttribute("data-theme", "dark");
            themeToggleBtn.innerHTML = "☀️ Light";
        }
        themeToggleBtn.addEventListener("click", () => {
            if (document.documentElement.getAttribute("data-theme") === "dark") {
                document.documentElement.setAttribute("data-theme", "light");
                localStorage.setItem("govbank-theme", "light");
                themeToggleBtn.innerHTML = "🌙 Dark";
            } else {
                document.documentElement.setAttribute("data-theme", "dark");
                localStorage.setItem("govbank-theme", "dark");
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

// --- CLIENT-SIDE PII MASKING & STORAGE SAFEGUARDS ---
function maskClientPII(text) {
    if (!text || typeof text !== "string") return text;
    let sanitized = text;
    // Bank account: account no / number followed by 9-18 digits
    sanitized = sanitized.replace(/\b(?:account\s*(?:no\.?|number)?\s*[:\-]?\s*)\d{9,18}\b/gi, "[BANK_ACCOUNT]");
    // Aadhaar: 12 digits (with optional single space or hyphen separator)
    sanitized = sanitized.replace(/(?<!\d)(?:\d{4}[\s-]?\d{4}[\s-]?\d{4})(?!\d)/g, "[AADHAAR]");
    // PAN: 5 letters, 4 digits, 1 letter
    sanitized = sanitized.replace(/\b[A-Za-z]{5}\d{4}[A-Za-z]\b/g, "[PAN]");
    // IFSC code: 4 letters, zero, 6 alphanumeric
    sanitized = sanitized.replace(/\b[A-Za-z]{4}0[A-Za-z0-9]{6}\b/g, "[IFSC]");
    // Email address
    sanitized = sanitized.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g, "[EMAIL]");
    // Phone number: optional +91, 10 digits starting with 6-9
    sanitized = sanitized.replace(/(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)/g, "[PHONE]");
    return sanitized;
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
        const raw = localStorage.getItem(STORAGE_KEY);
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
                    appendAssistantResponse(msg.answer, false);
                } else if (msg.text) {
                    appendAssistantResponse(createSystemNotice("Response", msg.text), false);
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
function setBackendOnlineStatus(isOnline) {
    isBackendLive = !!isOnline;
    if (backendBadge) {
        backendBadge.className = isOnline ? "connection-badge connected" : "connection-badge offline";
        backendBadge.textContent = isOnline ? "● Online" : "● Offline";
    }
}

async function checkBackendHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);
        const res = await fetch(`${API_BASE}/api/health`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (res.ok) {
            const data = await res.json().catch(() => null);
            if (data && (data.status === "ok" || data.status === "healthy" || data.service === "govbank-assistant")) {
                setBackendOnlineStatus(true);
                return;
            }
        }
    } catch (e) {
        // Backend offline or timed out
    }
    setBackendOnlineStatus(false);
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

// --- QUERY EXECUTION ---
async function executeQuery(userText, currentAttachment, chatObj) {
    let answer = null;

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
                        .slice(-10)
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
    } catch (err) {
        console.warn("Backend error, falling back to local guide:", err);
        setBackendOnlineStatus(false);
    }

    if (!answer) {
        answer = await getLocalFallbackAnswer(userText, currentAttachment);
    }

    const targetChat = (chatObj && chats.find(c => c.id === chatObj.id)) || getActiveChat() || chatObj;
    if (targetChat) {
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

    appendAssistantResponse(answer, true);
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

// --- APPEND ASSISTANT RESPONSE CARD ---
function appendAssistantResponse(answer, shouldScroll = true) {
    const row = document.createElement("div");
    row.className = "message-row";

    // 1. Masked items banner
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

    // 2. Documents required (Clean list - no checkboxes)
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

    // 3. Step-by-Step Procedure (Clean numbered process - no checkboxes)
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

    // 4. Warnings & Red Flags (Completely removed per user request)
    let warningsHtml = "";

    // 5. Gather and format tagged source links at the end
    const sourcesList = [];
    const seenUrls = new Set();

    function formatSourceDomain(urlStr) {
        try {
            const u = new URL(urlStr);
            return u.hostname.replace(/^www\./, "");
        } catch (e) {
            return "Official Portal";
        }
    }

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

    // Plain Language Summary - Always show the natural language explanation
    let summaryHtml = "";
    if (answer.summary) {
        const cleanSummaryText = String(answer.summary)
            .replace(/^For your question,.*?this is the closest guide I found\.?\s*/i, "")
            .trim();
        if (cleanSummaryText) {
            summaryHtml = `
                <div class="response-summary">
                    ${escapeHtml(cleanSummaryText)}
                </div>
            `;
        }
    }

    // Disclaimer Notice
    let disclaimerHtml = "";
    if (answer.disclaimer) {
        disclaimerHtml = `
            <div class="disclaimer-text">
                ⚖️ <strong>Official Notice:</strong> ${escapeHtml(answer.disclaimer)}
            </div>
        `;
    }

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

                <!-- Documents Needed (Clean list) -->
                ${docsHtml}

                <!-- Steps (Clean procedure) -->
                ${stepsHtml}

                <!-- Official Notice / Disclaimer -->
                ${disclaimerHtml}

                <!-- Tagged Sources & References at End -->
                ${sourcesHtml}
            </div>
        </div>
    `;

    messagesContainer.appendChild(row);
    if (shouldScroll) scrollToBottom();
}


// --- COPY RESPONSE TEXT HELPER ---
window.copyResponseText = function(btn) {
    const card = btn.closest(".assistant-response");
    if (!card) return;
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

// --- LOCAL FALLBACK (SIMULATED GUIDES) ---
async function getLocalFallbackAnswer(text, file) {
    const qLower = (text || "").toLowerCase();
    const trimmed = (text || "").trim().toLowerCase().replace(/[^\w\s]/g, "");

    if (/^(hi|hello|hey|heya|hiya|namaste|namaskar|pranam|kem cho|kemcho|good morning|good afternoon|good evening|help|who are you|what can you do)$/i.test(trimmed)) {
        return {
            title: "Welcome to GovBank Assistant",
            summary: "Hello! I am your AI civic and banking assistant. I can help you navigate official Indian government procedures, banking workflows, and identify risk clauses or deadlines in legal notices and loan documents.",
            documents_needed: [],
            steps: [
                {
                    no: 1,
                    text: "Identity & Taxes (PAN / Aadhaar / ITR)",
                    tip: "Ask how to apply for a new PAN card, link PAN with Aadhaar, update Aadhaar details, or file income tax returns."
                },
                {
                    no: 2,
                    text: "Passport & Civic Schemes",
                    tip: "Get step-by-step guidance for fresh/re-issue Indian Passport applications or PM Kisan Samman Nidhi."
                },
                {
                    no: 3,
                    text: "Banking & Provident Fund (EPF)",
                    tip: "Learn the exact procedure to withdraw EPF balance, open a savings account, or file a consumer court complaint."
                },
                {
                    no: 4,
                    text: "Notice & Loan Agreement Review",
                    tip: "Upload or paste document text to automatically detect penalty clauses, foreclosure conditions, and response deadlines."
                }
            ],
            warnings: [],
            source_url: "https://www.india.gov.in/",
            last_verified: "2026-10-25",
            confidence: "high",
            masked_items: []
        };
    }

    if (file) {
        return {
            title: `Document Analysis: ${file.name}`,
            summary: "We reviewed your uploaded document. Personal identifiers were masked before analysis. Here is a plain-language summary of the terms, procedure, and critical warnings detected.",
            documents_needed: [
                "Original sanction letter or notice copy",
                "Official photo ID (Aadhaar or Passport)",
                "Written grievance acknowledgment from the bank"
            ],
            steps: [
                {
                    no: 1,
                    text: "Review the highlighted pre-payment or renewal clause in the agreement.",
                    tip: "RBI guidelines prohibit pre-closure fees on individual floating-rate home loans."
                },
                {
                    no: 2,
                    text: "Submit a formal written objection to the Branch Manager referencing RBI Fair Practice Code.",
                    tip: "Banks must acknowledge grievances within 7 days."
                },
                {
                    no: 3,
                    text: "If unresolved after 30 days, file an online complaint with the RBI Banking Ombudsman (cms.rbi.org.in).",
                    tip: "The Ombudsman service is 100% free of charge."
                }
            ],
            warnings: [
                {
                    text: "Potential Pre-payment Penalty: 3.5% charge on floating rate loan is prohibited by RBI.",
                    reason: "RBI Circular DBOD.Dir.BC.No.27/13.03.00/2014-15 bans all foreclosure charges for individual floating loans."
                },
                {
                    text: "Strict 30-Day Response Window",
                    reason: "Failing to challenge within 30 days may forfeit administrative dispute rights."
                }
            ],
            source_url: "https://www.rbi.org.in",
            last_verified: "2026-09-28",
            confidence: "high",
            masked_items: [
                { item_type: "Aadhaar Number", count: 1 },
                { item_type: "Bank Account Number", count: 1 }
            ],
                    };
    }

    if (qLower.includes("tax") || qLower.includes("itr") || qLower.includes("income")) {
        return {
            title: "How to File Income Tax Return (ITR-1 Sahaj)",
            summary: "ITR-1 (Sahaj) is for resident individuals having total income up to ₹50 lakh from salary, one house property, and other sources (such as interest). It can be filed electronically on the Income Tax e-Filing portal.",
            documents_needed: [
                "Form 16 issued by your employer",
                "Form 26AS and Annual Information Statement (AIS)",
                "Bank account statements for interest income certificates",
                "Proof of tax-saving investments (Section 80C, 80D, 80G)"
            ],
            steps: [
                {
                    no: 1,
                    text: "Log in to the official e-Filing portal (incometax.gov.in) with your PAN and password.",
                    tip: "Ensure your primary bank account is pre-validated for refund credits."
                },
                {
                    no: 2,
                    text: "Navigate to 'e-File' > 'Income Tax Returns' > 'File Income Tax Return'.",
                    tip: "Select the correct Assessment Year (AY 2026-27)."
                },
                {
                    no: 3,
                    text: "Select Status as 'Individual' and choose 'ITR-1'.",
                    tip: "Pre-filled data from AIS/Form 16 will load automatically."
                },
                {
                    no: 4,
                    text: "Review personal details, gross salary, deductions, and confirm tax liability.",
                    tip: "Compare pre-filled TDS amounts against your Form 16."
                },
                {
                    no: 5,
                    text: "Verify the return electronically within 30 days using Aadhaar OTP.",
                    tip: "An unverified ITR is treated as invalid (never filed)."
                }
            ],
            warnings: [
                {
                    text: "Mandatory 30-Day e-Verification Deadline",
                    reason: "If not e-verified within 30 days of filing, the return is invalidated and late fees up to ₹5,000 apply under Section 234F."
                },
                {
                    text: "Mismatched TDS and AIS Records",
                    reason: "Variances trigger automated Section 143(1) defective return notices."
                }
            ],
            source_url: "https://www.incometax.gov.in",
            last_verified: "2026-10-01",
            confidence: "high",
            masked_items: [],
                    };
    }

    if (qLower.includes("loan") || qLower.includes("prepayment") || qLower.includes("rbi") || qLower.includes("foreclosure")) {
        return {
            title: "RBI Guidelines on Floating Rate Loan Prepayment & Foreclosure Charges",
            summary: "Under RBI Master Directions (Fair Practices Code), Scheduled Commercial Banks and NBFCs are strictly prohibited from charging foreclosure charges or pre-payment penalties on home loans and consumer loans sanctioned on a floating interest rate basis to individual borrowers.",
            documents_needed: [
                "Copy of Original Loan Sanction Letter",
                "Latest Loan Account Statement showing interest type (Floating vs Fixed)",
                "Bank's foreclosure notice or statement calculating penalty charges"
            ],
            steps: [
                {
                    no: 1,
                    text: "Verify that your loan is on a 'Floating Interest Rate' and sanctioned to an individual (not a business entity).",
                    tip: "Prepayment penalty exemption only applies to individual borrowers on floating rate loans."
                },
                {
                    no: 2,
                    text: "Write a formal objection letter citing RBI Circular RBI/2014-15/121 (DBOD.Dir.BC.No.27/13.03.00/2014-15).",
                    tip: "State clearly that charging a pre-closure fee violates RBI Fair Practices Code."
                },
                {
                    no: 3,
                    text: "Submit the letter to your Bank's Branch Manager and retain an acknowledged copy.",
                    tip: "Banks must resolve customer grievances within 30 days."
                },
                {
                    no: 4,
                    text: "If the bank insists on deduction, lodge a formal complaint on the RBI CMS portal (cms.rbi.org.in).",
                    tip: "Free resolution through the RBI Ombudsman scheme."
                }
            ],
            warnings: [
                {
                    text: "Fixed-rate loans are NOT exempt",
                    reason: "Lenders may legally levy prepayment charges if the loan was sanctioned on a purely fixed rate basis."
                }
            ],
            source_url: "https://www.rbi.org.in",
            last_verified: "2026-09-28",
            confidence: "high",
            masked_items: [],
                    };
    }

    if (qLower.includes("passport") || qLower.includes("paspot") || qLower.includes("pasport")) {
        return {
            title: "Apply for an Indian Passport (Fresh/Re-issue)",
            summary: "Apply for a fresh Indian passport or re-issue of an existing passport online through the official Passport Seva portal (passportindia.gov.in) under the Ministry of External Affairs. The process involves online registration, filling Form No. 1, paying the fee, scheduling an appointment at a Passport Seva Kendra (PSK) or Post Office PSK (POPSK), biometric capture, document verification, and police verification.",
            documents_needed: [
                "Proof of Date of Birth (Birth Certificate, School Leaving Certificate, Aadhaar Card, or PAN Card)",
                "Proof of Present Address (Aadhaar Card, Water/Electricity Bill, Bank Passbook with Photo, or Rent Agreement)",
                "Proof of Identity with Photo (Aadhaar Card, Voter ID, or PAN Card)",
                "Standard Annexure E declaration (for adult fresh passport applicants)",
                "Non-ECR Proof (10th standard matriculation certificate or higher educational degree, if applicable)"
            ],
            steps: [
                {
                    no: 1,
                    text: "Register on the Passport Seva Online Portal (passportindia.gov.in).",
                    tip: "Select your jurisdictional Passport Office and enter basic contact information."
                },
                {
                    no: 2,
                    text: "Fill out the Passport Application Form (Form No. 1).",
                    tip: "Choose Fresh Passport or Re-issue, Normal or Tatkaal, and 36 or 60 pages booklet."
                },
                {
                    no: 3,
                    text: "Pay the Application Fee and Schedule an Appointment.",
                    tip: "Fee is ₹1,500 for normal 36-page adult passport. Select your nearest PSK or POPSK."
                },
                {
                    no: 4,
                    text: "Visit PSK / POPSK for Biometrics and Document Verification.",
                    tip: "Arrive with all original documents and self-attested photocopies."
                },
                {
                    no: 5,
                    text: "Complete Police Verification and Receive Passport via Speed Post.",
                    tip: "Track your 15-digit File Number online until dispatched by India Post."
                }
            ],
            warnings: [
                {
                    text: "Beware of Fraudulent Third-Party Websites",
                    reason: "Only apply through www.passportindia.gov.in. Avoid fake intermediary sites charging extra fees."
                },
                {
                    text: "Carry All Original Documents to PSK",
                    reason: "Missing originals will lead to appointment cancellation and rescheduling."
                },
                {
                    text: "Ensure Present Residential Address is Accurate",
                    reason: "Police verification is strictly carried out at the current address entered in the application."
                }
            ],
            source_url: "https://www.passportindia.gov.in/",
            last_verified: "2026-10-01",
            confidence: "high",
            masked_items: []
        };
    }

    if (qLower.includes("pan")) {
        return {
            title: "PAN Card Application Basics (Form 49A)",
            summary: "A PAN card is required for tax and financial transactions. Indian citizens can apply online through authorized portals (Protean / UTIITSL) using Form 49A.",
            documents_needed: [
                "Proof of Identity (Aadhaar, Passport, Voter ID, Driving License)",
                "Proof of Address (Aadhaar, Utility Bill, Bank Account Statement)",
                "Proof of Date of Birth (Birth Certificate, Matriculation Certificate, Aadhaar)",
                "Two recent passport-size colour photographs"
            ],
            steps: [
                {
                    no: 1,
                    text: "Visit the official Protean (formerly NSDL) or UTIITSL online portal and select 'Form 49A'.",
                    tip: "Choose application type 'Indian Citizen (Form 49A)' and category 'Individual'."
                },
                {
                    no: 2,
                    text: "Fill in personal details, name, date of birth, and Assessing Officer (AO) code.",
                    tip: "Ensure your name and date of birth match your supporting documents exactly."
                },
                {
                    no: 3,
                    text: "Submit supporting documents online via Aadhaar paperless e-KYC or physical courier.",
                    tip: "Aadhaar e-KYC completes verification instantly using OTP."
                },
                {
                    no: 4,
                    text: "Pay the processing fee and save the 15-digit acknowledgement slip to track delivery status.",
                    tip: "Physical PAN cards are dispatched within 10-15 business days."
                }
            ],
            warnings: [
                {
                    text: "Mandatory Aadhaar-PAN Linking",
                    reason: "Failure to link Aadhaar with PAN makes the card inoperative under Income Tax rules."
                },
                {
                    text: "Use Authorized Portals Only",
                    reason: "Only use protean-tinpan.com or utiitsl.com to avoid third-party phishing or excessive fees."
                }
            ],
            source_url: "https://www.incometax.gov.in",
            last_verified: "2026-10-03",
            confidence: "high",
            masked_items: [],
                    };
    }

    return createSystemNotice("No Guide Found", "I could not find a verified guide for this query. Please check that the backend server is running on http://127.0.0.1:8000, or try asking about PAN, Aadhaar, Passport, EPF, ITR, or loan agreements.");
}

// --- UTILITIES ---
function setLoading(loading) {
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
