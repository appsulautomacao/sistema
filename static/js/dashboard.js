let currentConversationId = null;
let iaEnabled = true;
let conversationRequestToken = 0;
let selectedAttachmentMessageIds = new Set();
let currentConversationAttachmentIds = [];
let lastConversationRenderSignature = null;
let selectedMediaFiles = [];
let allConversations = [];
let activeConversationFilter = "all";
let lastCentralWhatsappStatus = null;
let currentAssistantSuggestion = "";
const USER_COMPANY_ID = Number(document.body?.dataset?.companyId || window.USER_COMPANY_ID || 0);
const socket = typeof window.io === "function"
  ? window.io()
  : {
      connected: false,
      on() {},
      emit() {},
    };
socket.on("connect", () => {
  socket.emit("join_company", {
    company_id: USER_COMPANY_ID
  });
  socket.emit("presence_heartbeat");
});

socket.on("conversation_moved", data => {

  console.log("MOVIDA:", data);

  // remove da lista esquerda
  const el = document.querySelector(
    `[data-conversation-id="${data.conversation_id}"]`
  );

  if (el) el.remove();

  // se estava aberta, limpa chat
  if (currentConversationId == data.conversation_id) {
    currentConversationId = null;

    document.getElementById("chatMessages").innerHTML = "";
    document.getElementById("chatClient").innerText = "Selecione uma conversa";
    document.getElementById("conversationActions").classList.add("d-none");
  }

  // atualiza setores direita
  loadSectorOverview();
});




let lastRenderedDate = null;

function getInitials(name) {
  if (!name) return "?";
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part.charAt(0).toUpperCase())
    .join("");
}

function formatRelativeTime(dateString) {
  if (!dateString) return "-";

  const date = new Date(dateString);
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000));

  if (diffMinutes < 1) return "agora";
  if (diffMinutes < 60) return `há ${diffMinutes} min`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `há ${diffHours} h`;

  return date.toLocaleDateString("pt-BR");
}

function formatDurationFromDates(startDate, endDate = new Date()) {
  if (!startDate) return "-";

  const start = new Date(startDate);
  const diffMinutes = Math.max(0, Math.round((endDate.getTime() - start.getTime()) / 60000));
  const hours = Math.floor(diffMinutes / 60);
  const minutes = diffMinutes % 60;

  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}min`;
  }

  return `${minutes} min`;
}

function formatConversationPhone(phone) {
  if (!phone) return "Telefone nao informado";
  return String(phone).replace("@s.whatsapp.net", "");
}

function getPriorityLabel(conversation) {
  if (!conversation) return "-";
  if (conversation.sla_breached) return "Alta";
  if (!conversation.is_read) return "Média";
  return "Normal";
}

function getConversationStatusBadge(conversation) {
  if (!conversation) {
    return { label: "Sem status", tone: "gray" };
  }

  if (conversation.sla_breached) {
    return { label: "SLA crítico", tone: "danger" };
  }

  if (!conversation.is_read) {
    return { label: "Não lida", tone: "warning" };
  }

  if (conversation.assigned_to) {
    return { label: "Em atendimento", tone: "success" };
  }

  return { label: "Na fila", tone: "gray" };
}

function conversationMatchesFilter(conversation) {
  switch (activeConversationFilter) {
    case "unread":
      return !conversation.is_read;
    case "mine":
      return !!conversation.is_mine;
    case "sla":
      return !!conversation.sla_breached;
    case "assigned":
      return !!conversation.assigned_to;
    default:
      return true;
  }
}

function updateDashboardCounters(conversations) {
  const total = conversations.length;
  const unread = conversations.filter(conversation => !conversation.is_read).length;
  const slaRisk = conversations.filter(conversation => conversation.sla_breached).length;
  const inService = conversations.filter(conversation => !!conversation.assigned_to).length;

  const conversationCount = document.getElementById("conversationCount");
  if (conversationCount) {
    conversationCount.textContent = `${total} ativa${total === 1 ? "" : "s"}`;
  }

  const sidebarConversationCount = document.getElementById("sidebarConversationCount");
  if (sidebarConversationCount) {
    sidebarConversationCount.textContent = String(total);
  }

  const kpiOpenConversations = document.getElementById("kpiOpenConversations");
  if (kpiOpenConversations) {
    kpiOpenConversations.textContent = String(total);
  }

  const kpiUnreadConversations = document.getElementById("kpiUnreadConversations");
  if (kpiUnreadConversations) {
    kpiUnreadConversations.textContent = String(unread);
  }

  const kpiSlaRisk = document.getElementById("kpiSlaRisk");
  if (kpiSlaRisk) {
    kpiSlaRisk.textContent = String(slaRisk);
  }

  const kpiInService = document.getElementById("kpiInService");
  if (kpiInService) {
    kpiInService.textContent = String(inService);
  }

  const kpiAverageFirstResponse = document.getElementById("kpiAverageFirstResponse");
  if (kpiAverageFirstResponse) {
    kpiAverageFirstResponse.textContent = "--";
  }
}

function updateConversationHeader(data) {
  const conversation = allConversations.find(item => item.id === data.id) || {};
  const clientName = data.client_name || conversation.client_name || "Selecione uma conversa";

  const chatClient = document.getElementById("chatClient");
  if (chatClient) chatClient.innerText = clientName;

  const chatClientAvatar = document.getElementById("chatClientAvatar");
  if (chatClientAvatar) {
    chatClientAvatar.textContent = getInitials(clientName);
  }

  const chatClientSubline = document.getElementById("chatClientSubline");
  if (chatClientSubline) {
    const phone = conversation.client_phone || "Telefone não disponível";
    const protocol = `Conversa #${data.id}`;
    chatClientSubline.textContent = `${phone} • ${protocol}`;
  }

  const chatSlaBadge = document.getElementById("chatSlaBadge");
  if (chatSlaBadge) {
    const statusBadge = getConversationStatusBadge(conversation);
    chatSlaBadge.className = `badge ${statusBadge.tone}`;
    chatSlaBadge.textContent = statusBadge.label;
  }

  const chatSectorBadge = document.getElementById("chatSectorBadge");
  if (chatSectorBadge) {
    chatSectorBadge.textContent = `Setor: ${conversation.sector || "Central"}`;
  }

  const chatAssignedBadge = document.getElementById("chatAssignedBadge");
  if (chatAssignedBadge) {
    chatAssignedBadge.textContent = `Responsável: ${conversation.user_name || "Não assumida"}`;
  }

  const infoChannel = document.getElementById("conversationInfoChannel");
  if (infoChannel) infoChannel.textContent = "WhatsApp";

  const infoQueue = document.getElementById("conversationInfoQueue");
  if (infoQueue) {
    infoQueue.textContent = formatDurationFromDates(conversation.created_at);
  }

  const infoLastInteraction = document.getElementById("conversationInfoLastInteraction");
  if (infoLastInteraction) {
    infoLastInteraction.textContent = formatRelativeTime(conversation.last_message_time);
  }

  const infoPriority = document.getElementById("conversationInfoPriority");
  if (infoPriority) {
    infoPriority.textContent = getPriorityLabel(conversation);
  }
}

function resetAssistantSuggestionPanel() {
  currentAssistantSuggestion = "";

  const panel = document.getElementById("assistantSuggestionPanel");
  const body = document.getElementById("assistantSuggestionBody");
  const meta = document.getElementById("assistantSuggestionMeta");
  const useBtn = document.getElementById("assistantUseBtn");

  if (panel) panel.classList.add("d-none");
  if (body) body.textContent = "";
  if (meta) meta.textContent = "Use a IA para montar uma pré-resposta com base no histórico e no RAG.";
  if (useBtn) useBtn.disabled = true;
}

function renderAssistantSuggestion(result) {
  const panel = document.getElementById("assistantSuggestionPanel");
  const body = document.getElementById("assistantSuggestionBody");
  const meta = document.getElementById("assistantSuggestionMeta");
  const useBtn = document.getElementById("assistantUseBtn");

  if (!panel || !body || !meta || !useBtn) return;

  currentAssistantSuggestion = (result?.reply || "").trim();
  panel.classList.remove("d-none");
  body.textContent = currentAssistantSuggestion || "A IA não conseguiu gerar uma sugestão para esta conversa.";

  const ragCount = result?.rag_result?.results?.length || 0;
  const provider = result?.provider || "fallback";
  const model = result?.model || "-";
  const reason = result?.reason ? ` | motivo: ${result.reason}` : "";
  meta.textContent = `provedor: ${provider} | modelo: ${model} | contexto RAG: ${ragCount} trecho(s)${reason}`;
  useBtn.disabled = !currentAssistantSuggestion;
}

function loadAssistantSuggestion() {
  if (!currentConversationId) return;

  const panel = document.getElementById("assistantSuggestionPanel");
  const body = document.getElementById("assistantSuggestionBody");
  const meta = document.getElementById("assistantSuggestionMeta");
  if (!panel || !body || !meta) return;

  panel.classList.remove("d-none");
  body.textContent = "Gerando sugestão da IA...";
  meta.textContent = "Consultando histórico da conversa e RAG da empresa.";

  fetch(`/api/conversations/${currentConversationId}/assistant-suggestion`)
    .then(async res => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.error || "Não foi possível gerar a sugestão da IA.");
      }
      return data;
    })
    .then(renderAssistantSuggestion)
    .catch(err => {
      panel.classList.remove("d-none");
      body.textContent = err.message;
      meta.textContent = "Falha ao gerar a sugestão.";
    });
}

function openMobileChatIfNeeded() {
  if (window.innerWidth <= 860) {
    document.body.classList.add("mobile-chat-open");
  }
}

function renderCentralAiState(enabled) {
  iaEnabled = !!enabled;

  const label = document.getElementById("iaLabel");
  if (label) {
    label.textContent = iaEnabled ? "IA: Ligada" : "IA: Humana";
  }

  const hint = document.getElementById("iaStatusHint");
  if (hint) {
    hint.textContent = iaEnabled
      ? "A IA ajuda a triar e orientar o atendimento da central."
      : "A central está operando apenas com atendimento humano.";
  }

  const button = document.getElementById("iaToggleBtn");
  if (button) {
    button.textContent = iaEnabled ? "IA: Ligada" : "IA: Desligada";
    button.classList.toggle("off", !iaEnabled);
  }
}

async function toggleCentralAi() {
  const nextEnabled = !iaEnabled;

  const response = await fetch("/api/central/ai", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      enabled: nextEnabled
    })
  });

  if (!response.ok) {
    throw new Error("Nao foi possivel atualizar a IA da central.");
  }

  renderCentralAiState(nextEnabled);
}

async function connectCentralWhatsapp() {
  await fetch("/api/whatsapp/connect", { method: "POST" });
  setTimeout(refreshCentralWhatsappStatus, 2000);
}

async function refreshCentralWhatsappStatus() {
  try {
    const res = await fetch("/api/whatsapp/status");
    const data = await res.json();

    const isConnected =
      data?.instance?.state === "open" ||
      data?.status === "open" ||
      data?.status?.instance?.state === "open";

    if (lastCentralWhatsappStatus === isConnected) return;
    lastCentralWhatsappStatus = isConnected;

    const container = document.getElementById("whatsappStatus");
    const topStatus = document.getElementById("whatsappStatusTop");
    if (!container) return;

    if (isConnected) {
      container.innerHTML = `
        <div class="wa-status-box">
          <div class="wa-dot wa-online"></div>
          <span>WhatsApp conectado</span>
        </div>
      `;
      if (topStatus) {
        topStatus.classList.remove("offline");
        topStatus.innerHTML = `<span class="status-dot"></span><span>WhatsApp logado</span>`;
      }
      return;
    }

    container.innerHTML = `
      <div class="wa-status-box">
        <div class="wa-dot wa-offline"></div>
        <span>Desconectado</span>
      </div>
      <button class="btn btn-sm btn-success mt-2" id="connectWhatsappBtn" type="button">
        Conectar
      </button>
    `;
    if (topStatus) {
      topStatus.classList.add("offline");
      topStatus.innerHTML = `<span class="status-dot"></span><span>WhatsApp desconectado</span>`;
    }
  } catch (err) {
    console.error("Erro ao buscar status:", err);
  }
}

function renderConversationMessages(messages) {
  const chat = document.getElementById("chatMessages");
  if (!chat) return;

  const previousSelection = new Set(selectedAttachmentMessageIds);
  chat.innerHTML = "";
  lastRenderedDate = null;
  currentConversationAttachmentIds = (messages || [])
    .filter(isAttachmentMessage)
    .map(message => message.id);
  selectedAttachmentMessageIds = new Set(
    currentConversationAttachmentIds.filter(messageId => previousSelection.has(messageId))
  );
  (messages || []).forEach(renderMessage);
  updateAttachmentBulkActions();
}

function buildConversationRenderSignature(messages) {
  return JSON.stringify(
    (messages || []).map(message => ({
      id: message.id,
      created_at: message.created_at,
      type: message.type,
      content: message.content,
      media_url: message.media_url,
      attachments: (message.attachments || []).map(attachment => ({
        id: attachment.id,
        download_status: attachment.download_status,
        storage_key: attachment.storage_key,
        original_filename: attachment.original_filename,
      })),
    }))
  );
}

function isChatNearBottom(chatElement, threshold = 120) {
  if (!chatElement) return true;
  const distanceFromBottom = chatElement.scrollHeight - chatElement.scrollTop - chatElement.clientHeight;
  return distanceFromBottom <= threshold;
}

function fetchConversation(conversationId, options = {}) {
  const { markAsRead = false, silent = false } = options;
  const requestToken = ++conversationRequestToken;

  if (markAsRead) {
    fetch(`/api/conversations/${conversationId}/read`, {
      method: "POST"
    }).catch(err => console.error("Erro ao marcar como lida:", err));
  }

  return fetch(`/api/conversations/${conversationId}`)
    .then(async res => {
      const data = await res.json();
      if (!res.ok) {
        throw { response: data, silent };
      }
      return data;
    })
    .then(data => {
      if (requestToken !== conversationRequestToken || conversationId != currentConversationId) {
        return null;
      }

      updateConversationHeader(data);
      const renderSignature = buildConversationRenderSignature(data.messages);
      const chat = document.getElementById("chatMessages");
      const shouldStickToBottom = markAsRead || isChatNearBottom(chat);

      if (renderSignature !== lastConversationRenderSignature) {
        renderConversationMessages(data.messages);
        lastConversationRenderSignature = renderSignature;
      }

      const actions = document.getElementById("conversationActions");
      if (actions) actions.classList.remove("d-none");

      loadConversationHistory(conversationId);
      loadConversationMetrics(conversationId);

      if (chat && shouldStickToBottom) {
        chat.scrollTop = chat.scrollHeight;
      }

      return data;
    });
}

// ============================
// INIT
// ============================
document.addEventListener("DOMContentLoaded", () => {
  loadConversations();
  loadSectors();
  loadUser();
  loadSectorOverview();
  refreshCentralWhatsappStatus();
  setInterval(refreshCentralWhatsappStatus, 5000);

  const sidebarToggleBtn = document.getElementById("sidebarToggleBtn");
  const sidebarOverlay = document.getElementById("sidebarOverlay");
  const mobileBackBtn = document.getElementById("mobileBackBtn");
  const newActionBtn = document.getElementById("newActionBtn");
  const detailToggleBtn = document.getElementById("detailToggleBtn");
  const attachShortcutBtn = document.getElementById("attachShortcutBtn");
  const whatsappStatus = document.getElementById("whatsappStatus");
  const iaToggleBtn = document.getElementById("iaToggleBtn");
  const assistantSuggestBtn = document.getElementById("assistantSuggestBtn");
  const assistantRefreshBtn = document.getElementById("assistantRefreshBtn");
  const assistantUseBtn = document.getElementById("assistantUseBtn");

  if (sidebarToggleBtn) {
    sidebarToggleBtn.addEventListener("click", () => {
      document.body.classList.add("sidebar-open");
    });
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener("click", () => {
      document.body.classList.remove("sidebar-open");
    });
  }

  if (mobileBackBtn) {
    mobileBackBtn.addEventListener("click", () => {
      document.body.classList.remove("mobile-chat-open");
    });
  }

  if (newActionBtn) {
    newActionBtn.addEventListener("click", () => {
      document.getElementById("conversationFilters")?.scrollIntoView({
        behavior: "smooth",
        block: "center"
      });
    });
  }

  if (detailToggleBtn) {
    detailToggleBtn.addEventListener("click", () => {
      document.getElementById("conversationDetailsPanel")?.classList.toggle("d-none");
    });
  }

  if (attachShortcutBtn) {
    attachShortcutBtn.addEventListener("click", () => {
      document.getElementById("mediaInput")?.click();
    });
  }

  if (whatsappStatus) {
    whatsappStatus.addEventListener("click", event => {
      const target = event.target;
      if (target instanceof HTMLElement && target.id === "connectWhatsappBtn") {
        connectCentralWhatsapp().catch(err => {
          console.error("Erro ao conectar WhatsApp:", err);
        });
      }
    });
  }

  if (iaToggleBtn) {
    iaToggleBtn.addEventListener("click", () => {
      toggleCentralAi().catch(err => {
        console.error("Erro ao atualizar IA:", err);
        alert(err.message);
      });
    });
  }

  if (assistantSuggestBtn) {
    assistantSuggestBtn.addEventListener("click", loadAssistantSuggestion);
  }

  if (assistantRefreshBtn) {
    assistantRefreshBtn.addEventListener("click", loadAssistantSuggestion);
  }

  if (assistantUseBtn) {
    assistantUseBtn.addEventListener("click", () => {
      const input = document.getElementById("messageInput");
      if (!input || !currentAssistantSuggestion) return;
      input.value = currentAssistantSuggestion;
      input.focus();
    });
  }

  const sendBtn = document.getElementById("sendMessageBtn");
  if (sendBtn) sendBtn.addEventListener("click", sendMessage);

  const markUnreadBtn = document.getElementById("markUnread");
  if (markUnreadBtn) markUnreadBtn.addEventListener("click", markUnread);

  const downloadSelectedAttachmentsBtn = document.getElementById("downloadSelectedAttachmentsBtn");
  if (downloadSelectedAttachmentsBtn) {
    downloadSelectedAttachmentsBtn.addEventListener("click", downloadSelectedAttachments);
  }
  const toggleAllAttachmentsBtn = document.getElementById("toggleAllAttachmentsBtn");
  if (toggleAllAttachmentsBtn) {
    toggleAllAttachmentsBtn.addEventListener("click", toggleAllAttachmentsSelection);
  }
  const removeAttachmentBtn = document.getElementById("removeAttachmentBtn");
  if (removeAttachmentBtn) {
    removeAttachmentBtn.addEventListener("click", clearSelectedMediaFile);
  }

  const sectorSelect = document.getElementById("sectorSelect");
  const mediaInput = document.getElementById("mediaInput");

  if (sectorSelect) {
  sectorSelect.addEventListener("change", async e => {

    if (!currentConversationId || !e.target.value) return;

    const conversationId = currentConversationId;

    const selectedSectorName =
      e.target.options[e.target.selectedIndex].text;

    if (!confirm(`Tem certeza que deseja enviar para ${selectedSectorName}?`)) {
      e.target.value = "";
      return;
    }

    try {

      const assign = await fetch(`/api/conversations/${conversationId}/assign`, {
        method: "POST"
      });

      const assignData = await assign.json();

      if (!assign.ok) {
        alert(assignData.error || "Erro ao assumir");
        return;
      }

      const move = await fetch(`/api/conversations/${conversationId}/sector`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          sector_id: e.target.value
        })
      });

      const moveData = await move.json();

      if (!move.ok) {
        alert(moveData.error || "Erro ao mover");
        return;
      }

      loadConversations();
      loadSectorOverview();

    } catch (err) {
      console.error(err);
    }

  });
}


  const input = document.getElementById("messageInput");
  if (input) {
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  if (mediaInput) {
    mediaInput.addEventListener("change", updateSelectedMediaPreview);
  }

  const searchInput = document.getElementById("conversationSearch");
  if (searchInput) {
    searchInput.addEventListener("input", renderConversationList);
  }

  document.querySelectorAll(".filter-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      activeConversationFilter = chip.dataset.filter || "all";
      document.querySelectorAll(".filter-chip").forEach(item => item.classList.remove("active"));
      chip.classList.add("active");
      renderConversationList();
    });
  }

  const assignBtn = document.getElementById("assignBtn");
  if (assignBtn) {
    assignBtn.addEventListener("click", () => {
      if (!currentConversationId) return;

      fetch(`/api/conversations/${currentConversationId}/assign`, {
        method: "POST"
      })
        .then(res => res.json())
        .then(data => {
          if (data.error) {
            alert(data.error);
          } else {
            alert("Conversa assumida!");
            loadConversations();
          }
        });
    });
  }

  setInterval(() => {
    if (socket.connected) {
      socket.emit("presence_heartbeat");
    }
  }, 15000);

  setInterval(() => {
    loadConversations();
    if (currentConversationId) {
      openConversation(currentConversationId, true);
    }
  }, 3000);

  window.addEventListener("resize", () => {
    if (window.innerWidth > 860) {
      document.body.classList.remove("mobile-chat-open");
    }
    if (window.innerWidth > 1180) {
      document.body.classList.remove("sidebar-open");
    }
  });

}); 

// ============================
// CONVERSAS
// ============================
function loadConversations() {
  const list = document.getElementById("conversationList");
  if (list && !allConversations.length) {
    list.innerHTML = `<div class="sector-item">Carregando conversas...</div>`;
  }

  fetch("/api/dashboard/conversations")
    .then(r => r.json())
    .then(conversations => {
      allConversations = Array.isArray(conversations) ? conversations : [];
      updateDashboardCounters(allConversations);
      renderConversationList();
    })
    .catch(err => {
      console.error("Erro ao carregar conversas:", err);
      if (list) {
        list.innerHTML = `<div class="sector-item">Nao foi possivel carregar as conversas.</div>`;
      }
    });
}

function renderConversationList() {
  const list = document.getElementById("conversationList");
  if (!list) return;

  list.innerHTML = "";
  const searchValue = (document.getElementById("conversationSearch")?.value || "").toLowerCase();

  const conversations = allConversations.filter(conversation => {
    if (!conversationMatchesFilter(conversation)) {
      return false;
    }

    if (!searchValue) {
      return true;
    }

    const haystack = [
      conversation.client_name,
      conversation.client_phone,
      conversation.last_message,
      conversation.user_name,
      conversation.sector,
    ].filter(Boolean).join(" ").toLowerCase();

    return haystack.includes(searchValue);
  });

  conversations.forEach(c => {
    const div = document.createElement("div");
    div.className = "conversation-item";
    if (c.id === currentConversationId) {
      div.classList.add("conversation-active");
    }

    div.dataset.conversationId = c.id;
    const statusBadge = getConversationStatusBadge(c);
    const timeLabel = c.last_message_time
      ? formatRelativeTime(c.last_message_time)
      : "-";
    const exactTimeLabel = c.last_message_time
      ? new Date(c.last_message_time).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
      : "-";
    const lastMessage = c.last_message || "Sem mensagens ainda";

    div.innerHTML = `
      <div class="conversation-layout">
        <div class="conversation-side">
          <div class="conversation-avatar">${getInitials(c.client_name || "S")}</div>
          <span class="badge primary conversation-sector-badge">${c.sector || "Central"}</span>
        </div>

        <div class="conversation-body">
          <div class="conversation-top">
            <div class="conversation-text">
              <strong>${c.client_name || "Sem nome"}</strong>
            </div>
            <span class="conversation-time-pill" title="${timeLabel}">
              ${exactTimeLabel}
            </span>
          </div>

          <div class="conversation-preview conversation-preview-inline" title="${timeLabel}">
            ${lastMessage}
          </div>

          <div class="conversation-card-footer">
            <div class="conversation-badges">
              <span class="badge ${statusBadge.tone}">${statusBadge.label}</span>
            </div>
          </div>
        </div>
      </div>
    `;


    div.onclick = () => openConversation(c.id);
    list.appendChild(div);
  });

  if (!conversations.length) {
    list.innerHTML = `<div class="sector-item">Nenhuma conversa encontrada com o filtro atual.</div>`;
  }
}

// ============================
// CHAT
// ============================
function formatDateSeparator(dateString) {
  const date = new Date(dateString);

  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  const sameDay = (d1, d2) =>
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate();

  if (sameDay(date, today)) return "Hoje";
  if (sameDay(date, yesterday)) return "Ontem";

  return date.toLocaleDateString("pt-BR");
}




function openConversation(id, silentRefresh = false) {

  if (!silentRefresh && currentConversationId) {
    socket.emit("leave_conversation", {
      conversation_id: currentConversationId
    });
  }

  currentConversationId = id;
  if (!silentRefresh) {
    resetAssistantSuggestionPanel();
  }
  if (!silentRefresh) {
    openMobileChatIfNeeded();
    document.body.classList.remove("sidebar-open");
  }

  if (!silentRefresh) {
    socket.emit("join_conversation", {
      conversation_id: id
    });
  }

  fetchConversation(id, {
    markAsRead: !silentRefresh,
    silent: silentRefresh,
  }).catch(err => {
    if (err?.silent) return;

    const data = err?.response || {};
    if (data.assigned_to) {
      alert(`Esta conversa jÃ¡ estÃ¡ sendo tratada por ${data.assigned_to}`);
      return;
    }

    alert("Erro ao abrir conversa.");
  });
  return;

  lastRenderedDate = null;

  if (!silentRefresh) {
    fetch(`/api/conversations/${id}/read`, {
      method: "POST"
    }).catch(err => console.error("Erro ao marcar como lida:", err));
  }

  // Buscar conversa
  fetch(`/api/conversations/${id}`)
    .then(res => {
      if (!res.ok) {
        throw new Error(`Erro ${res.status}`);
      }
      return res.json();
    })
    .then(data => {

      const chatClient = document.getElementById("chatClient");
      if (chatClient) chatClient.innerText = data.client_name;

      const chat = document.getElementById("chatMessages");
      if (!chat) return;

      // 🔥 LIMPA CHAT
      chat.innerHTML = "";
      lastRenderedDate = null;

      // 🔥 RENDERIZA TUDO PELO FUNIL ÚNICO
      data.messages.forEach(m => {
        renderMessage(m);
      });

      const actions = document.getElementById("conversationActions");
      if (actions) actions.classList.remove("d-none");

      loadConversationHistory(id);
      loadConversationMetrics(id);

      chat.scrollTop = chat.scrollHeight;
    })
    .catch(async err => {
      if (silentRefresh) return;
      try {
        const res = await fetch(`/api/conversations/${id}`);
        const data = await res.json();

        if (data.assigned_to) {
          alert(`Esta conversa já está sendo tratada por ${data.assigned_to}`);
        }
      } catch {
        alert("Erro ao abrir conversa.");
      }
    });
}

  






// ============================
// SETORES
// ============================
function loadSectors() {
  fetch("/api/sectors")
    .then(r => {
      if (!r.ok) {
        console.warn("⚠️ /api/sectors ainda não implementado");
        return [];
      }
      return r.json();
    })
    .then(sectors => {
      if (!Array.isArray(sectors)) return;

      const select = document.getElementById("sectorSelect");
      const list = document.getElementById("sectorList");

      if (!select || !list) return;

      select.innerHTML = `<option value="">Enviar para setor...</option>`;
      list.innerHTML = "";

      sectors.forEach(s => {
        select.innerHTML += `<option value="${s.id}">${s.name}</option>`;
        list.innerHTML += `<div class="sector-item">${s.name}</div>`;
      });
    })
    .catch(err => {
      console.warn("Erro ao carregar setores:", err);
    });
}


// ============================
// MENSAGENS
// ============================

function formatAgentMessage(content, sender) {

  if (sender === "agent" && content) {

    const parts = content.split(":\n");

    if (parts.length === 2) {
      const header = parts[0];
      const body = parts[1];

      return `
        <div class="agent-prefix">${header}:</div>
        <div>${body}</div>
      `;
    }
  }

  return content || "";
}

function getPrimaryAttachment(data) {
  if (!data || !Array.isArray(data.attachments) || !data.attachments.length) {
    return null;
  }
  return data.attachments[0];
}

function getMessageDownloadUrl(data) {
  const attachment = getPrimaryAttachment(data);
  if (attachment?.download_url) {
    return attachment.download_url;
  }
  if (data.sender === "client" && ["image", "audio", "video", "document"].includes(data.type)) {
    return `/media/message/${data.id}`;
  }
  if (data.media_url?.startsWith("http")) {
    return data.media_url;
  }
  return `/media/message/${data.id}`;
}

function getMessageDisplayName(data, fallback = "Arquivo") {
  const attachment = getPrimaryAttachment(data);
  return attachment?.original_filename || attachment?.safe_filename || data.content || fallback;
}

function updateSelectedMediaPreview() {
  const mediaInput = document.getElementById("mediaInput");
  const attachmentBox = document.getElementById("composerAttachment");
  const attachmentName = document.getElementById("composerAttachmentName");

  if (!attachmentBox || !attachmentName) return;

  const incomingFiles = Array.from(mediaInput?.files || []);
  if (incomingFiles.length) {
    const seen = new Set(selectedMediaFiles.map(file => `${file.name}:${file.size}:${file.lastModified}`));
    incomingFiles.forEach(file => {
      const key = `${file.name}:${file.size}:${file.lastModified}`;
      if (!seen.has(key)) {
        selectedMediaFiles.push(file);
        seen.add(key);
      }
    });
    mediaInput.value = "";
  }

  if (!selectedMediaFiles.length) {
    attachmentBox.classList.add("d-none");
    attachmentName.textContent = "";
    return;
  }

  const fileNames = selectedMediaFiles.map(file => file.name).join(" • ");
  attachmentName.textContent = selectedMediaFiles.length === 1
    ? `Anexado: ${fileNames}`
    : `${selectedMediaFiles.length} anexos: ${fileNames}`;
  attachmentBox.classList.remove("d-none");
}

function clearSelectedMediaFile() {
  const mediaInput = document.getElementById("mediaInput");
  if (mediaInput) {
    mediaInput.value = "";
  }
  selectedMediaFiles = [];
  updateSelectedMediaPreview();
}

async function uploadAndSendSelectedFiles(files, conversationId) {
  for (const file of files) {
    const formData = new FormData();
    formData.append("file", file);

    const uploadResponse = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });
    const uploadData = await uploadResponse.json().catch(() => ({}));
    if (!uploadResponse.ok) {
      throw new Error(uploadData.error || "Erro ao enviar arquivo.");
    }

    const messageResponse = await fetch("/api/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        conversation_id: conversationId,
        content: "",
        type:
          file.type.startsWith("image") ? "image" :
          file.type.startsWith("audio") ? "audio" :
          file.type.startsWith("video") ? "video" :
          "document",
        media_url: uploadData.media_path,
        original_filename: uploadData.original_filename || file.name,
        mime_type: uploadData.mime_type || file.type
      })
    });

    if (!messageResponse.ok) {
      const errorData = await messageResponse.json().catch(() => ({}));
      throw new Error(errorData.error || "Erro ao enviar mídia.");
    }
  }
}

function isAttachmentMessage(data) {
  return ["document", "image", "audio", "video"].includes(data?.type);
}

function renderAttachmentSelector(data) {
  if (!isAttachmentMessage(data)) {
    return "";
  }

  const checked = selectedAttachmentMessageIds.has(data.id) ? "checked" : "";
  return `
    <label class="attachment-selector">
      <input type="checkbox" class="attachment-checkbox" data-message-id="${data.id}" ${checked}>
      Selecionar
    </label>
  `;
}

function updateAttachmentBulkActions() {
  const btn = document.getElementById("downloadSelectedAttachmentsBtn");
  const toggleBtn = document.getElementById("toggleAllAttachmentsBtn");
  if (!btn || !toggleBtn) return;

  const count = selectedAttachmentMessageIds.size;
  const total = currentConversationAttachmentIds.length;

  if (!currentConversationId || total === 0) {
    toggleBtn.classList.add("d-none");
    toggleBtn.textContent = "Selecionar todos";
    btn.classList.add("d-none");
    btn.textContent = "Baixar selecionados (.zip)";
    return;
  }

  toggleBtn.classList.remove("d-none");
  toggleBtn.textContent = count === total ? "Limpar selecao" : "Selecionar todos";

  if (count === 0) {
    btn.classList.add("d-none");
    btn.textContent = "Baixar selecionados (.zip)";
    return;
  }

  btn.classList.remove("d-none");
  btn.textContent = `Baixar ${count} selecionado(s) (.zip)`;
}

function toggleAttachmentSelection(messageId, checked) {
  if (checked) {
    selectedAttachmentMessageIds.add(messageId);
  } else {
    selectedAttachmentMessageIds.delete(messageId);
  }
  updateAttachmentBulkActions();
}

function clearAttachmentSelection() {
  selectedAttachmentMessageIds = new Set();
  document.querySelectorAll(".attachment-checkbox").forEach(checkbox => {
    checkbox.checked = false;
  });
  updateAttachmentBulkActions();
}

function downloadSelectedAttachments() {
  if (!currentConversationId || selectedAttachmentMessageIds.size === 0) return;

  fetch(`/api/conversations/${currentConversationId}/attachments/download-zip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message_ids: Array.from(selectedAttachmentMessageIds),
    })
  })
    .then(async res => {
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Nao foi possivel gerar o arquivo compactado.");
      }
      const disposition = res.headers.get("Content-Disposition") || "";
      const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const basicMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
      const filename = utf8Match
        ? decodeURIComponent(utf8Match[1])
        : (basicMatch ? basicMatch[1] : `anexos_conversa_${currentConversationId}.zip`);
      const blob = await res.blob();
      return { blob, filename };
    })
    .then(({ blob, filename }) => {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      clearAttachmentSelection();
    })
    .catch(err => alert(err.message));
}

function toggleAllAttachmentsSelection() {
  if (!currentConversationAttachmentIds.length) return;

  const shouldSelectAll = selectedAttachmentMessageIds.size !== currentConversationAttachmentIds.length;
  selectedAttachmentMessageIds = shouldSelectAll
    ? new Set(currentConversationAttachmentIds)
    : new Set();

  document.querySelectorAll(".attachment-checkbox").forEach(checkbox => {
    checkbox.checked = shouldSelectAll;
  });

  updateAttachmentBulkActions();
}


function renderMessage(data) {
  const chat = document.getElementById("chatMessages");
  if (!chat) return;

  const messageDate = new Date(data.created_at);
  const currentDateString = messageDate.toDateString();

  // Separador de data
  if (lastRenderedDate !== currentDateString) {
    const separator = document.createElement("div");
    separator.className = "date-separator";
    separator.innerText = formatDateSeparator(data.created_at);
    chat.appendChild(separator);
    lastRenderedDate = currentDateString;
  }

  const div = document.createElement("div");

  div.className =
    data.sender === "client"
      ? "chat-bubble client"
      : "chat-bubble agent";

  // 🔥 Monta conteúdo baseado no tipo
  let messageHTML = "";

  switch (data.type) {

    case "image":
      const imageSrc = getMessageDownloadUrl(data);
      messageHTML =
        renderAttachmentSelector(data) +
        (data.content ? `<div>${data.content}</div>` : "") +
        `
          <div class="media-wrapper">
            <img src="${imageSrc}" class="chat-image"/>
            <a href="${imageSrc}" class="download-btn">
              ⬇ Baixar
            </a>
          </div>
        `;
      break;

    case "audio":
      const audioSrc = getMessageDownloadUrl(data);
      messageHTML =
        `
          ${renderAttachmentSelector(data)}
          <div class="media-wrapper">
            <audio controls src="${audioSrc}"></audio>
            <a href="${audioSrc}" class="download-btn">
              ⬇ Baixar
            </a>
          </div>
        `;
      break;

    case "video":
      const videoSrc = getMessageDownloadUrl(data);
      messageHTML =
        `
          ${renderAttachmentSelector(data)}
          <div class="media-wrapper">
            <video controls class="chat-video" src="${videoSrc}"></video>
            <a href="${videoSrc}" class="download-btn">
              ⬇ Baixar
            </a>
          </div>
        `;
      break;

    case "document":
      const documentSrc = getMessageDownloadUrl(data);
      const documentName = getMessageDisplayName(data, "Documento");
      messageHTML =
        `
          ${renderAttachmentSelector(data)}
          <div class="doc-bubble">
            📄 ${documentName}
            <br>
            <a href="${documentSrc}" class="download-btn" target="_blank" rel="noopener noreferrer">
              ⬇ Baixar
            </a>
          </div>
        `;
      break;

    default:
      if (data.sender === "agent" && data.content) {
        const parts = data.content.split(":\n");
        if (parts.length === 2) {
          const header = parts[0];
          const body = parts[1];
          messageHTML = `
            <div class="agent-prefix">${header}:</div>
            <div>${body}</div>
          `;
        } else {
          messageHTML = data.content;
        }
      } else {
        messageHTML = formatAgentMessage(data.content, data.sender);
      }
  }

  div.innerHTML = `
    <small class="message-time">
      ${messageDate.toLocaleTimeString("pt-BR", {
        hour: "2-digit",
        minute: "2-digit"
      })}
    </small>
    <div class="message-content">
      ${messageHTML}
    </div>
  `;

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  div.querySelector(".attachment-checkbox")?.addEventListener("change", event => {
    toggleAttachmentSelection(data.id, event.target.checked);
  });
}




function sendMessage() {  

  const input = document.getElementById("messageInput");
  const mediaInput = document.getElementById("mediaInput");

  const message = input.value.trim();
  const files = [...selectedMediaFiles];

  if (!currentConversationId) return;

  // 🔥 Se tiver arquivo → faz upload primeiro
  if (files.length) {
    uploadAndSendSelectedFiles(files, currentConversationId)
      .then(() => {
        input.value = "";
        clearSelectedMediaFile();
      })
      .catch(err => {
        alert(err.message);
      });
    return;
  }
  // 🔥 Se não tiver arquivo → envio normal de texto
  else if (message) {

    fetch("/api/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        conversation_id: currentConversationId,
        content: message,
        type: "text"
      })
    })
    .then(async res => {
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.error || "Você precisa assumir esta conversa.");
      }
    })
    .then(() => {
      input.value = "";
    })
    .catch(err => {
      const chat = document.getElementById("chatMessages");

      const warning = document.createElement("div");
      warning.className = "chat-warning";
      warning.innerText = err.message;

      chat.appendChild(warning);
      chat.scrollTop = chat.scrollHeight;

      setTimeout(() => {
        warning.remove();
      }, 3000);
    });
  }
}








// ============================
// NÃO LIDA
// ============================
function markUnread() {
  if (!currentConversationId) return;

  fetch(`/api/conversations/${currentConversationId}/unread`, {
    method: "POST"
  }).then(loadConversations);
}

// ============================
// SOCKET EVENTS
// ============================
socket.on("new_message", data => {

  // 🔥 SEMPRE ATUALIZA LISTA
  loadConversations();

  // 🔥 se estiver aberta, renderiza
  if (data.conversation_id == currentConversationId) {
    fetchConversation(currentConversationId, {
      markAsRead: false,
      silent: true,
    }).catch(() => {});
  }

});




socket.on("conversation_read", data => {
  const item = document.querySelector(
    `.conversation-item[data-conversation-id="${data.conversation_id}"]`
  );
  if (item) {
    item.querySelector(".conversation-avatar")?.classList.remove("avatar-unread");
  }
});


socket.on("conversation_unread", (data) => {
  const item = document.querySelector(
    `.conversation-item[data-conversation-id="${data.conversation_id}"]`
  );

  if (item) {
    item.querySelector(".conversation-avatar")?.classList.add("avatar-unread");
  } else {
    loadConversations();
  }
});


socket.on("conversation_assigned", (data) => {
  if (data.conversation_id === currentConversationId) {
    loadConversations();
  }
});

socket.on("presence_updated", () => {
  loadSectorOverview();
  loadUser();
});



function loadConversationHistory(conversationId) {
  fetch(`/api/conversations/${conversationId}/history`)
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById("conversationHistory");
      if (!container) return;

      container.innerHTML = "";

      data.forEach(item => {
        const div = document.createElement("div");
        div.className = "history-item";

        const date = new Date(item.created_at).toLocaleTimeString("pt-BR", {
          hour: "2-digit",
          minute: "2-digit"
        });

        let text = "";

        if (item.action_type === "created") {
          text = item.to_sector_name
            ? `Conversa criada em ${item.to_sector_name}`
            : "Conversa criada";
        } else if (item.action_type === "assigned") {
          text = `Assumida por ${item.user_name || "usuário"}`;
        } else if (item.action_type === "sector_changed") {
          const fromSector = item.from_sector_name || "origem";
          const toSector = item.to_sector_name || "destino";
          text = `Transferida de ${fromSector} para ${toSector}`;
        } else if (item.action_type === "sent_message") {
          text = `Respondida por ${item.user_name || "usuário"}`;
        } else {
          text = item.action_type;
        }

        div.innerHTML = `<strong>${date}</strong> - ${text}`;

        container.appendChild(div);
      });
    });
}


function formatDuration(seconds) {
  if (!seconds) return "Sem resposta";

  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours > 0) {
    return `${hours}h ${remainingMinutes}min`;
  }

  return `${minutes}min`;
}


function loadConversationMetrics(conversationId) {
  fetch(`/api/conversations/${conversationId}/metrics`)
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById("conversationMetrics");
      if (!container) return;

      const formatted = formatDuration(data.first_response_seconds);

      container.innerHTML = `
        <div class="metric-item">
          ⏱️ Primeira resposta: <strong>${formatted}</strong>
        </div>
      `;
    });
}




async function loadWhatsAppStatus() {
    const res = await fetch("/admin/whatsapp/status");
    const data = await res.json();

    const el = document.getElementById("whatsappStatus");

    if (data.status === "open") {
        el.innerHTML = `
            <span class="badge bg-success">
                WhatsApp conectado
            </span>
            <a href="/admin/whatsapp/disconnect" class="btn btn-sm btn-danger ms-2">
                Desconectar
            </a>
        `;
    } 
    else if (data.status === "connecting") {
        el.innerHTML = `
            <span class="badge bg-warning text-dark">
                Aguardando conexão...
            </span>
            <a href="/admin/whatsapp/qrcode" class="btn btn-sm btn-primary ms-2">
                Ver QR
            </a>
        `;
    } 
    else {
        el.innerHTML = `
            <span class="badge bg-secondary">
                WhatsApp desconectado
            </span>
            <a href="/admin/whatsapp/connect" class="btn btn-sm btn-success ms-2">
                Conectar
            </a>
        `;
    }
}

async function loadUser() {
    const res = await fetch("/api/me", {
        credentials: "include"
    });

    const user = await res.json();

    document.getElementById("userInfo").innerHTML = `
        👤 ${user.name} (${user.sector})
    `;
}


async function loadSectorOverview() {
    const res = await fetch("/api/sectors/overview", {
        credentials: "include"
    });

    if (!res.ok) {
        console.warn("Erro ao carregar setores:", res.status);
        return;
    }

    const data = await res.json();

    const container = document.getElementById("sectorList");
    container.innerHTML = "";

    data.forEach(s => {
        const div = document.createElement("div");

        div.innerHTML = `
            <strong>${s.name}</strong><br>
            👤 ${s.users.length} usuários<br>
            🟡 ${s.unassigned} fila<br>
            🟢 ${s.assigned} em atendimento
            <hr>
        `;

        container.appendChild(div);
    });
}

socket.on("conversation_moved", (data) => {
  loadConversations();
  loadSectorOverview(); // 🔥 FALTAVA ISSO

  if (data.conversation_id === currentConversationId) {
    currentConversationId = null;
    document.getElementById("chatMessages").innerHTML = "";
  }
});



async function loadUser() {
    const res = await fetch("/api/me", {
        credentials: "include"
    });

    const user = await res.json();

    const userInfo = document.getElementById("userInfo");
    if (userInfo) {
        userInfo.innerHTML = `
            <strong>${user.name}</strong><br>
            ${user.role || "AGENT"} • ${user.sector || "Sem setor"} • ${user.status}
        `;
    }

    const topbarLogo = document.getElementById("topbarLogo");
    if (topbarLogo && user.logo_url) {
        topbarLogo.innerHTML = `<img src="${user.logo_url}" alt="Logo da empresa">`;
    }

    const headerUserMeta = document.getElementById("headerUserMeta");
    if (headerUserMeta) {
        headerUserMeta.innerHTML = `
            <strong>${user.name}</strong>
            <span>${user.role || "AGENT"}</span>
        `;
    }

    renderCentralAiState(user.ai_enabled);
}


async function loadSectorOverview() {
    const res = await fetch("/api/sectors/overview", {
        credentials: "include"
    });

    if (!res.ok) {
        console.warn("Erro ao carregar setores:", res.status);
        return;
    }

    const data = await res.json();

    const container = document.getElementById("sectorList");
    const sidebarSectorCount = document.getElementById("sidebarSectorCount");
    if (sidebarSectorCount) {
        sidebarSectorCount.textContent = String(data.length);
    }
    container.innerHTML = "";

    data.forEach(s => {
        const div = document.createElement("div");
        const usersDetail = (s.users_detail || [])
            .map(u => `${u.name} (${u.status})`)
            .join("<br>");
        const routing = s.routing_metrics || {};
        const attention = routing.attention_level || "ok";
        const attentionLabel =
            attention === "critical" ? "Critico" :
            attention === "warning" ? "Atencao" :
            "Ok";
        const averageRouting =
            routing.average_routing_minutes != null
                ? `${routing.average_routing_minutes} min`
                : "sem historico";
        const longestOpen =
            routing.longest_open_minutes != null
                ? `${routing.longest_open_minutes} min`
                : "0 min";

        div.className = "sector-item sector-card";
        div.innerHTML = `
            <h4>${s.name}</h4>
            <div class="sector-stats">
                <div class="sector-stat"><span>Atendentes on-line</span><strong>${s.online}</strong></div>
                <div class="sector-stat"><span>Fila</span><strong>${s.unassigned}</strong></div>
                <div class="sector-stat"><span>Em atendimento</span><strong>${s.assigned}</strong></div>
            </div>
            <div class="mt-2 small">Tempo médio: ${averageRouting}</div>
            <div class="small">Maior aberto: ${longestOpen}</div>
            <div class="small">Status: ${attentionLabel}</div>
            ${usersDetail ? `<div class="mt-2 small">${usersDetail}</div>` : ""}
        `;

        container.appendChild(div);
    });
}
