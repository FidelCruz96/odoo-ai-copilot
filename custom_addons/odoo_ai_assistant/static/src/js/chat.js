/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller"
import { onMounted } from "@odoo/owl"
import { patch } from "@web/core/utils/patch"

const STORAGE_KEY = "odoo_ai_chat_history"
let aiChatContext = {}

function nowTime() {
    const d = new Date()
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

function loadHistory() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY)
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
        localStorage.setItem(STORAGE_KEY, JSON.stringify(history))
    } catch (err) {
        // ignore storage errors
    }
}

function appendMessage(role, text, time, persist = true) {
    const container = document.getElementById("ai_chat_messages")
    if (!container) {
        return
    }

    const bubble = document.createElement("div")
    bubble.className = `o_ai_msg o_ai_msg_${role}`
    const content = document.createElement("div")
    content.innerText = text
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
                context: aiChatContext || {},
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
