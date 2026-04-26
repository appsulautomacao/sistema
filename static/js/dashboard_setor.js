let currentConversationId = null;
let currentConversation = null;
let currentFilter = "all";
let conversationsCache = [];
let lastRenderedDate = null;
let conversationRequestToken = 0;
let selectedAttachmentMessageIds = new Set();
let currentConversationAttachmentIds = [];
let lastConversationRenderSignature = null;
let selectedMediaFiles = [];

const socket = io();

socket.on("connect", () => {
  socket.emit("join_company", { company_id: USER_COMPANY_ID });
  socket.emit("presence_heartbeat");
});

socket.on("new_message", data => {
  loadConversations();
  if (data.conversation_id == currentConversationId) {
    refreshOpenConversation();
  }
});

socket.on("conversation_moved", data => {
  loadConversations();
  loadTeamOverview();

  if (data.conversation_id === currentConversationId) {
    currentConversationId = null;
    currentConversation = null;
    resetOpenConversation();
  }
});

socket.on("conversation_read", () => loadConversations());
socket.on("conversation_unread", () => loadConversations());
socket.on("conversation_assigned", () => loadConversations());
socket.on("presence_updated", () => {
  loadUser();
  loadTeamOverview();
});

document.addEventListener("DOMContentLoaded", () => {
  bindActions();
  loadUser();
  loadSectors();
  loadConversations();
  loadTeamOverview();
  loadWhatsAppStatus();

  setInterval(() => {
    if (socket.connected) {
      socket.emit("presence_heartbeat");
    }
  }, 15000);

  setInterval(() => {
    loadConversations();
    if (currentConversationId) {
      refreshOpenConversation();
    }
  }, 3000);

  setInterval(loadWhatsAppStatus, 5000);
});

function bindActions() {
  document.getElementById("filterAll")?.addEventListener("click", () => setFilter("all"));
  document.getElementById("filterQueue")?.addEventListener("click", () => setFilter("queue"));
  document.getElementById("filterMine")?.addEventListener("click", () => setFilter("mine"));

  document.getElementById("conversationSearch")?.addEventListener("input", renderConversationList);
  document.getElementById("assignBtn")?.addEventListener("click", assignCurrentConversation);
  document.getElementById("toggleAllAttachmentsBtn")?.addEventListener("click", toggleAllAttachmentsSelection);
  document.getElementById("downloadSelectedAttachmentsBtn")?.addEventListener("click", downloadSelectedAttachments);
  document.getElementById("sendMessageBtn")?.addEventListener("click", sendMessage);
  document.getElementById("markUnread")?.addEventListener("click", markUnread);
  document.getElementById("sectorSelect")?.addEventListener("change", transferConversation);
  document.getElementById("removeAttachmentBtn")?.addEventListener("click", clearSelectedMediaFile);

  const input = document.getElementById("messageInput");
  const mediaInput = document.getElementById("mediaInput");
  if (input) {
    input.addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
  }

  if (mediaInput) {
    mediaInput.addEventListener("change", updateSelectedMediaPreview);
  }
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

    const uploadResponse = await fetch("/api/upload", { method: "POST", body: formData });
    const uploadData = await uploadResponse.json().catch(() => ({}));
    if (!uploadResponse.ok) {
      throw new Error(uploadData.error || "Erro ao enviar arquivo.");
    }

    const messageResponse = await fetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        content: "",
        type: file.type.startsWith("image") ? "image" :
          file.type.startsWith("audio") ? "audio" :
          file.type.startsWith("video") ? "video" : "document",
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

function setFilter(filter) {
  currentFilter = filter;

  ["filterAll", "filterQueue", "filterMine"].forEach(id => {
    document.getElementById(id)?.classList.remove("active");
  });

  if (filter === "all") document.getElementById("filterAll")?.classList.add("active");
  if (filter === "queue") document.getElementById("filterQueue")?.classList.add("active");
  if (filter === "mine") document.getElementById("filterMine")?.classList.add("active");

  renderConversationList();
}

function loadConversations() {
  fetch("/api/dashboard/conversations")
    .then(r => r.json())
    .then(data => {
      conversationsCache = Array.isArray(data) ? data : [];
      renderConversationList();
      renderSectorSummary();
    })
    .catch(err => console.error("Erro ao carregar conversas:", err));
}

function getFilteredConversations() {
  const search = (document.getElementById("conversationSearch")?.value || "").toLowerCase();

  return conversationsCache.filter(conversation => {
    if (currentFilter === "queue" && conversation.assigned_to) return false;
    if (currentFilter === "mine" && !conversation.is_mine) return false;

    const haystack = `${conversation.client_name || ""} ${conversation.client_phone || ""} ${conversation.last_message || ""}`.toLowerCase();
    return haystack.includes(search);
  });
}

function renderSectorSummary() {
  const container = document.getElementById("sectorSummary");
  if (!container) return;

  const total = conversationsCache.length;
  const queue = conversationsCache.filter(c => !c.assigned_to).length;
  const mine = conversationsCache.filter(c => c.is_mine).length;

  container.innerHTML = `
    <div><strong>${total}</strong> no setor</div>
    <div><strong>${queue}</strong> aguardando assunção</div>
    <div><strong>${mine}</strong> com você</div>
  `;
}

function renderConversationList() {
  const list = document.getElementById("conversationList");
  if (!list) return;

  const conversations = getFilteredConversations();
  list.innerHTML = "";

  if (!conversations.length) {
    list.innerHTML = `<div class="p-3 text-muted">Nenhuma conversa encontrada neste filtro.</div>`;
    return;
  }

  conversations.forEach(c => {
    const div = document.createElement("div");
    const ownershipClass = c.is_mine ? "conversation-active" : (!c.assigned_to ? "conversation-queue" : "");

    div.className = `conversation-item ${ownershipClass}`.trim();
    if (c.id === currentConversationId) {
      div.classList.add("conversation-active");
    }

    const ownershipLabel = c.is_mine
      ? "Com você"
      : c.assigned_to
        ? `Com ${c.user_name}`
        : "Aguardando";

    div.innerHTML = `
      <div class="conversation-avatar ${!c.is_read ? "avatar-unread" : ""}">
        ${(c.client_name || "?").charAt(0).toUpperCase()}
      </div>
      <div class="conversation-content">
        <div class="conversation-top">
          <strong>${c.client_name || c.client_phone}</strong>
          <small class="conversation-time">
            ${c.last_message_time ? new Date(c.last_message_time).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : ""}
          </small>
        </div>
        <div class="conversation-preview">${c.last_message || ""}</div>
        <div class="conversation-sector">
          <span class="sector-agent">${ownershipLabel}</span>
        </div>
      </div>
    `;

    div.onclick = () => openConversation(c.id);
    list.appendChild(div);
  });
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
  const { markAsRead = false } = options;
  const requestToken = ++conversationRequestToken;

  if (markAsRead) {
    fetch(`/api/conversations/${conversationId}/read`, { method: "POST" }).catch(() => {});
  }

  return fetch(`/api/conversations/${conversationId}`)
    .then(async res => {
      const data = await res.json();
      if (!res.ok) throw data;
      return data;
    })
    .then(data => {
      if (requestToken !== conversationRequestToken || conversationId != currentConversationId) {
        return null;
      }

      const summary = conversationsCache.find(item => item.id === conversationId) || {};
      currentConversation = { ...(currentConversation || {}), ...summary, ...data };
      const renderSignature = buildConversationRenderSignature(data.messages);
      const chat = document.getElementById("chatMessages");
      const shouldStickToBottom = markAsRead || isChatNearBottom(chat);

      document.getElementById("chatClient").innerText = data.client_name || "Conversa";
      if (renderSignature !== lastConversationRenderSignature) {
        renderConversationMessages(data.messages);
        lastConversationRenderSignature = renderSignature;
      }

      document.getElementById("conversationActions")?.classList.remove("d-none");
      updateConversationState();
      loadConversationHistory(conversationId);
      loadConversationMetrics(conversationId);

      if (chat && shouldStickToBottom) {
        chat.scrollTop = chat.scrollHeight;
      }

      return data;
    });
}

function openConversation(id) {
  if (currentConversationId) {
    socket.emit("leave_conversation", { conversation_id: currentConversationId });
  }

  currentConversationId = id;
  socket.emit("join_conversation", { conversation_id: id });
  fetchConversation(id, { markAsRead: true })
    .catch(err => {
      const assignedTo = err.assigned_to ? ` Esta conversa jÃ¡ estÃ¡ com ${err.assigned_to}.` : "";
      alert((err.error || "NÃ£o foi possÃ­vel abrir a conversa.") + assignedTo);
      currentConversationId = null;
      currentConversation = null;
      resetOpenConversation();
      loadConversations();
    });
  return;

  lastRenderedDate = null;

  fetch(`/api/conversations/${id}/read`, { method: "POST" }).catch(() => {});

  fetch(`/api/conversations/${id}`)
    .then(async res => {
      const data = await res.json();
      if (!res.ok) throw data;
      return data;
    })
    .then(data => {
      const summary = conversationsCache.find(item => item.id === id) || {};
      currentConversation = { ...summary, ...data };

      document.getElementById("chatClient").innerText = data.client_name || "Conversa";
      document.getElementById("chatMessages").innerHTML = "";
      lastRenderedDate = null;
      data.messages.forEach(renderMessage);

      document.getElementById("conversationActions")?.classList.remove("d-none");
      updateConversationState();
      loadConversationHistory(id);
      loadConversationMetrics(id);
    })
    .catch(err => {
      const assignedTo = err.assigned_to ? ` Esta conversa já está com ${err.assigned_to}.` : "";
      alert((err.error || "Não foi possível abrir a conversa.") + assignedTo);
      currentConversationId = null;
      currentConversation = null;
      resetOpenConversation();
      loadConversations();
    });
}

function refreshOpenConversation() {
  if (!currentConversationId) return;

  fetchConversation(currentConversationId)
    .catch(() => {});
  return;

  fetch(`/api/conversations/${currentConversationId}`)
    .then(async res => {
      const data = await res.json();
      if (!res.ok) throw data;
      return data;
    })
    .then(data => {
      currentConversation = { ...(currentConversation || {}), ...data };
      document.getElementById("chatMessages").innerHTML = "";
      lastRenderedDate = null;
      data.messages.forEach(renderMessage);
      updateConversationState();
      loadConversationHistory(currentConversationId);
      loadConversationMetrics(currentConversationId);
    })
    .catch(() => {});
}

function resetOpenConversation() {
  document.getElementById("chatMessages").innerHTML = "";
  document.getElementById("chatClient").innerText = "Selecione uma conversa";
  document.getElementById("chatOwnershipHint").innerText = "Assuma uma conversa para iniciar o atendimento.";
  document.getElementById("conversationActions")?.classList.add("d-none");
  document.getElementById("conversationHistory").innerHTML = "";
  document.getElementById("conversationMetrics").innerHTML = "";
  selectedAttachmentMessageIds = new Set();
  currentConversationAttachmentIds = [];
  lastConversationRenderSignature = null;
  updateAttachmentBulkActions();
  setComposerState(false);
}

function updateConversationState() {
  const hint = document.getElementById("chatOwnershipHint");
  const assignBtn = document.getElementById("assignBtn");

  if (!currentConversation) {
    setComposerState(false);
    return;
  }

  const isMine = currentConversation.assigned_to === USER_ID || currentConversation.is_mine;
  const isUnassigned = !currentConversation.assigned_to;

  if (isMine) {
    hint.innerText = "Conversa assumida por você. Atendimento liberado.";
    assignBtn.disabled = true;
    setComposerState(true);
  } else if (isUnassigned) {
    hint.innerText = "Conversa aguardando assunção. Assuma antes de responder.";
    assignBtn.disabled = false;
    setComposerState(false);
  } else {
    hint.innerText = `Conversa em atendimento por ${currentConversation.user_name || "outro atendente"}.`;
    assignBtn.disabled = true;
    setComposerState(false);
  }
}

function setComposerState(enabled) {
  const input = document.getElementById("messageInput");
  const sendBtn = document.getElementById("sendMessageBtn");

  input.disabled = !enabled;
  sendBtn.disabled = !enabled;
  input.placeholder = enabled
    ? "Digite sua resposta..."
    : "Assuma a conversa para responder...";
}

function assignCurrentConversation() {
  if (!currentConversationId) return;

  fetch(`/api/conversations/${currentConversationId}/assign`, { method: "POST" })
    .then(r => r.json().then(data => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) {
        alert(data.error || "Não foi possível assumir.");
        return;
      }

      if (currentConversation) {
        currentConversation.assigned_to = USER_ID;
        currentConversation.user_name = "Você";
        currentConversation.is_mine = true;
      }

      updateConversationState();
      loadConversations();
    });
}

function transferConversation(event) {
  if (!currentConversationId || !event.target.value) return;

  fetch(`/api/conversations/${currentConversationId}/sector`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sector_id: event.target.value })
  })
    .then(r => r.json().then(data => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok) {
        alert(data.error || "Não foi possível transferir.");
        event.target.value = "";
        return;
      }

      currentConversation = null;
      currentConversationId = null;
      resetOpenConversation();
      event.target.value = "";
      loadConversations();
      loadTeamOverview();
    });
}

function sendMessage() {
  const input = document.getElementById("messageInput");
  const mediaInput = document.getElementById("mediaInput");
  const message = input.value.trim();
  const files = [...selectedMediaFiles];

  if (!currentConversationId) return;

  if (files.length) {
    uploadAndSendSelectedFiles(files, currentConversationId)
      .then(() => {
        input.value = "";
        clearSelectedMediaFile();
      })
      .catch(err => alert(err.message));
    return;
  }

  if (!message) return;

  fetch("/api/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
      input.value = "";
      loadConversations();
    })
    .catch(err => alert(err.message));
}

function markUnread() {
  if (!currentConversationId) return;
  fetch(`/api/conversations/${currentConversationId}/unread`, { method: "POST" })
    .then(() => loadConversations());
}

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

  if (lastRenderedDate !== currentDateString) {
    const separator = document.createElement("div");
    separator.className = "date-separator";
    separator.innerText = formatDateSeparator(data.created_at);
    chat.appendChild(separator);
    lastRenderedDate = currentDateString;
  }

  const div = document.createElement("div");
  div.className = data.sender === "client" ? "chat-bubble client" : "chat-bubble agent";

  let messageHTML = data.content || "";
  switch (data.type) {
    case "image": {
      const imageSrc = getMessageDownloadUrl(data);
      messageHTML = `
        ${renderAttachmentSelector(data)}
        ${(data.content ? `<div>${data.content}</div>` : "")}
        <div class="media-wrapper"><img src="${imageSrc}" class="chat-image"/></div>
      `;
      break;
    }

    case "audio": {
      const audioSrc = getMessageDownloadUrl(data);
      messageHTML = `
        ${renderAttachmentSelector(data)}
        <div class="media-wrapper">
          <audio controls src="${audioSrc}"></audio>
          <a href="${audioSrc}" class="download-btn" target="_blank" rel="noopener noreferrer">
            Baixar audio
          </a>
        </div>
      `;
      break;
    }

    case "video": {
      const videoSrc = getMessageDownloadUrl(data);
      messageHTML = `
        ${renderAttachmentSelector(data)}
        ${(data.content ? `<div>${data.content}</div>` : "")}
        <div class="media-wrapper">
          <video controls class="chat-video" src="${videoSrc}"></video>
          <a href="${videoSrc}" class="download-btn" target="_blank" rel="noopener noreferrer">
            Baixar video
          </a>
        </div>
      `;
      break;
    }

    case "document": {
      const documentSrc = getMessageDownloadUrl(data);
      const documentName = getMessageDisplayName(data, "Documento");
      messageHTML = `
        ${renderAttachmentSelector(data)}
        <div class="doc-bubble">
          ${documentName}
          <br>
          <a href="${documentSrc}" class="download-btn" target="_blank" rel="noopener noreferrer">
            Baixar documento
          </a>
        </div>
      `;
      break;
    }
  }

  div.innerHTML = `
    <small class="message-time">${messageDate.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</small>
    <div class="message-content">${messageHTML}</div>
  `;

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;

  div.querySelector(".attachment-checkbox")?.addEventListener("change", event => {
    toggleAttachmentSelection(data.id, event.target.checked);
  });
}

function loadConversationHistory(conversationId) {
  fetch(`/api/conversations/${conversationId}/history`)
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById("conversationHistory");
      container.innerHTML = "";

      data.forEach(item => {
        const div = document.createElement("div");
        div.className = "history-item";
        const date = new Date(item.created_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

        let text = item.action_type;
        if (item.action_type === "assigned") text = `Assumida por ${item.user_name || "usuário"}`;
        if (item.action_type === "sector_changed") text = `Transferida de ${item.from_sector_name || "origem"} para ${item.to_sector_name || "destino"}`;
        if (item.action_type === "sent_message") text = `Respondida por ${item.user_name || "usuário"}`;
        if (item.action_type === "created") text = `Conversa criada em ${item.to_sector_name || "setor"}`;

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
  if (hours > 0) return `${hours}h ${remainingMinutes}min`;
  return `${minutes}min`;
}

function loadConversationMetrics(conversationId) {
  fetch(`/api/conversations/${conversationId}/metrics`)
    .then(r => r.json())
    .then(data => {
      const container = document.getElementById("conversationMetrics");
      container.innerHTML = `<div class="metric-item">Primeira resposta: <strong>${formatDuration(data.first_response_seconds)}</strong></div>`;
    });
}

function loadSectors() {
  fetch("/api/sectors")
    .then(r => r.json())
    .then(sectors => {
      const select = document.getElementById("sectorSelect");
      if (!select) return;

      select.innerHTML = `<option value="">Transferir para setor...</option>`;
      sectors
        .filter(sector => sector.id !== USER_SECTOR_ID)
        .forEach(sector => {
          select.innerHTML += `<option value="${sector.id}">${sector.name}</option>`;
        });
    });
}

function loadUser() {
  fetch("/api/me", { credentials: "include" })
    .then(r => r.json())
    .then(user => {
      document.getElementById("userInfo").innerHTML = `${user.name} (${user.sector}) - ${user.status}`;
    });
}

function loadTeamOverview() {
  fetch("/api/sectors/overview", { credentials: "include" })
    .then(r => r.json())
    .then(data => {
      const sector = (data || []).find(item => item.id === USER_SECTOR_ID);
      const container = document.getElementById("teamOverview");
      if (!container || !sector) return;

      const users = (sector.users_detail || []).map(user => `${user.name} (${user.status})`).join("<br>");
      container.innerHTML = `
        <div><strong>${sector.name}</strong></div>
        <div>${sector.online} online</div>
        <div>${sector.unassigned} aguardando</div>
        <div>${sector.assigned} em atendimento</div>
        <hr>
        <div class="small">${users || "Sem equipe"}</div>
      `;
    });
}

async function loadWhatsAppStatus() {
  const res = await fetch("/api/whatsapp/status");
  const data = await res.json();
  const el = document.getElementById("whatsappStatus");
  if (!el) return;

  if (data.status === "open") {
    el.innerHTML = `<span class="badge bg-success">WhatsApp conectado</span>`;
  } else if (data.status === "connecting") {
    el.innerHTML = `<span class="badge bg-warning text-dark">Aguardando conexão</span>`;
  } else {
    el.innerHTML = `<span class="badge bg-secondary">WhatsApp desconectado</span>`;
  }
}
