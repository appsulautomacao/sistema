function adminEscapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function buscarConversas() {
  const client = document.getElementById("filterClient")?.value || "";
  const agent = document.getElementById("filterAgent")?.value || "";
  const date = document.getElementById("filterDate")?.value || "";
  const container = document.getElementById("conversationList");
  if (!container) return;

  container.innerHTML = `<div class="empty-state">Buscando conversas...</div>`;

  const params = new URLSearchParams({ client, agent, date });
  const res = await fetch(`/admin/api/conversations?${params.toString()}`);
  const data = await res.json();

  if (!Array.isArray(data) || data.length === 0) {
    container.innerHTML = `<div class="empty-state">Nenhuma conversa encontrada</div>`;
    return;
  }

  container.innerHTML = "";
  data.forEach(conv => {
    const div = document.createElement("div");
    div.className = "conversation-item";
    div.innerHTML = `
      <div class="result-item-content">
        <strong>${adminEscapeHtml(conv.client)}</strong>
        <span>${adminEscapeHtml(conv.agent)}</span><br>
        <small>${adminEscapeHtml(conv.last_message || "Sem mensagens")}</small><br>
        <small class="text-muted">${adminEscapeHtml(conv.date)}</small>
      </div>
    `;
    div.addEventListener("click", () => openConversation(conv.id));
    container.appendChild(div);
  });
}

function openConversation(id) {
  fetch(`/admin/conversations/${id}`)
    .then(res => res.json())
    .then(data => {
      const modal = document.getElementById("conversationModal");
      const title = document.getElementById("modalTitle");
      const container = document.getElementById("modalMessages");
      if (!modal || !title || !container) return;

      title.innerText = data?.conversation?.client || "Conversa";
      container.innerHTML = "";

      const messages = Array.isArray(data?.messages) ? data.messages : [];
      if (!messages.length) {
        container.innerHTML = `<div class="empty-state">Sem mensagens nesta conversa.</div>`;
      }

      messages.forEach(msg => {
        const div = document.createElement("div");
        div.className = `chat-message ${msg.from_me ? "sent" : "received"}`;
        div.innerHTML = `
          <div class="bubble">
            ${adminEscapeHtml(msg.content)}
            <div class="time">${adminEscapeHtml(msg.time)}</div>
          </div>
        `;
        container.appendChild(div);
      });

      modal.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
    })
    .catch(() => {
      alert("Nao foi possivel abrir a conversa.");
    });
}

function closeConversationModal() {
  const modal = document.getElementById("conversationModal");
  if (!modal) return;
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
}

function initAdminCharts(agentLabels, agentData, volumeLabels, volumeData) {
  if (typeof Chart !== "function") return;

  const agentCanvas = document.getElementById("agentChart");
  if (agentCanvas) {
    new Chart(agentCanvas, {
      type: "bar",
      data: {
        labels: agentLabels,
        datasets: [{
          label: "Atendimentos",
          data: agentData,
          backgroundColor: "#2563eb",
          borderRadius: 8,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });
  }

  const volumeCanvas = document.getElementById("volumeChart");
  if (volumeCanvas) {
    new Chart(volumeCanvas, {
      type: "line",
      data: {
        labels: volumeLabels,
        datasets: [{
          label: "Conversas",
          data: volumeData,
          borderColor: "#22c55e",
          backgroundColor: "rgba(34, 197, 94, 0.14)",
          tension: 0.35,
          fill: true,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });
  }
}

function refreshAdminWhatsappStatus() {
  const label = document.getElementById("adminWhatsappStatusLabel");
  const card = document.querySelector("[data-whatsapp-status-card]");
  if (!label) return;

  fetch("/admin/whatsapp/status")
    .then(res => res.json())
    .then(data => {
      const connected = data?.status === "open" || data?.instance?.state === "open";
      label.textContent = connected ? "Conectado" : "Desconectado";
      if (card) {
        card.classList.toggle("is-offline", !connected);
      }
    })
    .catch(() => {
      label.textContent = "Indisponivel";
      if (card) card.classList.add("is-offline");
    });
}

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    closeConversationModal();
  }
});

document.addEventListener("click", event => {
  const modal = document.getElementById("conversationModal");
  if (modal && event.target === modal) {
    closeConversationModal();
  }
});
