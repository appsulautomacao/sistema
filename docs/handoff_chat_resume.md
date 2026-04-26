# Handoff Chat Resume

Cole este resumo no proximo chat para retomar exatamente deste ponto.

```text
Estamos finalizando uma plataforma SaaS de atendimento WhatsApp com Flask + PostgreSQL + Socket.IO + Evolution API.

Estado atual do projeto:
- app principal roda pela estrutura nova `application/...` com entrypoint `run.py`
- rota pública `/planos` já existe e funciona
- painel Ops já existe com:
  - `/ops/clients`
  - `/ops/simulator`
  - `/ops/billing-events`
- webhook `/webhooks/pagseguro` já existe
- worker de billing já existe
- super admin por `SUPER_ADMIN_EMAILS` já existe
- bloqueio de cliente por plano `blocked` já existe
- login por tenant `/<slug>/login` já existe
- troca obrigatória de senha e onboarding já existem

Camada comercial/billing que foi implementada:
- modelos novos:
  - `BillingPlan`
  - `CheckoutSession`
  - `Subscription`
  - `PaymentTransaction`
- arquivo principal da lógica comercial:
  - `core/commercial_service.py`
- integração PagBank:
  - `core/pagbank_service.py`
- integração billing/webhook atualizada em:
  - `core/billing.py`
  - `core/billing_service.py`
- rotas comerciais:
  - `/planos`
  - `POST /checkout/start`
  - `/checkout/<public_token>`
  - `POST /checkout/<public_token>/pay`

Arquivos principais alterados:
- `models.py`
- `application/__init__.py`
- `application/routes/commercial.py`
- `application/routes/ops.py`
- `core/commercial_service.py`
- `core/pagbank_service.py`
- `core/billing.py`
- `core/billing_service.py`
- `templates/public/plans.html`
- `templates/public/checkout.html`
- `templates/ops/clients.html`
- `templates/ops/billing_events.html`
- `templates/base.html`

Migration criada:
- `migrations/versions/d9f0a1b2c3d4_add_commercial_billing_foundation.py`

Docs criadas:
- `docs/go_live_checklist.md`
- `docs/commercial_billing_architecture.md`
- `docs/pagbank_sandbox_activation.md`
- `.env.example`

O que já foi validado localmente:
- `/planos` responde 200
- plano temporário de teste `teste-5-reais` foi criado com valor de R$ 5,00
- checkout sandbox PagBank gerou link real com sucesso
- credencial PagBank funcionou
- problema de localhost foi contornado para geração do checkout

Link sandbox que chegou a ser gerado:
- o PagBank respondeu com link `PAY` válido, então a geração do checkout está funcionando

O que ainda NÃO foi validado ponta a ponta:
- webhook automático do PagBank para `/webhooks/pagseguro`
- criação automática de `PaymentTransaction`
- criação automática de `Subscription`
- provisionamento fim a fim após pagamento real em URL pública

Motivo:
- os testes foram feitos localmente em `localhost`, então o PagBank não consegue chamar o webhook da aplicação local

Situação atual do banco local:
- `CheckoutSession` do teste existe
- `external_checkout_id` foi salvo
- ainda não apareceu `PaymentTransaction`
- ainda não apareceu `Subscription`
- isso é esperado sem webhook público

Variáveis importantes no `.env`:
- `SECRET_KEY`
- `SUPER_ADMIN_EMAILS`
- `PLATFORM_BASE_URL`
- `PAGSEGURO_WEBHOOK_SECRET`
- `BILLING_WORKER_ENABLED=true`
- `BILLING_WORKER_INTERVAL_SECONDS=5`
- `PAGBANK_API_TOKEN`
- `PAGBANK_ENVIRONMENT=sandbox`
- `PAGBANK_API_BASE_URL=https://sandbox.api.pagseguro.com`
- `PAGBANK_SOFT_DESCRIPTOR=APPSUL`
- SMTP configurado

Atenção importante:
- houve exposição de segredos durante o trabalho, então recomendamos rotacionar:
  - `OPENAI_API_KEY`
  - `SMTP_PASSWORD`
  - `PAGSEGURO_WEBHOOK_SECRET`
  - qualquer token PagBank usado em prints/testes

Próximo passo quando voltar:
1. preparar VPS com URL pública
2. subir código atualizado
3. ajustar `.env` de produção/sandbox
4. rodar migration
5. subir containers
6. testar `/planos`
7. gerar checkout PagBank
8. pagar
9. validar webhook em `/ops/billing-events`
10. validar cliente criado em `/ops/clients`
11. validar login em `/<slug>/login`

Contexto importante:
- usar `run.py`, não `app.py` legado
- parte comercial está pronta
- o que falta é só validação final em ambiente público com webhook real
```
