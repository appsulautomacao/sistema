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

function setAdminNavActive(link) {
  document.querySelectorAll(".admin-side-nav a").forEach(item => {
    item.classList.toggle("active", item === link);
  });
}

function showAdminHome() {
  const home = document.getElementById("adminDashboardHome");
  const panel = document.getElementById("adminDynamicPanel");
  const content = document.getElementById("adminDynamicContent");
  if (home) home.classList.remove("d-none");
  if (panel) panel.classList.add("d-none");
  if (content) content.innerHTML = `<div class="empty-state">Carregando...</div>`;
}

function extractEmbeddedContent(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  doc.querySelectorAll("nav.navbar, script, link[rel='stylesheet'], style").forEach(node => node.remove());
  const container = doc.querySelector(".container");
  return container ? container.innerHTML : doc.body.innerHTML;
}

function shouldEmbedAdminUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin
      && (
        parsed.pathname.startsWith("/admin/")
        || parsed.pathname === "/admin"
        || parsed.pathname === "/planos"
      )
      && !parsed.pathname.includes("/delete/")
      && !parsed.pathname.includes("/toggle/");
  } catch {
    return false;
  }
}

async function loadAdminPanel(url, title, link) {
  const home = document.getElementById("adminDashboardHome");
  const panel = document.getElementById("adminDynamicPanel");
  const content = document.getElementById("adminDynamicContent");
  const titleEl = document.getElementById("adminDynamicTitle");
  if (!panel || !content) {
    window.location.href = url;
    return;
  }

  setAdminNavActive(link);
  if (home) home.classList.add("d-none");
  panel.classList.remove("d-none");
  if (titleEl) titleEl.textContent = title || "Painel";
  content.innerHTML = `<div class="empty-state">Carregando...</div>`;

  try {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) throw new Error("Falha ao carregar conteudo");
    const html = await res.text();
    content.innerHTML = extractEmbeddedContent(html);
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    content.innerHTML = `
      <div class="empty-state">
        Nao foi possivel abrir esta area aqui. <a href="${url}">Abrir pagina completa</a>
      </div>
    `;
  }
}

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    closeConversationModal();
  }
});

document.addEventListener("click", event => {
  const homeTrigger = event.target.closest("[data-admin-home]");
  if (homeTrigger) {
    event.preventDefault();
    showAdminHome();
    setAdminNavActive(document.querySelector(".admin-side-nav a[data-admin-home]"));
    return;
  }

  const embeddedLink = event.target.closest("[data-admin-embed-url]");
  if (embeddedLink) {
    event.preventDefault();
    loadAdminPanel(
      embeddedLink.getAttribute("data-admin-embed-url"),
      embeddedLink.textContent.trim(),
      embeddedLink
    );
    return;
  }

  const dynamicPanelLink = event.target.closest("#adminDynamicContent a[href]");
  if (dynamicPanelLink && shouldEmbedAdminUrl(dynamicPanelLink.href)) {
    event.preventDefault();
    loadAdminPanel(
      dynamicPanelLink.getAttribute("href"),
      dynamicPanelLink.textContent.trim() || "Painel",
      document.querySelector(`.admin-side-nav a[data-admin-embed-url="${dynamicPanelLink.getAttribute("href")}"]`)
    );
    return;
  }

  const modal = document.getElementById("conversationModal");
  if (modal && event.target === modal) {
    closeConversationModal();
  }
});
