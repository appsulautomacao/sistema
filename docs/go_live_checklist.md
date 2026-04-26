# Go-Live Checklist

Este documento resume a validacao final do fluxo de provisionamento SaaS, painel Ops e webhook do PagSeguro.

## 1. Variaveis de ambiente obrigatorias

Confirme no `.env`:

```env
SUPER_ADMIN_EMAILS=seuemail@dominio.com
PAGSEGURO_WEBHOOK_SECRET=chave_forte
PLATFORM_BASE_URL=https://app.appsul.com.br
BILLING_WORKER_ENABLED=true
BILLING_WORKER_INTERVAL_SECONDS=5

SMTP_HOST=smtp.seudominio.com
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=senha
SMTP_FROM=naoresponder@seudominio.com
```

Observacoes:

- `SUPER_ADMIN_EMAILS` aceita mais de um e-mail separado por virgula.
- O webhook do PagSeguro exige o header `X-PagSeguro-Webhook-Secret` quando `PAGSEGURO_WEBHOOK_SECRET` estiver definido.
- O worker de billing roda em background ao subir a aplicacao.
- O envio de e-mail depende de `SMTP_HOST` e `SMTP_FROM`. Usuario e senha so sao usados se informados.

## 2. Reinicio da aplicacao

Depois de alterar o `.env`, reinicie a app para carregar as novas variaveis.

Exemplos usados neste projeto:

```powershell
docker-compose down
docker-compose up --build
```

Ou, se estiver rodando containers ja criados:

```powershell
docker-compose restart
```

## 3. Validacao no painel Ops

Login com um usuario cujo e-mail esteja em `SUPER_ADMIN_EMAILS`.

Rotas principais:

- `/ops/clients`
- `/ops/simulator`
- `/ops/billing-events`

Checklist:

1. Abrir `/ops/clients` e confirmar acesso como super admin.
2. Abrir `/ops/simulator`.
3. Simular pagamento aprovado.
4. Validar em `/ops/clients`:
   - cliente criado
   - slug gerado
   - link de login exibido
   - senha temporaria exibida
5. Abrir `/<slug>/login` com as credenciais geradas.
6. Validar troca obrigatoria de senha no primeiro acesso.
7. Validar onboarding inicial do cliente.
8. Voltar ao Ops, bloquear o cliente e confirmar que o login passa a ser negado.

## 4. Validacao do webhook PagSeguro

Endpoint:

```text
POST /webhooks/pagseguro
```

Header exigido:

```text
X-PagSeguro-Webhook-Secret: <valor do .env>
```

Resultado esperado:

- resposta inicial do webhook: `queued`
- worker ou reprocessamento manual leva o evento para `processed`
- evento visivel em `/ops/billing-events`

### Exemplo PowerShell

```powershell
$headers = @{
  "X-PagSeguro-Webhook-Secret" = "chave_forte"
  "Content-Type" = "application/json"
}

$body = @{
  id = "evt_go_live_001"
  type = "payment.paid"
  status = "PAID"
  metadata = @{
    company_name = "Cliente Go Live"
    admin_name = "Admin Cliente"
    admin_email = "admin.cliente@dominio.com"
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method POST `
  -Uri "https://app.appsul.com.br/webhooks/pagseguro" `
  -Headers $headers `
  -Body $body
```

### O que verificar depois do POST

1. Abrir `/ops/billing-events`.
2. Confirmar que o evento entrou com provider `pagseguro`.
3. Confirmar transicao de fila:
   - `queued`
   - `processed`
4. Se necessario, usar o botao de reprocessamento na tela de billing events.
5. Confirmar que o cliente apareceu em `/ops/clients`.

## 5. Fluxo real de aceite

O fluxo esta pronto quando todos os itens abaixo estiverem ok:

1. Super admin acessa `/ops`.
2. Simulador cria cliente com slug e senha temporaria.
3. Webhook real do PagSeguro entra autenticado por secret.
4. Evento vai para billing queue e e processado.
5. Cliente consegue logar em `/<slug>/login`.
6. Primeiro acesso obriga troca de senha.
7. Onboarding conclui normalmente.
8. Bloqueio no Ops derruba o acesso do cliente bloqueado.

## 6. Observacoes operacionais

- Se um evento chegar duplicado, o sistema responde `duplicate_ignored`.
- Se o pagamento nao estiver aprovado, o evento e marcado como `ignored_payment_not_approved`.
- Se o e-mail do admin ja existir, o evento nao provisiona novo cliente.
- O simulador processa o evento na hora e expõe a senha temporaria na tela de Ops.
- O worker usa `PLATFORM_BASE_URL` como base para montar links fora do request atual.
