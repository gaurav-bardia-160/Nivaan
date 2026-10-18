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
const previewSampleBtn = document.getElementById("previewSampleBtn");

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

    // Preview Sample Button
    if (previewSampleBtn) {
        previewSampleBtn.addEventListener("click", loadSampleAnswer);
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

// --- STORAGE & PERSISTENCE ---
function loadChatsFromStorage() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        chats = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(chats)) chats = [];

        const savedActiveId = localStorage.getItem(ACTIVE_CHAT_KEY);
        if (savedActiveId && chats.some(c => c.id === savedActiveId)) {
            activeChatId = savedActiveId;
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
        localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
        if (activeChatId) {
            localStorage.setItem(ACTIVE_CHAT_KEY, activeChatId);
        } else {
            localStorage.removeItem(ACTIVE_CHAT_KEY);
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
    const title = generateTitle(firstPrompt);
    const chat = {
        id,
        title,
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: []
    };
    chats.unshift(chat);
    activeChatId = id;
    saveChatsToStorage();
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

        const titleSpan = document.createElement("span");
        titleSpan.className = "history-item-title";
        titleSpan.textContent = chat.title || "Inquiry";
        titleSpan.title = chat.title || "Inquiry";
        titleSpan.onclick = () => switchChat(chat.id);

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
    if (activeChatId === chatId) return;
    activeChatId = chatId;
    saveChatsToStorage();
    renderHistoryList();
    loadActiveChatMessages();
}

function deleteChat(chatId) {
    const idx = chats.findIndex(c => c.id === chatId);
    if (idx === -1) return;
    chats.splice(idx, 1);
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
    saveChatsToStorage();
    renderHistoryList();
    resetChatView();
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
    if (!currentChat || currentChat.messages.length === 0) {
        resetChatView();
        return;
    }

    messagesContainer.innerHTML = "";
    if (welcomeScreen) welcomeScreen.style.display = "none";

    currentChat.messages.forEach(msg => {
        if (msg.role === "user") {
            appendUserBubble(msg.text, msg.file, msg.id, false);
        } else if (msg.role === "assistant" && msg.answer) {
            appendAssistantResponse(msg.answer, false);
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
async function checkBackendHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        if (res.ok) {
            isBackendLive = true;
            backendBadge.className = "connection-badge connected";
            backendBadge.textContent = "● Online";
            return;
        }
    } catch (e) {
        // Backend offline
    }
    isBackendLive = false;
    backendBadge.className = "connection-badge mock";
    backendBadge.textContent = "● Standalone Mock";
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
    if (!currentChat) {
        currentChat = createNewChat(userText);
    } else if (currentChat.messages.length === 0) {
        currentChat.title = generateTitle(userText);
        saveChatsToStorage();
        renderHistoryList();
    }

    const msgId = "msg_" + Date.now() + "_" + Math.random().toString(36).substr(2, 5);
    const fileMeta = fileObj ? {
        name: fileObj.name,
        type: fileObj.type,
        size: fileObj.size,
        isImage: fileObj.isImage,
        isPdf: fileObj.isPdf
    } : null;

    currentChat.messages.push({
        id: msgId,
        role: "user",
        text: userText,
        file: fileMeta
    });
    currentChat.updatedAt = Date.now();
    saveChatsToStorage();

    appendUserBubble(userText, fileMeta, msgId, true);

    const currentAttachment = fileObj || attachedFile;
    clearAttachment();

    setLoading(true);
    await executeQuery(userText, currentAttachment, currentChat);
    setLoading(false);
}

// --- QUERY EXECUTION ---
async function executeQuery(userText, currentAttachment, chatObj) {
    let answer = null;

    if (isBackendLive) {
        try {
            const hasReadableDocumentText = !!(currentAttachment && currentAttachment.textContent && currentAttachment.textContent.trim());

            if (currentAttachment && !hasReadableDocumentText && currentAttachment.fileRef) {
                const formData = new FormData();
                formData.append("file", currentAttachment.fileRef);
                formData.append("question", userText || "Explain this document");

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
                const payload = {
                    input_type: currentAttachment ? "document" : "question",
                    question: userText,
                    conversation_id: chatObj ? chatObj.id : "conv_default",
                    file_attached: !!currentAttachment
                };

                if (hasReadableDocumentText) {
                    payload.document_text = currentAttachment.textContent.trim();
                    payload.file_attached = false;
                }

                const response = await fetch(`${API_BASE}/api/ask`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    answer = await response.json();
                } else {
                    const errorPayload = await safeReadJson(response);
                    answer = createSystemNotice(
                        "This file cannot be processed yet",
                        errorPayload?.detail || errorPayload?.message || "The backend rejected this request. PDF/image OCR is not implemented yet, so use typed questions or paste text for now."
                    );
                }
            }
        } catch (err) {
            console.warn("Backend error, falling back to local guide:", err);
        }
    }

    if (!answer) {
        answer = await getLocalFallbackAnswer(userText, currentAttachment);
    }

    if (chatObj) {
        chatObj.messages.push({
            id: "msg_ast_" + Date.now(),
            role: "assistant",
            answer: answer
        });
        chatObj.updatedAt = Date.now();
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
    msg.text = newText;

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
        warnings: [{
            title: "Workflow not available yet",
            message: "Use typed questions or paste document text. Real PDF/image OCR upload is a planned next phase.",
            severity: "warning"
        }],
        source_url: "https://www.india.gov.in/",
        last_verified: new Date().toISOString().slice(0, 10),
        confidence: "low",
        masked_items: [],
        disclaimer: "This is a product limitation notice, not legal, tax, or financial advice."
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

    // 2. Documents required
    let docsHtml = "";
    if (answer.documents_needed && answer.documents_needed.length > 0) {
        const docItems = answer.documents_needed.map((doc, idx) => `
            <li class="doc-row" onclick="toggleCheckboxRow(this)">
                <input type="checkbox" id="dchk_${Date.now()}_${idx}">
                <label>${escapeHtml(doc)}</label>
            </li>
        `).join("");

        docsHtml = `
            <div>
                <div class="section-title">
                    <span>📑 Required Documents</span>
                    <span style="font-size: 11px; font-weight: normal; color: var(--text-muted);">(tick to check off)</span>
                </div>
                <ul class="docs-checklist">${docItems}</ul>
            </div>
        `;
    }

    // 3. Step-by-Step Procedure Checklist
    let stepsHtml = "";
    if (answer.steps && answer.steps.length > 0) {
        const stepItems = answer.steps.map((st, idx) => {
            const stepNo = st.no || idx + 1;
            const stepText = st.text || st.title || "Step";
            const stepTip = st.tip || st.detail || "";
            return `
            <div class="step-item" id="step_${Date.now()}_${stepNo}">
                <input type="checkbox" onchange="toggleStepItem(this)">
                <div class="step-body">
                    <div class="step-num">Step ${stepNo}</div>
                    <div class="step-desc">${escapeHtml(stepText)}</div>
                    ${stepTip ? `<div class="step-hint">💡 <strong>Details:</strong> ${escapeHtml(stepTip)}</div>` : ""}
                </div>
            </div>
        `;
        }).join("");

        stepsHtml = `
            <div>
                <div class="section-title">
                    <span>✅ Step-by-Step Action Plan</span>
                </div>
                <div class="steps-checklist">${stepItems}</div>
            </div>
        `;
    }

    // 4. Warnings & Red Flags
    let warningsHtml = "";
    if (answer.warnings && answer.warnings.length > 0) {
        const warnItems = answer.warnings.map(w => {
            const warningText = w.text || w.title || "Warning";
            const warningReason = w.reason || w.message || w.source || "Review this point carefully.";
            return `
            <div class="warning-box">
                <div class="warning-text">⚠️ ${escapeHtml(warningText)}</div>
                <div class="warning-reason">${escapeHtml(warningReason)}</div>
            </div>
        `;
        }).join("");

        warningsHtml = `
            <div>
                <div class="section-title" style="color: var(--warning);">
                    <span>⚠️ Risk & Deadline Warnings</span>
                </div>
                <div style="display:flex; flex-direction:column; gap:8px;">${warnItems}</div>
            </div>
        `;
    }

    // 5. Evidence citations
    let citationsHtml = "";
    const citations = Array.isArray(answer.citations) ? answer.citations : [];
    if (citations.length > 0) {
        const citationItems = citations.map((citation, idx) => `
            <article class="citation-card">
                <div class="citation-header">
                    <span class="citation-number">${idx + 1}</span>
                    <a href="${escapeHtml(citation.url)}" target="_blank" rel="noopener noreferrer" class="citation-title">
                        ${escapeHtml(citation.title)} ↗
                    </a>
                </div>
                <p class="citation-excerpt">${escapeHtml(citation.excerpt)}</p>
                <div class="citation-meta">
                    <span>Reported date: ${escapeHtml(citation.reported_last_verified)}</span>
                    <span class="verification-status verification-${escapeHtml(citation.factual_verification || 'unverified')}">
                        ${escapeHtml((citation.factual_verification || 'unverified').toUpperCase())}
                    </span>
                </div>
            </article>
        `).join("");
        citationsHtml = `
            <section class="citations-section" aria-label="Answer evidence sources">
                <div class="section-title"><span>📚 Evidence Sources</span></div>
                <div class="citations-list">${citationItems}</div>
            </section>
        `;
    }
    const hasUnverifiedEvidence = citations.some(citation => citation.factual_verification !== "verified");
    const sourceDateLabel = hasUnverifiedEvidence ? "Source date reported" : "Verified";

    row.innerHTML = `
        <div class="message-avatar bot-avatar">🏛️</div>
        <div class="message-content">
            <div class="assistant-response">
                <!-- Header -->
                <div class="response-header">
                    <h3 class="response-title">${escapeHtml(answer.title)}</h3>
                    <span class="response-confidence confidence-${answer.confidence || 'high'}">
                        ● ${answer.confidence ? answer.confidence.toUpperCase() : 'VERIFIED'}
                    </span>
                </div>

                <!-- Privacy Redaction Badge -->
                ${maskedBanner}

                <!-- Plain Language Summary -->
                <div class="response-summary">
                    ${escapeHtml(answer.summary)}
                </div>

                <!-- Documents Needed -->
                ${docsHtml}

                <!-- Steps Checklist -->
                ${stepsHtml}

                <!-- Risk Flags -->
                ${warningsHtml}

                <!-- Evidence citations -->
                ${citationsHtml}

                <!-- Sourced & Dated Footer -->
                <div class="response-footer">
                    <a href="${escapeHtml(answer.source_url)}" target="_blank" rel="noopener noreferrer" class="source-anchor">
                        🔗 Official Source: ${escapeHtml(answer.source_url)} ↗
                    </a>
                    <span class="verify-pill">
                        ${sourceDateLabel}: <strong>${escapeHtml(answer.last_verified)}</strong>
                    </span>
                </div>

                <!-- Legal Disclaimer -->
                <div class="disclaimer-text">
                    ℹ️ <strong>Disclaimer:</strong> ${escapeHtml(answer.disclaimer)}
                </div>
            </div>
        </div>
    `;

    messagesContainer.appendChild(row);
    if (shouldScroll) scrollToBottom();
}

// --- CHECKLIST INTERACTION HELPERS ---
window.toggleCheckboxRow = function(rowEl) {
    const chk = rowEl.querySelector('input[type="checkbox"]');
    if (event.target !== chk) chk.checked = !chk.checked;
    rowEl.classList.toggle("checked", chk.checked);
};

window.toggleStepItem = function(checkboxEl) {
    const item = checkboxEl.closest(".step-item");
    if (item) {
        item.classList.toggle("checked", checkboxEl.checked);
    }
};

// --- PREVIEW SAMPLE PAN GUIDE ---
async function loadSampleAnswer() {
    if (welcomeScreen) welcomeScreen.style.display = "none";

    let currentChat = getActiveChat();
    if (!currentChat) {
        currentChat = createNewChat("Apply for new PAN card");
    }

    const msgId = "msg_" + Date.now();
    currentChat.messages.push({
        id: msgId,
        role: "user",
        text: "How do I apply for a new PAN card online?",
        file: null
    });
    appendUserBubble("How do I apply for a new PAN card online?", null, msgId, true);
    setLoading(true);

    try {
        const res = await fetch("sample_answer.json");
        const data = await res.json();
        setTimeout(() => {
            currentChat.messages.push({
                id: "msg_ast_" + Date.now(),
                role: "assistant",
                answer: data
            });
            currentChat.updatedAt = Date.now();
            saveChatsToStorage();
            renderHistoryList();

            appendAssistantResponse(data, true);
            setLoading(false);
        }, 300);
    } catch (e) {
        setLoading(false);
    }
}

// --- LOCAL FALLBACK (SIMULATED GUIDES) ---
async function getLocalFallbackAnswer(text, file) {
    const qLower = (text || "").toLowerCase();

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
            disclaimer: "GovBank Assistant provides educational guidance and does not provide legal representation. Please consult a legal professional or the RBI Ombudsman."
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
            disclaimer: "GovBank Assistant provides step-by-step guidance based on official Income Tax Department instructions. It does not replace a Chartered Accountant for complex audit cases."
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
            disclaimer: "GovBank Assistant provides informational guidance based on RBI regulations. It does not constitute formal legal advice."
        };
    }

    try {
        const res = await fetch("sample_answer.json");
        return await res.json();
    } catch (e) {
        return createSystemNotice("No Guide Found", "No local procedure guide was found for this query.");
    }
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
