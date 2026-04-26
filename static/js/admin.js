console.log("admin.js carregado");
async function buscarConversas() {

    const client = document.getElementById("filterClient").value;
    const agent = document.getElementById("filterAgent").value;
    const date = document.getElementById("filterDate").value;

    const res = await fetch(`/admin/api/conversations?client=${client}&agent=${agent}&date=${date}`);
    const data = await res.json();

    const container = document.getElementById("conversationList");
    container.innerHTML = "";

    if (data.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                Nenhuma conversa encontrada
            </div>
        `;
        return;
    }

    data.forEach(conv => {

        const div = document.createElement("div");

        div.className = "conversation-item";

        // 🔥 AQUI É O PONTO QUE VOCÊ NÃO TINHA
        div.innerHTML = `
            <div onclick="openConversation(${conv.id})">
                <strong>${conv.client}</strong> (${conv.agent})<br>
                <small>${conv.last_message}</small><br>
                <small class="text-muted">${conv.date}</small>
            </div>
        `;

        container.appendChild(div);
    });
}


function openConversation(id) {
    fetch(`/admin/conversations/${id}`)
        .then(res => res.json())
        .then(data => {
            console.log(data);
            // depois vamos ligar com modal
        });
}



// 📊 GRÁFICO
function initChart(labels, data) {
    new Chart(document.getElementById('agentChart'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Atendimentos',
                data: data,
            }]
        }
    });
}

// 🔎 BUSCA
async function buscarConversas() {

    const client = document.getElementById("filterClient").value;
    const agent = document.getElementById("filterAgent").value;
    const date = document.getElementById("filterDate").value;

    const res = await fetch(`/admin/api/conversations?client=${client}&agent=${agent}&date=${date}`);
    const data = await res.json();

    const container = document.getElementById("conversationList");
    container.innerHTML = "";

    if (data.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                Nenhuma conversa encontrada
            </div>
        `;
        return;
    }

    data.forEach(conv => {

        const div = document.createElement("div");

        div.className = "conversation-item";

        div.innerHTML = `
            <strong>${conv.client}</strong> (${conv.agent})<br>
            <small>${conv.last_message}</small><br>
            <small class="text-muted">${conv.date}</small>
        `;

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

            title.innerText = data.conversation.client;

            container.innerHTML = "";

            data.messages.forEach(msg => {

                const div = document.createElement("div");

                div.classList.add("chat-message");

                if (msg.from_me) {
                    div.classList.add("sent");
                } else {
                    div.classList.add("received");
                }

                div.innerHTML = `
                    <div class="bubble">
                        ${msg.content}
                        <div class="time">${msg.time}</div>
                    </div>
                `;

                container.appendChild(div);
            });

            modal.style.display = "block";
        });
}

function openConversation(id) {
    console.log("clicou na conversa:", id);
}