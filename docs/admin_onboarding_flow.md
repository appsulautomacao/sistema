# Fluxo de Onboarding do Cliente (Admin)

## Objetivo
Garantir um fluxo previsivel desde a compra do sistema ate a operacao do administrador no painel.

## Sequencia recomendada
1. Compra confirmada no comercial/financeiro.
2. Provisionamento do tenant:
   - criar `Company`;
   - criar `CompanySettings`;
   - criar usuario `ADMIN` com senha temporaria.
3. Envio de e-mail de boas-vindas para o admin:
   - login (`/{slug}/login`);
   - usuario;
   - senha temporaria;
   - orientacao de primeiro acesso.
4. Primeiro login do admin:
   - redirecionar para `/onboarding/password`.
5. Troca obrigatoria de senha no primeiro acesso.
6. Step 1:
   - validar dados da empresa (nome/documento).
7. Step 2:
   - conectar WhatsApp e aguardar status `open`.
8. Finalizar onboarding:
   - marcar `company.onboarding_completed = True`.
9. Admin segue para configuracoes:
   - SLA;
   - horarios;
   - setores;
   - usuarios;
   - IA (classificador/assistente/RAG).
10. Operacao:
   - time entra no dashboard de atendimento.

## Melhorias aplicadas no codigo
- Rotas de onboarding e WhatsApp protegidas para `ADMIN`.
- Correcao de check de conexao no `step2_whatsapp.html` (status `open`).
- `seed.py` agora suporta provisionamento de novo cliente:
  - `python seed.py provision-client --company-name "..."`
  - opcional de envio de e-mail via SMTP: `--send-email`.
- Login por tenant habilitado:
  - `/{company_slug}/login`
- Branding por empresa:
  - `logo_url`
  - `primary_color`
  - `slug`

## Variaveis de ambiente para envio SMTP (opcional)
- `SMTP_HOST`
- `SMTP_PORT` (padrao 587)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_USE_TLS` (`true`/`false`)
