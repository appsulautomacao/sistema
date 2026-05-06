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

function renderWhatsappStatus(panel, status) {
  const box = panel?.querySelector("[data-whatsapp-status-box]");
  if (!box) return;

  if (status === "open") {
    box.innerHTML = `<div class="alert alert-success mb-0">WhatsApp conectado e pronto para atender.</div>`;
    return;
  }

  if (status === "error") {
    box.innerHTML = `<div class="alert alert-danger mb-0">Nao foi possivel consultar o status agora.</div>`;
    return;
  }

  box.innerHTML = `<div class="alert alert-warning mb-0">WhatsApp ainda nao conectado.</div>`;
}

async function loadWhatsappQr(panel) {
  const area = panel.querySelector("[data-whatsapp-qr-area]");
  const button = panel.querySelector("[data-whatsapp-connect-button]");
  if (!area || !button) return;

  if (!panel.dataset.authorizedNumber) {
    area.innerHTML = `<div class="alert alert-warning mb-0">Salve primeiro o WhatsApp autorizado da empresa.</div>`;
    return;
  }

  button.disabled = true;
  button.textContent = "Gerando QR Code...";
  area.innerHTML = `<p class="text-muted mb-0">Criando conexao segura com o WhatsApp...</p>`;

  try {
    const connectRes = await fetch("/api/whatsapp/connect", {
      method: "POST",
      credentials: "same-origin"
    });
    const connectData = await connectRes.json().catch(() => ({}));
    if (!connectRes.ok || connectData.error) {
      throw new Error(connectData.error || "Nao foi possivel iniciar a conexao.");
    }

    const qrRes = await fetch("/api/whatsapp/qrcode", { credentials: "same-origin" });
    const qrData = await qrRes.json();
    if (!qrRes.ok || qrData.error) {
      throw new Error(qrData.error || "Nao foi possivel gerar o QR Code.");
    }

    if (qrData.qr) {
      area.innerHTML = `
        <div class="whatsapp-qr-card">
          <img src="${qrData.qr}" alt="QR Code para conectar o WhatsApp">
          <p>Abra o WhatsApp no celular da empresa, toque em aparelhos conectados e escaneie este QR Code.</p>
        </div>
      `;
      button.textContent = "Gerar novo QR Code";
      return;
    }

    area.innerHTML = `<div class="alert alert-warning mb-0">QR Code ainda nao disponivel. Tente novamente em alguns segundos.</div>`;
    button.textContent = "Tentar novamente";
  } catch (error) {
    area.innerHTML = `<div class="alert alert-danger mb-0">${adminEscapeHtml(error.message || "Erro ao conectar WhatsApp.")}</div>`;
    button.textContent = "Tentar novamente";
  } finally {
    button.disabled = false;
  }
}

function initAdminWhatsappPanel(root = document) {
  const panel = root.querySelector("[data-whatsapp-panel]");
  if (!panel || panel.dataset.initialized === "1") return;
  panel.dataset.initialized = "1";

  const button = panel.querySelector("[data-whatsapp-connect-button]");
  if (button) {
    button.addEventListener("click", () => loadWhatsappQr(panel));
  }

  const authorizedForm = panel.querySelector("[data-authorized-whatsapp-form]");
  if (authorizedForm) {
    authorizedForm.addEventListener("submit", async event => {
      event.preventDefault();
      const formData = new FormData(authorizedForm);
      const submitButton = authorizedForm.querySelector("button");
      if (submitButton) submitButton.disabled = true;

      try {
        const res = await fetch("/api/whatsapp/authorized-number", {
          method: "POST",
          credentials: "same-origin",
          body: formData
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Nao foi possivel salvar o numero.");
        }

        panel.dataset.authorizedNumber = data.number;
        const box = panel.querySelector(".authorized-whatsapp-box");
        if (box) {
          box.innerHTML = `
            <strong>WhatsApp autorizado</strong>
            <p class="mb-0">Este painel so pode conectar o numero <code>${adminEscapeHtml(data.number)}</code>.</p>
          `;
        }
        if (button) button.disabled = false;
      } catch (error) {
        const box = panel.querySelector(".authorized-whatsapp-box");
        if (box) {
          box.insertAdjacentHTML("beforeend", `<div class="alert alert-danger mt-2 mb-0">${adminEscapeHtml(error.message || "Erro ao salvar numero.")}</div>`);
        }
      } finally {
        if (submitButton) submitButton.disabled = false;
      }
    });
  }

  const pollStatus = async () => {
    try {
      const res = await fetch("/api/whatsapp/status", { credentials: "same-origin" });
      const data = await res.json();
      renderWhatsappStatus(panel, data.status);
      if (data.status === "blocked_wrong_number") {
        const area = panel.querySelector("[data-whatsapp-qr-area]");
        if (area) {
          area.innerHTML = `
            <div class="alert alert-danger mb-0">
              O numero conectado nao e o WhatsApp autorizado desta empresa. A conexao foi bloqueada.
            </div>
          `;
        }
        return;
      }
      if (data.status === "open") {
        const area = panel.querySelector("[data-whatsapp-qr-area]");
        const actions = panel.querySelector(".whatsapp-actions");
        if (area) area.innerHTML = `<p class="text-muted mb-0">Conexao confirmada. Sua central ja pode receber mensagens.</p>`;
        if (actions) {
          const centralLink = panel.dataset.canOpenCentral === "1"
            ? `<a class="btn btn-outline-secondary" href="/dashboard">Ir para a central</a>`
            : "";
          actions.innerHTML = `
            <a class="btn btn-outline-danger" href="/admin/whatsapp/disconnect">Desconectar WhatsApp</a>
            ${centralLink}
          `;
        }
      }
    } catch {
      renderWhatsappStatus(panel, "error");
    }
  };

  pollStatus();
  panel._whatsappStatusTimer = window.setInterval(pollStatus, 5000);
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
      && !parsed.pathname.includes("/toggle/")
      && !parsed.pathname.includes("/disconnect");
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
    initAdminWhatsappPanel(content);
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

document.addEventListener("DOMContentLoaded", () => {
  initAdminWhatsappPanel(document);
});
