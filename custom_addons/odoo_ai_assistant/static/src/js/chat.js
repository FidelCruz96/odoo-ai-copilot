/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller"
import { onMounted } from "@odoo/owl"
import { patch } from "@web/core/utils/patch"

const STORAGE_KEY_PREFIX = "odoo_ai_chat_history"
const SESSION_KEY_STORAGE = "odoo_ai_chat_session_key"
const CONTEXT_SIGNATURE_STORAGE = "odoo_ai_chat_context_signature"
const NAV_RESOLVE_CACHE = {}
const MODEL_CONTEXT_SUGGESTIONS = {
    "purchase.order": [
        { label: "Ver pickings", prompt: "muéstrame los pickings asociados" },
        { label: "Recepciones pendientes", prompt: "muéstrame las recepciones pendientes" },
        { label: "Recepciones canceladas", prompt: "muéstrame las recepciones canceladas" },
        { label: "Facturas del proveedor", prompt: "muéstrame las facturas relacionadas" },
        { label: "Productos pendientes", prompt: "muéstrame sus productos" },
    ],
    "sale.order": [
        { label: "Facturas relacionadas", prompt: "muéstrame las facturas relacionadas" },
        { label: "Pagos pendientes", prompt: "muéstrame los pagos pendientes" },
        { label: "Productos vendidos", prompt: "muéstrame sus productos" },
        { label: "Margen estimado", prompt: "cuál es el margen estimado de esta venta" },
    ],
    "account.move": [
        { label: "Abrir facturas", prompt: "muéstrame facturas relacionadas" },
        { label: "Ver vencidas", prompt: "muéstrame las facturas vencidas" },
        { label: "Filtrar por cliente", prompt: "filtra por cliente" },
    ],
    "stock.picking": [
        { label: "Ver movimientos", prompt: "muéstrame los movimientos de este picking" },
        { label: "Pendientes", prompt: "qué pickings están pendientes" },
        { label: "Cancelados", prompt: "qué pickings están cancelados" },
    ],
}
const MODEL_PLACEHOLDERS = {
    "purchase.order": "Pregúntame sobre esta compra, sus pickings o facturas relacionadas...",
    "sale.order": "Pregúntame sobre esta venta, productos o facturas...",
    "account.move": "Pregúntame sobre esta factura, vencimientos o pagos...",
    "stock.picking": "Pregúntame sobre este picking y sus movimientos...",
}
const ANSWER_TYPE_LABELS = {
    table: "Consulta ERP",
    summary: "Resumen",
    clarification: "Aclaración",
    error: "Error funcional",
    confirmation: "Confirmación",
}
const ANSWER_MODE_BADGES = {
    deterministic: "Determinístico",
    tool_guided: "Consulta ERP",
    clarification_required: "Aclaración",
    fallback_explanatory: "Resumen",
}
const DEFAULT_SUGGESTIONS = [
    { label: "Ventas del mes", prompt: "ventas del mes" },
    { label: "Facturas pendientes", prompt: "facturas pendientes este mes" },
    { label: "Top clientes", prompt: "top clientes por facturación" },
    { label: "Stock negativo", prompt: "qué productos tienen stock negativo" },
]
let aiChatContext = {}
let lastUserMessage = ""

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

function getActiveModel() {
    return (aiChatContext && aiChatContext.active_model) || null
}

function getContextSignature(context = aiChatContext) {
    if (!context || typeof context !== "object") {
        return "global"
    }
    const activeModel = context.active_model || "global"
    const activeId = context.active_id || "none"
    return `${activeModel}:${activeId}`
}

function syncSessionWithContext() {
    const signature = getContextSignature(aiChatContext)
    try {
        const previous = localStorage.getItem(CONTEXT_SIGNATURE_STORAGE)
        if (previous && previous !== signature) {
            resetSessionKey()
        }
        localStorage.setItem(CONTEXT_SIGNATURE_STORAGE, signature)
    } catch (err) {
        // ignore storage errors
    }
}

function humanizeModelName(modelName) {
    const map = {
        "purchase.order": "Compra",
        "sale.order": "Venta",
        "account.move": "Factura",
        "stock.picking": "Picking",
    }
    return map[modelName] || modelName
}

function humanizeContextText(rawText) {
    let text = String(rawText || "").trim()
    if (!text) {
        return "Sin contexto activo"
    }
    text = text.replace(/^Contexto activo:\s*/i, "")
    text = text.replace(/\bpurchase\.order\b/gi, "Compra")
    text = text.replace(/\bsale\.order\b/gi, "Venta")
    text = text.replace(/\baccount\.move\b/gi, "Factura")
    text = text.replace(/\bstock\.picking\b/gi, "Picking")
    return text
}

function formatLatency(ms) {
    if (typeof ms !== "number" || ms < 0) {
        return ""
    }
    if (ms >= 1000) {
        const seconds = (ms / 1000).toFixed(1)
        return `Procesado en ~${seconds} s`
    }
    return `Procesado en ~${Math.round(ms)} ms`
}

function updateHeaderFromUi(ui) {
    const status = document.getElementById("ai_chat_status")
    const latency = document.getElementById("ai_chat_latency")
    if (status) {
        status.innerText = "● En línea"
    }
    if (latency) {
        const ms = ui && typeof ui.latency_ms === "number" ? ui.latency_ms : null
        latency.innerText = ms !== null ? formatLatency(ms) : ""
    }
}

function updateContextFromUi(ui) {
    const contextNode = document.getElementById("ai_chat_context")
    if (!contextNode) {
        return
    }
    const active = ui && ui.context && ui.context.active ? ui.context.active : "Sin contexto activo"
    contextNode.innerText = humanizeContextText(active)
}

function contextSuggestionsForModel(modelName) {
    return MODEL_CONTEXT_SUGGESTIONS[modelName] || DEFAULT_SUGGESTIONS
}

function normalizeSuggestions(items, modelName = null) {
    const fallback = contextSuggestionsForModel(modelName || getActiveModel())
    if (!Array.isArray(items) || !items.length) {
        return fallback
    }
    return items
        .map((item) => {
            if (typeof item === "string") {
                return { label: item, prompt: item }
            }
            if (item && typeof item === "object" && item.label) {
                return { label: item.label, prompt: item.prompt || item.label }
            }
            return null
        })
        .filter(Boolean)
        .slice(0, 6)
}

function renderSuggestions(items, modelName = null) {
    const container = document.getElementById("ai_chat_suggestions")
    if (!container) {
        return
    }
    const suggestions = normalizeSuggestions(items, modelName)
    container.innerHTML = ""
    suggestions.forEach((item) => {
        const btn = document.createElement("button")
        btn.type = "button"
        btn.className = "o_ai_chip"
        btn.innerText = item.label
        btn.addEventListener("click", () => sendMessage(item.prompt))
        container.appendChild(btn)
    })
}

function setInputPlaceholder() {
    const input = document.getElementById("ai_chat_message")
    if (!input) {
        return
    }
    const modelName = getActiveModel()
    input.placeholder = MODEL_PLACEHOLDERS[modelName] || "Haz una consulta sobre ventas, facturas o clientes..."
}

async function loadContextSummary() {
    const activeModel = getActiveModel()
    const activeId = aiChatContext && aiChatContext.active_id
    if (!activeModel || !activeId) {
        updateContextFromUi(null)
        renderSuggestions(null, activeModel)
        return
    }

    try {
        const response = await fetch("/ai_assistant/context_summary", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                context: aiChatContext || {},
            }),
        })
        if (!response.ok) {
            throw new Error(`status_${response.status}`)
        }
        const payload = await response.json()
        if (payload && payload.summary_text) {
            const contextNode = document.getElementById("ai_chat_context")
            if (contextNode) {
                contextNode.innerText = humanizeContextText(payload.summary_text)
            }
        } else {
            updateContextFromUi({ context: { active: `${humanizeModelName(activeModel)} #${activeId}` } })
        }
        renderSuggestions(payload && payload.suggestions ? payload.suggestions : null, activeModel)
    } catch (err) {
        updateContextFromUi({ context: { active: `${humanizeModelName(activeModel)} #${activeId}` } })
        renderSuggestions(null, activeModel)
    }
}

function exportHistoryAsCsv() {
    const rows = loadHistory()
    if (!Array.isArray(rows) || !rows.length) {
        return
    }
    const csvLines = ["role,time,text"]
    rows.forEach((row) => {
        const role = String(row.role || "").replaceAll('"', '""')
        const time = String(row.time || "").replaceAll('"', '""')
        const text = String(row.text || "").replaceAll('"', '""').replace(/\r?\n/g, " ")
        csvLines.push(`"${role}","${time}","${text}"`)
    })
    const blob = new Blob([csvLines.join("\n")], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `ai_chat_${getSessionKey()}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
}

async function resolveNavigationHint(action) {
    if (!action || typeof action !== "object" || !action.model) {
        return null
    }
    const actionType = action.type || "open_model_list"
    const cacheKey = `${action.model}:${actionType}`
    if (NAV_RESOLVE_CACHE[cacheKey]) {
        return NAV_RESOLVE_CACHE[cacheKey]
    }
    try {
        const response = await fetch("/ai_assistant/resolve_navigation", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model: action.model,
                type: actionType,
            }),
        })
        if (!response.ok) {
            return null
        }
        const payload = await response.json()
        if (!payload || !payload.ok) {
            return null
        }
        const hint = {
            action_id: payload.action_id || null,
            menu_id: payload.menu_id || null,
        }
        NAV_RESOLVE_CACHE[cacheKey] = hint
        return hint
    } catch (err) {
        return null
    }
}

async function openOdooAction(action) {
    if (!action || typeof action !== "object" || !action.model) {
        return
    }

    const params = new URLSearchParams()
    const actionType = action.type || "open_model_list"
    params.set("model", String(action.model))

    if (actionType === "open_record" && action.id) {
        params.set("id", String(action.id))
        params.set("view_type", "form")
        params.set("active_id", String(action.id))
        params.set("active_ids", JSON.stringify([action.id]))
        params.set("context", JSON.stringify({ active_id: action.id, active_ids: [action.id] }))
    } else {
        params.set("view_type", "list")
        if (Array.isArray(action.domain) && action.domain.length) {
            params.set("domain", JSON.stringify(action.domain))
        }
        if (typeof action.orderby === "string" && action.orderby.trim()) {
            params.set("orderby", action.orderby.trim())
        }
        if (typeof action.limit === "number" && action.limit > 0) {
            params.set("limit", String(action.limit))
        }
        const ctxActiveIdRaw = aiChatContext ? Number(aiChatContext.active_id) : NaN
        const ctxActiveId = Number.isInteger(ctxActiveIdRaw) && ctxActiveIdRaw > 0 ? ctxActiveIdRaw : null
        if (ctxActiveId) {
            params.set("active_id", String(ctxActiveId))
            params.set("active_ids", JSON.stringify([ctxActiveId]))
            params.set("context", JSON.stringify({ active_id: ctxActiveId, active_ids: [ctxActiveId] }))
        }
    }

    window.location.href = `/web#${params.toString()}`
}

function handleUiAction(action) {
    if (!action || typeof action !== "object") {
        return
    }
    if (action.type === "open_record" || action.type === "open_model_list") {
        void openOdooAction(action)
        return
    }
    if (action.key === "export_csv") {
        exportHistoryAsCsv()
        return
    }
    if (action.prompt) {
        sendMessage(action.prompt)
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

function toSafeHtml(text) {
    return formatInlineMarkdown(escapeHtml(String(text || "")))
}

function inferEntityHeader(queryText) {
    const q = String(queryText || "").toLowerCase()
    if (q.includes("cliente")) {
        return "Cliente"
    }
    if (q.includes("producto")) {
        return "Producto"
    }
    if (q.includes("factura")) {
        return "Factura"
    }
    if (q.includes("venta") || q.includes("pedido")) {
        return "Venta"
    }
    if (q.includes("compra")) {
        return "Compra"
    }
    if (q.includes("picking") || q.includes("guia") || q.includes("guía")) {
        return "Documento"
    }
    return "Item"
}

function prettifyHeaderLabel(rawKey) {
    const mapping = {
        monto: "Monto",
        amount_total: "Monto",
        total: "Total",
        subtotal: "Subtotal",
        cantidad: "Cantidad",
        qty_available: "Cantidad",
        product_uom_qty: "Cantidad",
        fecha: "Fecha",
        estado: "Estado",
        codigo: "Código",
        code: "Código",
        cliente: "Cliente",
        proveedor: "Proveedor",
    }
    const key = String(rawKey || "").trim().toLowerCase().replace(/\s+/g, "_")
    if (mapping[key]) {
        return mapping[key]
    }
    const compact = key.replace(/_/g, " ").trim()
    if (!compact) {
        return "Valor"
    }
    return compact.charAt(0).toUpperCase() + compact.slice(1)
}

function parseNumericValue(raw, fieldKey = "") {
    if (typeof raw === "number" && Number.isFinite(raw)) {
        return raw
    }
    if (typeof raw !== "string") {
        return null
    }
    let value = raw.trim()
    if (!value) {
        return null
    }
    const key = String(fieldKey || "").toLowerCase()
    value = value.replace(/^[^\d\-]+/, "").trim()
    const maybeThousandDots = /^\d{1,3}(\.\d{3})+$/.test(value)
    const monetaryLike = /(monto|total|importe|amount|subtotal|price)/.test(key)
    if (maybeThousandDots && monetaryLike) {
        value = value.replace(/\./g, "")
    } else if (value.includes(",") && !value.includes(".")) {
        value = value.replace(",", ".")
    } else if (value.includes(",") && value.includes(".")) {
        value = value.replace(/,/g, "")
    }
    const num = Number(value)
    return Number.isFinite(num) ? num : null
}

function formatMetricValue(raw, fieldKey = "", currencySymbol = "") {
    const key = String(fieldKey || "").toLowerCase()
    const numeric = parseNumericValue(raw, key)
    const mustFormatNumber = /(monto|total|importe|amount|subtotal|price|cantidad|qty|stock|count)/.test(key)
    if (numeric === null || !mustFormatNumber) {
        return String(raw || "")
    }
    const formatted = new Intl.NumberFormat("es-PE", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(numeric)
    const monetaryLike = /(monto|total|importe|amount|subtotal|price)/.test(key)
    const symbol = String(currencySymbol || "").trim()
    if (!monetaryLike || !symbol) {
        return formatted
    }
    if (/^\s*(S\/|US\$|\$|€|£)/i.test(String(raw || ""))) {
        return String(raw || "")
    }
    return `${symbol} ${formatted}`
}

function parseNumberedPipeRows(lines, queryText = "") {
    const parsedRows = []
    const columnKeys = []
    let hasLabelColumn = false

    for (const line of lines) {
        const trimmed = line.trim()
        const match = trimmed.match(/^(\d+)\.\s+(.+)$/)
        if (!match || !match[2].includes("|")) {
            continue
        }
        const parts = match[2].split("|").map((p) => p.trim()).filter(Boolean)
        if (parts.length < 2) {
            continue
        }
        const row = { label: null, values: {} }
        parts.forEach((part, index) => {
            const pair = part.match(/^([^:]+):\s*(.+)$/)
            if (pair) {
                const key = pair[1].trim().toLowerCase().replace(/\s+/g, "_")
                const value = pair[2].trim()
                row.values[key] = value
                if (!columnKeys.includes(key)) {
                    columnKeys.push(key)
                }
                return
            }
            if (index === 0 && !row.label) {
                row.label = part
                hasLabelColumn = true
            } else {
                const fallbackKey = `valor_${index + 1}`
                row.values[fallbackKey] = part
                if (!columnKeys.includes(fallbackKey)) {
                    columnKeys.push(fallbackKey)
                }
            }
        })
        parsedRows.push(row)
    }

    if (parsedRows.length < 2 || columnKeys.length === 0) {
        return null
    }

    const headers = []
    if (hasLabelColumn) {
        headers.push({ key: "__label", label: inferEntityHeader(queryText), isLabel: true })
    }
    columnKeys.forEach((key) => headers.push({ key, label: prettifyHeaderLabel(key), isLabel: false }))
    return {
        headers,
        rows: parsedRows,
        count: parsedRows.length,
    }
}

function renderStructuredTable(table, currencySymbol = "") {
    if (!table || !Array.isArray(table.headers) || !Array.isArray(table.rows)) {
        return ""
    }
    const html = ["<div class=\"o_ai_result_table\">", "<div class=\"o_ai_result_row o_ai_result_header_row\">"]
    table.headers.forEach((header) => {
        html.push(`<span class="o_ai_result_cell o_ai_result_header_cell">${toSafeHtml(header.label)}</span>`)
    })
    html.push("</div>")

    table.rows.forEach((row) => {
        html.push("<div class=\"o_ai_result_row\">")
        table.headers.forEach((header) => {
            let value = ""
            if (header.isLabel) {
                value = row.label || "-"
            } else {
                value = formatMetricValue(row.values[header.key], header.key, currencySymbol) || "-"
            }
            html.push(`<span class="o_ai_result_cell">${toSafeHtml(value)}</span>`)
        })
        html.push("</div>")
    })
    html.push("</div>")
    return html.join("")
}

function renderMessageHtml(text, queryText = "", currencySymbol = "") {
    const normalized = String(text || "").replace(/\r\n/g, "\n").trim()
    if (!normalized) {
        return { html: "", resultCount: 0 }
    }

    const lines = normalized.split("\n")
    const pipeLines = lines
        .map((line) => line.trim())
        .filter((line) => /^\d+\.\s+.+\|.+/.test(line))
    if (pipeLines.length >= 2) {
        const parsedTable = parseNumberedPipeRows(pipeLines, queryText)
        if (parsedTable) {
            const lead = lines
                .map((line) => line.trim())
                .filter((line) => line && !/^\d+\.\s+.+\|.+/.test(line))
                .filter((line) => !/^resultados:?$/i.test(line))
            const leadHtml = lead.map((line) => `<p>${toSafeHtml(line)}</p>`).join("")
            const tableHtml = renderStructuredTable(parsedTable, currencySymbol)
            return { html: `${leadHtml}${tableHtml}`, resultCount: parsedTable.count }
        }
    }

    const html = []
    let listType = null
    let orderedCount = 0

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
            orderedCount += 1
            if (listType !== "ol") {
                closeList()
                html.push(`<ol start="${orderedMatch[1]}">`)
                listType = "ol"
            }
            html.push(`<li>${toSafeHtml(orderedMatch[2])}</li>`)
            continue
        }

        const unorderedMatch = line.match(/^[-*]\s+(.+)$/)
        if (unorderedMatch) {
            if (listType !== "ul") {
                closeList()
                html.push("<ul>")
                listType = "ul"
            }
            html.push(`<li>${toSafeHtml(unorderedMatch[1])}</li>`)
            continue
        }

        closeList()
        html.push(`<p>${toSafeHtml(line)}</p>`)
    }

    closeList()
    return { html: html.join(""), resultCount: orderedCount }
}

function normalizeBadges(response, ui) {
    const badges = []
    const mode = response && response.answer_mode
    const modeBadge = ANSWER_MODE_BADGES[mode]
    if (modeBadge) {
        badges.push(modeBadge)
    }
    if (ui && Array.isArray(ui.badges)) {
        badges.push(...ui.badges)
    }
    const output = []
    const seen = new Set()
    badges.forEach((b) => {
        const key = String(b || "").trim()
        if (!key || seen.has(key)) {
            return
        }
        seen.add(key)
        output.push(key)
    })
    return output.slice(0, 4)
}

function toBusinessTitle(questionText) {
    const cleaned = String(questionText || "").replace(/[?¿]+$/g, "").trim()
    if (!cleaned) {
        return null
    }
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1)
}

function buildMessageMeta(response, ui, questionText = "") {
    const answerType = response && response.answer_type ? response.answer_type : null
    return {
        badges: normalizeBadges(response, ui),
        actions: (response && Array.isArray(response.actions) ? response.actions : null) || (ui && ui.actions) || [],
        clarification:
            (ui && ui.clarification) ||
            (response && response.needs_clarification
                ? { required: true, question: "Necesito una precisión para responder mejor.", options: response.clarification_options || [] }
                : null),
        answerTitle: ANSWER_TYPE_LABELS[answerType] || null,
        businessTitle: toBusinessTitle(questionText),
        queryText: questionText || "",
        currencySymbol: response && response.metadata ? response.metadata.currency_symbol : null,
        currencyName: response && response.metadata ? response.metadata.currency_name : null,
        latencyMs: response && response.metadata ? response.metadata.latency_ms : null,
    }
}

function appendMessage(role, text, time, persist = true, meta = null) {
    const container = document.getElementById("ai_chat_messages")
    if (!container) {
        return
    }

    const bubble = document.createElement("div")
    bubble.className = `o_ai_msg o_ai_msg_${role}`
    if (role === "bot") {
        bubble.classList.add("o_ai_msg_card")
    }
    const content = document.createElement("div")
    content.className = "o_ai_msg_content"
    const rendered = renderMessageHtml(
        text,
        meta && meta.queryText ? meta.queryText : "",
        meta && meta.currencySymbol ? meta.currencySymbol : ""
    )
    content.innerHTML = rendered.html

    if (role === "bot" && meta && (meta.answerTitle || meta.businessTitle || rendered.resultCount > 0)) {
        const header = document.createElement("div")
        header.className = "o_ai_result_header"
        if (meta.answerTitle) {
            const typeNode = document.createElement("div")
            typeNode.className = "o_ai_result_title"
            typeNode.innerText = meta.answerTitle
            header.appendChild(typeNode)
        }
        if (meta.businessTitle) {
            const heading = document.createElement("div")
            heading.className = "o_ai_result_heading"
            heading.innerText = meta.businessTitle
            header.appendChild(heading)
        }
        if (rendered.resultCount > 0) {
            const subtitle = document.createElement("div")
            subtitle.className = "o_ai_result_subtitle"
            subtitle.innerText = `${rendered.resultCount} resultados encontrados`
            header.appendChild(subtitle)
        }
        content.insertBefore(header, content.firstChild)
    }

    if (role === "bot" && meta && Array.isArray(meta.badges) && meta.badges.length) {
        const tags = document.createElement("div")
        tags.className = "o_ai_msg_tags"
        meta.badges.slice(0, 4).forEach((badgeText) => {
            const badge = document.createElement("span")
            badge.className = "o_ai_msg_tag"
            badge.innerText = String(badgeText)
            tags.appendChild(badge)
        })
        content.insertBefore(tags, content.firstChild)
    }
    bubble.appendChild(content)

    if (role === "bot" && meta && Array.isArray(meta.actions) && meta.actions.length) {
        const actionsWrap = document.createElement("div")
        actionsWrap.className = "o_ai_msg_actions"
        meta.actions.forEach((action) => {
            const btn = document.createElement("button")
            btn.type = "button"
            btn.className = "o_ai_msg_action_btn"
            btn.innerText = action.label || action.key
            btn.addEventListener("click", () => handleUiAction(action))
            actionsWrap.appendChild(btn)
        })
        bubble.appendChild(actionsWrap)
    }

    if (role === "bot" && meta && meta.clarification && meta.clarification.required) {
        const clarifyBox = document.createElement("div")
        clarifyBox.className = "o_ai_clarify_box"

        const title = document.createElement("div")
        title.className = "o_ai_clarify_title"
        title.innerText = meta.clarification.question || "Necesito una precisión para responder mejor."
        clarifyBox.appendChild(title)

        const optionsWrap = document.createElement("div")
        optionsWrap.className = "o_ai_clarify_options"
        const options = Array.isArray(meta.clarification.options) ? meta.clarification.options : []
        options.forEach((opt) => {
            const chip = document.createElement("button")
            chip.type = "button"
            chip.className = "o_ai_chip"
            chip.innerText = opt.label || opt.key
            chip.addEventListener("click", () => {
                const value = opt.submit_value || opt.value || opt.label || opt.key
                if (value) {
                    sendMessage(String(value))
                }
            })
            optionsWrap.appendChild(chip)
        })
        clarifyBox.appendChild(optionsWrap)
        bubble.appendChild(clarifyBox)
    }

    const metaNode = document.createElement("div")
    metaNode.className = "o_ai_msg_meta"
    metaNode.innerText = time || nowTime()
    bubble.appendChild(metaNode)

    container.appendChild(bubble)
    container.scrollTop = container.scrollHeight

    if (persist) {
        const history = loadHistory()
        history.push({ role, text, time: metaNode.innerText })
        saveHistory(history)
    }
}

function ensureGreeting() {
    const container = document.getElementById("ai_chat_messages")
    if (!container) {
        return
    }

    if (container.childElementCount === 0) {
        appendMessage("bot", "Hola, soy tu asistente. ¿En qué puedo ayudarte?", nowTime(), true, {
            badges: ["Asistente listo"],
            actions: [],
        })
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
        status.innerText = isLoading ? "● Procesando..." : "● En línea"
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

async function sendMessage(messageOverride = null) {
    const input = document.getElementById("ai_chat_message")
    if (!input) {
        return
    }
    if (input.disabled) {
        return
    }

    const rawMessage = typeof messageOverride === "string" ? messageOverride : input.value
    const message = rawMessage.trim()
    if (!message) {
        return
    }

    lastUserMessage = message
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
            appendMessage("bot", `Error del servidor: ${httpResponse.status}`, nowTime(), true, {
                badges: ["Error"],
            })
            return
        }

        let rpcResponse = null
        try {
            rpcResponse = await httpResponse.json()
        } catch (err) {
            appendMessage("bot", "Error: respuesta no es JSON.", nowTime(), true, {
                badges: ["Error"],
            })
            return
        }

        const answer = rpcResponse && rpcResponse.answer ? rpcResponse.answer : null
        const ui = rpcResponse && rpcResponse.ui ? rpcResponse.ui : null
        updateHeaderFromUi({
            latency_ms:
                rpcResponse && rpcResponse.metadata && typeof rpcResponse.metadata.latency_ms === "number"
                    ? rpcResponse.metadata.latency_ms
                    : (ui ? ui.latency_ms : null),
        })
        updateContextFromUi(ui)
        renderSuggestions(ui && ui.suggestions ? ui.suggestions : null, getActiveModel())
        appendMessage("bot", answer || "Sin respuesta.", nowTime(), true, buildMessageMeta(rpcResponse, ui, lastUserMessage))
    } catch (err) {
        appendMessage("bot", "No pude conectar con el servidor.", nowTime(), true, {
            badges: ["Error de conexión"],
        })
    } finally {
        setLoading(false)
    }
}

function initChatUI() {
    syncSessionWithContext()
    updateHeaderFromUi(null)
    updateContextFromUi(null)
    renderSuggestions(null, getActiveModel())
    setInputPlaceholder()
    renderHistory()
    ensureGreeting()
    void loadContextSummary()

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
            updateHeaderFromUi(null)
            updateContextFromUi(null)
            renderSuggestions(null, getActiveModel())
            setInputPlaceholder()
            void loadContextSummary()
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
