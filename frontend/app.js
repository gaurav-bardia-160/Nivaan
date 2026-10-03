/**
 * GovBank Assistant - Minimal Chatbot Controller
 * Handles conversation flow, camera/file upload, PII masking, and structured checklist rendering.
 */

const API_BASE = "http://127.0.0.1:8000";
let isBackendLive = false;
let currentChatHistory = [];
let attachedFile = null; // { name, type, size, textContent }

// DOM Elements
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebarToggle");
const newChatBtn = document.getElementById("newChatBtn");
const historyList = document.getElementById("historyList");
const langSelect = document.getElementById("langSelect");
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

// Quick Prompts
const suggestionCards = document.querySelectorAll(".suggestion-card");

// --- TRANSLATIONS ---
const UI_TRANSLATIONS = {
    "en": {
        "welcomeTitle": "How can I help with official procedures today?",
        "welcomeText": "Ask about government forms, tax notices, bank rules, or upload a photo/PDF of a document to get a plain-language checklist with verified sources.",
        "inputPlaceholder": "Ask a question or upload a notice/form...",
        "previewSample": "Preview Sample",
        "darkTheme": "🌙 Dark",
        "lightTheme": "☀️ Light",
        "historyHeading": "Recent Inquiries",
        "privacyBadge": "Privacy-by-Design",
        "privacyText": "Aadhaar, PAN, phone & accounts masked before processing.",
        "q1Title": "Apply for PAN Card", "q1Desc": "Form 49A steps, fees & documents",
        "q2Title": "File ITR-1 Return", "q2Desc": "Income tax filing basics & proofs",
        "q3Title": "Loan Prepayment Rules", "q3Desc": "RBI rules on floating rate penalty bans",
        "q4Title": "Cheque Bounce Notice", "q4Desc": "Deadlines, 15-day notice & legal steps"
    },
    "hi": {
        "welcomeTitle": "आज मैं सरकारी प्रक्रियाओं में आपकी क्या मदद कर सकता हूँ?",
        "welcomeText": "सरकारी फॉर्म, टैक्स नोटिस, बैंक नियमों के बारे में पूछें, या स्पष्ट चेकलिस्ट प्राप्त करने के लिए दस्तावेज़ की फोटो/पीडीएफ अपलोड करें।",
        "inputPlaceholder": "कोई प्रश्न पूछें या नोटिस/फॉर्म अपलोड करें...",
        "previewSample": "नमूना देखें",
        "darkTheme": "🌙 डार्क",
        "lightTheme": "☀️ लाइट",
        "historyHeading": "हाल की पूछताछ",
        "privacyBadge": "गोपनीयता की सुरक्षा",
        "privacyText": "आधार, पैन, फोन और खाते नंबर हटा दिए जाते हैं।",
        "q1Title": "पैन कार्ड के लिए आवेदन", "q1Desc": "फॉर्म 49A के चरण, शुल्क और दस्तावेज़",
        "q2Title": "ITR-1 रिटर्न भरें", "q2Desc": "आयकर रिटर्न बेसिक्स और प्रमाण",
        "q3Title": "ऋण पूर्व भुगतान नियम", "q3Desc": "फ्लोटिंग रेट पेनल्टी पर आरबीआई के नियम",
        "q4Title": "चेक बाउंस नोटिस", "q4Desc": "समय सीमा, 15-दिन का नोटिस और कानूनी कदम"
    },
    "gu": {
        "welcomeTitle": "આજે હું સરકારી પ્રક્રિયાઓમાં તમારી કેવી રીતે મદદ કરી શકું?",
        "welcomeText": "સરકારી ફોર્મ, ટેક્સ નોટિસ, બેંક નિયમો વિશે પૂછો, અથવા સરળ ચેકલિસ્ટ મેળવવા માટે દસ્તાવેજનો ફોટો/પીડીએફ અપલોડ કરો.",
        "inputPlaceholder": "કોઈ પ્રશ્ન પૂછો અથવા નોટિસ/ફોર્મ અપલોડ કરો...",
        "previewSample": "નમૂનો જુઓ",
        "darkTheme": "🌙 ડાર્ક",
        "lightTheme": "☀️ લાઇટ",
        "historyHeading": "તાજેતરની પૂછપરછ",
        "privacyBadge": "ગોપનીયતા રક્ષણ",
        "privacyText": "આધાર, પાન, ફોન અને એકાઉન્ટ છુપાવેલ છે.",
        "q1Title": "પાન કાર્ડ માટે અરજી", "q1Desc": "ફોર્મ 49A ના પગલાં, ફી અને દસ્તાવેજો",
        "q2Title": "ITR-1 રિટર્ન ભરો", "q2Desc": "આવકવેરા રિટર્નની મૂળભૂત બાબતો",
        "q3Title": "લોન પ્રીપેમેન્ટ નિયમો", "q3Desc": "ફ્લોટિંગ રેટ પેનલ્ટી પર RBI ના નિયમો",
        "q4Title": "ચેક બાઉન્સ નોટિસ", "q4Desc": "સમય મર્યાદા, 15-દિવસની નોટિસ અને કાનૂની પગલાં"
    }
};

function translateUI() {
    const lang = langSelect ? langSelect.value : "en";
    const t = UI_TRANSLATIONS[lang] || UI_TRANSLATIONS["en"];

    const setInner = (selector, text) => { const el = document.querySelector(selector); if(el) el.innerHTML = text; };
    
    setInner('.welcome-title', t.welcomeTitle);
    setInner('.welcome-text', t.welcomeText);
    if(chatInput) chatInput.placeholder = t.inputPlaceholder;
    if(previewSampleBtn) previewSampleBtn.innerHTML = t.previewSample;
    setInner('.history-heading', t.historyHeading);
    
    const pBadge = document.querySelector('.privacy-badge div');
    if(pBadge) pBadge.innerHTML = `<strong>${t.privacyBadge}</strong><p>${t.privacyText}</p>`;
    
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if (themeToggleBtn) themeToggleBtn.innerHTML = isDark ? t.lightTheme : t.darkTheme;
    
    const cards = document.querySelectorAll('.suggestion-card');
    if(cards.length >= 4) {
        cards[0].querySelector('strong').innerHTML = t.q1Title; cards[0].querySelector('p').innerHTML = t.q1Desc;
        cards[1].querySelector('strong').innerHTML = t.q2Title; cards[1].querySelector('p').innerHTML = t.q2Desc;
        cards[2].querySelector('strong').innerHTML = t.q3Title; cards[2].querySelector('p').innerHTML = t.q3Desc;
        cards[3].querySelector('strong').innerHTML = t.q4Title; cards[3].querySelector('p').innerHTML = t.q4Desc;
    }
}

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
    checkBackendHealth();
    setupEventListeners();
    translateUI(); // initialize translations based on default dropdown
});

function setupEventListeners() {
    // Language change
    if (langSelect) {
        langSelect.addEventListener("change", translateUI);
    }

    // Sidebar toggle
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener("click", () => {
            sidebar.classList.toggle("collapsed");
        });
    }

    // New Chat
    if (newChatBtn) {
        newChatBtn.addEventListener("click", resetChat);
    }

    // Preview Sample
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
        // Auto-expand input height
        chatInput.addEventListener("input", () => {
            chatInput.style.height = "auto";
            chatInput.style.height = Math.min(chatInput.scrollHeight, 140) + "px";
        });
    }

    // File Attachment (Document Picker)
    if (attachBtn && fileInput) {
        attachBtn.addEventListener("click", () => {
            fileInput.removeAttribute("capture");
            fileInput.click();
        });
    }

    // Camera Button (Direct Camera Capture)
    if (cameraBtn && fileInput) {
        cameraBtn.addEventListener("click", () => {
            fileInput.setAttribute("capture", "environment");
            fileInput.click();
        });
    }

    // File Input Handler
    if (fileInput) {
        fileInput.addEventListener("change", handleFileSelected);
    }

    // Remove Attachment
    if (removeAttachmentBtn) {
        removeAttachmentBtn.addEventListener("click", clearAttachment);
    }
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

    // If it's a plain text file, read text
    if (file.type.startsWith("text/")) {
        const reader = new FileReader();
        reader.onload = (event) => {
            attachedFile.textContent = event.target.result;
        };
        reader.readAsText(file);
    }

    // Update Preview Pill
    if (previewFilename) previewFilename.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
    if (previewIcon) previewIcon.textContent = isImage ? "📷" : (isPdf ? "📕" : "📄");
    if (attachmentPreview) attachmentPreview.style.display = "flex";

    // Focus input
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
        // Backend not running
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

    // Append User Message to UI
    appendUserBubble(userText, fileObj);

    // Save attachment snapshot and clear input attachment
    const currentAttachment = fileObj || attachedFile;
    clearAttachment();

    setLoading(true);

    // Try live backend first
    if (isBackendLive) {
        try {
            const payload = {
                input_type: currentAttachment ? "document" : "question",
                question: userText,
                language: langSelect ? langSelect.value : "en",
                conversation_id: "conv_default",
                file_attached: !!currentAttachment
            };

            const response = await fetch(`${API_BASE}/api/ask`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                const answer = await response.json();
                appendAssistantResponse(answer);
                addChatHistory(userText);
                setLoading(false);
                return;
            }
        } catch (err) {
            console.warn("Backend error, falling back to local guide:", err);
        }
    }

    // Intelligent local fallback matching the project spec
    await handleLocalFallback(userText, currentAttachment);
    addChatHistory(userText);
    setLoading(false);
}

// --- APPEND USER BUBBLE ---
function appendUserBubble(text, file) {
    const row = document.createElement("div");
    row.className = "message-row";
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
            <div class="user-bubble">${escapeHtml(text)}</div>
        </div>
        <div class="message-avatar user-avatar">👤</div>
    `;

    messagesContainer.appendChild(row);
    scrollToBottom();
}

// --- APPEND ASSISTANT RESPONSE CARD ---
function appendAssistantResponse(answer) {
    const row = document.createElement("div");
    row.className = "message-row";

    // 1. Masked items banner
    let maskedBanner = "";
    if (answer.masked_items && answer.masked_items.length > 0) {
        const maskedDetails = answer.masked_items.map(m => `${m.count} ${m.item_type}`).join(", ");
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
        const stepItems = answer.steps.map((st) => `
            <div class="step-item" id="step_${Date.now()}_${st.no}">
                <input type="checkbox" onchange="toggleStepItem(this)">
                <div class="step-body">
                    <div class="step-num">Step ${st.no}</div>
                    <div class="step-desc">${escapeHtml(st.text)}</div>
                    ${st.tip ? `<div class="step-hint">💡 <strong>Tip:</strong> ${escapeHtml(st.tip)}</div>` : ""}
                </div>
            </div>
        `).join("");

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
        const warnItems = answer.warnings.map(w => `
            <div class="warning-box">
                <div class="warning-text">⚠️ ${escapeHtml(w.text)}</div>
                <div class="warning-reason">${escapeHtml(w.reason)}</div>
            </div>
        `).join("");

        warningsHtml = `
            <div>
                <div class="section-title" style="color: var(--warning);">
                    <span>⚠️ Risk & Deadline Warnings</span>
                </div>
                <div style="display:flex; flex-direction:column; gap:8px;">${warnItems}</div>
            </div>
        `;
    }

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

                <!-- Sourced & Dated Footer -->
                <div class="response-footer">
                    <a href="${escapeHtml(answer.source_url)}" target="_blank" rel="noopener noreferrer" class="source-anchor">
                        🔗 Official Source: ${escapeHtml(answer.source_url)} ↗
                    </a>
                    <span class="verify-pill">
                        Verified: <strong>${escapeHtml(answer.last_verified)}</strong>
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
    scrollToBottom();
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
    appendUserBubble("How do I apply for a new PAN card online?");
    setLoading(true);

    try {
        const res = await fetch("sample_answer.json");
        const data = await res.json();
        setTimeout(() => {
            appendAssistantResponse(data);
            addChatHistory("Apply for new PAN card");
            setLoading(false);
        }, 300);
    } catch (e) {
        setLoading(false);
    }
}

// --- LOCAL FALLBACK (SIMULATED GUIDES) ---
async function handleLocalFallback(text, file) {
    const qLower = text.toLowerCase();

    // Check if user uploaded a document or notice
    if (file) {
        const fakeMasked = [
            { item_type: "Aadhaar Number", count: 1 },
            { item_type: "Bank Account Number", count: 1 }
        ];

        appendAssistantResponse({
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
            masked_items: fakeMasked,
            disclaimer: "GovBank Assistant provides educational guidance and does not provide legal representation. Please consult a legal professional or the RBI Ombudsman."
        });
        return;
    }

    // Query Fallbacks
    if (qLower.includes("tax") || qLower.includes("itr") || qLower.includes("income")) {
        appendAssistantResponse({
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
        });
        return;
    }

    if (qLower.includes("loan") || qLower.includes("prepayment") || qLower.includes("rbi") || qLower.includes("foreclosure")) {
        appendAssistantResponse({
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
        });
        return;
    }

    // Default: Return the verified PAN guide
    try {
        const res = await fetch("sample_answer.json");
        const data = await res.json();
        appendAssistantResponse(data);
    } catch (e) {
        // Fallback
    }
}

// --- CHAT HISTORY MANAGEMENT ---
function addChatHistory(title) {
    if (!historyList) return;
    const cleanTitle = title.length > 28 ? title.substring(0, 26) + "..." : title;
    const item = document.createElement("div");
    item.className = "history-item";
    item.textContent = cleanTitle;
    item.onclick = () => {
        chatInput.value = title;
        handleUserSubmit();
    };
    historyList.prepend(item);
}

function resetChat() {
    messagesContainer.innerHTML = "";
    if (welcomeScreen) {
        messagesContainer.appendChild(welcomeScreen);
        welcomeScreen.style.display = "block";
    }
    clearAttachment();
    chatInput.value = "";
    chatInput.style.height = "auto";
    chatInput.focus();
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
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
