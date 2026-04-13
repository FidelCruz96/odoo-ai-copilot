/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller"
import { onMounted } from "@odoo/owl"
import { patch } from "@web/core/utils/patch"

const STORAGE_KEY_PREFIX = "odoo_ai_chat_history"
const SESSION_KEY_STORAGE = "odoo_ai_chat_session_key"
let aiChatContext = {}

function generateSessionKey() {
    return `chat_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

function getSessionKey() {
    try {
        let sessionKey = localStorage.getItem(SESSION_KEY_STORAGE)
        if (!sessionKey) {
            sessionKey = generateSessionKey()
            localStorage.setItem(SESSION_KEY_STORAGE, sessionKey)
        }
        return sessionKey
    } catch (err) {
        return "chat_fallback_session"
    }
}

function resetSessionKey() {
    const sessionKey = generateSessionKey()
    try {
        localStorage.setItem(SESSION_KEY_STORAGE, sessionKey)
    } catch (err) {
        // ignore storage errors
    }
    return sessionKey
}

function getHistoryStorageKey() {
    return `${STORAGE_KEY_PREFIX}:${getSessionKey()}`
}

function nowTime() {
    const d = new Date()
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

function loadHistory() {
    try {
        const raw = localStorage.getItem(getHistoryStorageKey())
        return raw ? JSON.parse(raw) : []
    } catch (err) {
        return []
    }
}

function getShortHistory(limit = 8) {
    const history = loadHistory()
    if (!Array.isArray(history) || history.length === 0) {
        return []
    }
    const slice = history.slice(Math.max(0, history.length - limit))
    return slice.map((h) => ({
        role: h.role === "user" ? "user" : "bot",
        text: h.text || "",
        time: h.time || null,
        source: "client",
    }))
}

function saveHistory(history) {
    try {
        localStorage.setItem(getHistoryStorageKey(), JSON.stringify(history))
    } catch (err) {
        // ignore storage errors
    }
}

function escapeHtml(text) {
    return String(text || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;")
}

function formatInlineMarkdown(text) {
    return text
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/\*(.+?)\*/g, "<em>$1</em>")
}

function renderMessageHtml(text) {
    const normalized = escapeHtml(text).replace(/\r\n/g, "\n").trim()
    if (!normalized) {
        return ""
    }

    const lines = normalized.split("\n")
    const html = []
    let listType = null

    const closeList = () => {
        if (listType) {
            html.push(`</${listType}>`)
            listType = null
        }
    }

    for (const rawLine of lines) {
        const line = rawLine.trim()
        if (!line) {
            closeList()
            continue
        }

        const orderedMatch = line.match(/^(\d+)\.\s+(.+)$/)
        if (orderedMatch) {
            if (listType !== "ol") {
                closeList()
                html.push(`<ol start="${orderedMatch[1]}">`)
                listType = "ol"
            }
            html.push(`<li>${formatInlineMarkdown(orderedMatch[2])}</li>`)
            continue
        }

        const unorderedMatch = line.match(/^[-*]\s+(.+)$/)
        if (unorderedMatch) {
            if (listType !== "ul") {
                closeList()
                html.push("<ul>")
                listType = "ul"
            }
            html.push(`<li>${formatInlineMarkdown(unorderedMatch[1])}</li>`)
            continue
        }

        closeList()
        html.push(`<p>${formatInlineMarkdown(line)}</p>`)
    }

    closeList()
    return html.join("")
}

function appendMessage(role, text, time, persist = true) {
    const container = document.getElementById("ai_chat_messages")
    if (!container) {
        return
    }

    const bubble = document.createElement("div")
    bubble.className = `o_ai_msg o_ai_msg_${role}`
    const content = document.createElement("div")
    content.className = "o_ai_msg_content"
    content.innerHTML = renderMessageHtml(text)
    bubble.appendChild(content)

    const meta = document.createElement("div")
    meta.className = "o_ai_msg_meta"
    meta.innerText = time || nowTime()
    bubble.appendChild(meta)

    container.appendChild(bubble)
    container.scrollTop = container.scrollHeight

    if (persist) {
        const history = loadHistory()
        history.push({ role, text, time: meta.innerText })
        saveHistory(history)
    }
}

function ensureGreeting() {
    const container = document.getElementById("ai_chat_messages")
    if (!container) {
        return
    }

    if (container.childElementCount === 0) {
        appendMessage("bot", "Hola, soy tu asistente. ¿En qué puedo ayudarte?", nowTime(), true)
    }
}

function renderHistory() {
    const container = document.getElementById("ai_chat_messages")
    if (!container) {
        return
    }
    if (container.dataset.aiHistoryLoaded === "1") {
        return
    }
    const history = loadHistory()
    if (!history.length) {
        container.dataset.aiHistoryLoaded = "1"
        return
    }
    history.forEach((msg) => appendMessage(msg.role, msg.text, msg.time, false))
    container.dataset.aiHistoryLoaded = "1"
}

function setLoading(isLoading) {
    const status = document.getElementById("ai_chat_status")
    const sendBtn = document.getElementById("ai_chat_send_btn")
    const input = document.getElementById("ai_chat_message")
    const container = document.getElementById("ai_chat_messages")
    if (status) {
        status.innerText = isLoading ? "Escribiendo..." : ""
    }
    if (sendBtn) {
        sendBtn.classList.toggle("disabled", isLoading)
        sendBtn.setAttribute("aria-disabled", isLoading ? "true" : "false")
    }
    if (input) {
        input.disabled = isLoading
    }

    if (container) {
        let typing = container.querySelector(".o_ai_msg_typing")
        if (isLoading && !typing) {
            typing = document.createElement("div")
            typing.className = "o_ai_msg o_ai_msg_bot o_ai_msg_typing"
            typing.setAttribute("aria-live", "polite")
            typing.innerHTML = "<span class=\"o_ai_typing_dot\"></span><span class=\"o_ai_typing_dot\"></span><span class=\"o_ai_typing_dot\"></span>"
            container.appendChild(typing)
            container.scrollTop = container.scrollHeight
        }
        if (!isLoading && typing) {
            typing.remove()
        }
    }
}

async function sendMessage() {
    const input = document.getElementById("ai_chat_message")
    if (!input) {
        return
    }
    if (input.disabled) {
        return
    }

    const message = input.value.trim()
    if (!message) {
        return
    }

    appendMessage("user", message)
    input.value = ""
    input.focus()
    setLoading(true)

    try {
        const httpResponse = await fetch("/ai_assistant/ask_http", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: message,
                context: {
                    ...(aiChatContext || {}),
                    chat_session_key: getSessionKey(),
                },
                history: getShortHistory(8),
            })
        })

        if (!httpResponse.ok) {
            appendMessage("bot", `Error del servidor: ${httpResponse.status}`)
            return
        }

        let rpcResponse = null
        try {
            rpcResponse = await httpResponse.json()
        } catch (err) {
            appendMessage("bot", "Error: respuesta no es JSON.")
            return
        }

        const answer = rpcResponse && rpcResponse.answer ? rpcResponse.answer : null
        appendMessage("bot", answer || "Sin respuesta.")
    } catch (err) {
        appendMessage("bot", "No pude conectar con el servidor.")
    } finally {
        setLoading(false)
    }
}

function initChatUI() {
    renderHistory()
    ensureGreeting()

    const sendBtn = document.getElementById("ai_chat_send_btn")
    const clearBtn = document.getElementById("ai_chat_clear_btn")
    const input = document.getElementById("ai_chat_message")

    if (sendBtn && !sendBtn.dataset.aiBound) {
        sendBtn.dataset.aiBound = "1"
        sendBtn.addEventListener("click", (ev) => {
            ev.preventDefault()
            sendMessage()
        })
    }

    if (clearBtn && !clearBtn.dataset.aiBound) {
        clearBtn.dataset.aiBound = "1"
        clearBtn.addEventListener("click", (ev) => {
            ev.preventDefault()
            const container = document.getElementById("ai_chat_messages")
            if (container) {
                container.innerHTML = ""
            }
            resetSessionKey()
            saveHistory([])
            ensureGreeting()
        })
    }

    if (input && !input.dataset.aiBound) {
        input.dataset.aiBound = "1"
        input.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" && !ev.ctrlKey) {
                ev.preventDefault()
                sendMessage()
            }
        })
    }
}

const _originalSetup = FormController.prototype.setup

patch(FormController.prototype, {
    setup() {
        if (_originalSetup) {
            _originalSetup.call(this)
        }
        onMounted(() => {
            const resModel = this.model && this.model.root && this.model.root.resModel
            if (resModel === "ai.chat.ui") {
                const root = this.model && this.model.root ? this.model.root : {}
                const rootCtx = root.context || {}
                aiChatContext = {
                    view_model: root.resModel || null,
                    record_id: root.resId || null,
                    domain: root.domain || [],
                    active_model: rootCtx.active_model || null,
                    active_id: rootCtx.active_id || null,
                    active_ids: rootCtx.active_ids || null,
                }
                initChatUI()
            }
        })
    },
})

window.sendMessage = sendMessage
