# Ativacao Sandbox PagBank

Este roteiro fecha a ativacao da camada comercial no ambiente sandbox.

## 1. Preparar variaveis

Preencha no `.env`:

```env
SECRET_KEY=troque-por-uma-chave-forte
PLATFORM_BASE_URL=https://app.appsul.com.br
PAGSEGURO_WEBHOOK_SECRET=troque-por-um-segredo-forte

PAGBANK_API_TOKEN=seu-token-pagbank
PAGBANK_ENVIRONMENT=sandbox
PAGBANK_API_BASE_URL=https://sandbox.api.pagseguro.com
PAGBANK_SOFT_DESCRIPTOR=APPSUL
```

## 2. Aplicar migration

No ambiente em que o banco `postgres_app` esta acessivel:

```powershell
$env:FLASK_APP='run.py'
flask db upgrade
```

Se quiser conferir o head antes:

```powershell
$env:FLASK_APP='run.py'
flask db heads
```

Head esperado:

```text
d9f0a1b2c3d4
```

## 3. Reiniciar a aplicacao

Exemplo com Docker Compose:

```powershell
docker-compose down
docker-compose up --build
```

## 4. Criar checkout sandbox

Abra:

```text
/planos
```

Fluxo:

1. Escolher o plano.
2. Informar empresa, admin, e-mail e forma de pagamento.
3. Criar a sessao.
4. Na tela da sessao, clicar em `Gerar checkout PagBank`.
5. Confirmar que houve redirecionamento para o link `PAY` do PagBank.

## 5. Confirmar o retorno no sistema

Depois da aprovacao no sandbox, validar:

1. `/ops/billing-events`
   - evento recebido
   - plano preenchido
   - metodo de pagamento preenchido
   - status processado
2. `/ops/clients`
   - cliente criado
   - assinatura criada
   - pagamento contabilizado
3. `/<slug>/login`
   - credenciais provisórias
   - troca de senha
   - onboarding

## 6. Rotas envolvidas

- `/planos`
- `/checkout/<public_token>`
- `POST /checkout/<public_token>/pay`
- `POST /webhooks/pagseguro`
- `/ops/clients`
- `/ops/billing-events`

## 7. Observacoes importantes

- O sistema usa `reference_id = public_token` para correlacionar o checkout com o webhook.
- Se o webhook nao trouxer dados comerciais completos, o sistema tenta completar pela `checkout_session`.
- Checkout recorrente no PagBank, segundo a documentacao oficial atual, esta disponivel apenas para cartao de credito.
- Parcelamento e controlado no checkout criado pelo sistema, usando o limite configurado no plano.
