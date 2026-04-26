# Comercial e Billing

Esta etapa fecha a camada comercial que faltava entre a escolha do plano e o webhook aprovado.

## Fluxo final

1. Cliente acessa `/planos`.
2. Escolhe plano, forma de pagamento e parcelamento.
3. O sistema cria uma `checkout_session`.
4. O sistema cria o checkout hospedado no PagBank usando `reference_id = public_token`.
5. O pagamento aprovado chega em `/webhooks/pagseguro`.
6. O billing:
   - deduplica o evento
   - identifica a sessao de checkout
   - provisiona a empresa
   - cria assinatura
   - cria transacao
   - ativa a empresa
7. Ops acompanha em `/ops/billing-events` e `/ops/clients`.

## Entidades novas

- `billing_plans`
  - catalogo comercial dos planos
  - suporta mensal, anual e pagamento unico
  - controla metodos aceitos e parcelamento maximo

- `checkout_sessions`
  - guarda a intencao comercial do cliente
  - registra plano, empresa, responsavel, metodo e parcelas
  - gera `public_token` para rastrear o checkout

- `subscriptions`
  - representa a assinatura ativa da empresa
  - liga empresa, plano e periodo vigente

- `payment_transactions`
  - registra a cobranca liquidada
  - liga evento do webhook, sessao de checkout e assinatura

## Como o webhook identifica o checkout

O identificador principal enviado ao PagBank e `reference_id`, preenchido com o `public_token` da sessao.

Quando o webhook retorna, o sistema tenta localizar o checkout por:

1. `checkout_session_token`, se existir no payload
2. `reference` ou `reference_id`, que aponta para o `public_token`

Depois disso o plano e os dados comerciais sao recuperados da sessao local.

## Planos padrao seedados pelo sistema

- `starter-monthly`
- `pro-monthly`
- `pro-yearly`
- `implantacao-avista`

Esses planos sao criados automaticamente quando a camada comercial e acessada.

## Limite desta entrega

Esta entrega fecha a arquitetura interna e o fluxo de dados do comercial.

Ainda depende da integracao final com o checkout real do gateway para:

- lidar com recorrencia nativa do provedor

## Variaveis de ambiente novas

```env
PAGBANK_API_TOKEN=seu_token_pagbank
PAGBANK_ENVIRONMENT=sandbox
PAGBANK_API_BASE_URL=https://sandbox.api.pagseguro.com
PAGBANK_SOFT_DESCRIPTOR=APPSUL
PLATFORM_BASE_URL=https://app.appsul.com.br
```

Observacoes:

- Se `PAGBANK_API_BASE_URL` nao for informado, o sistema escolhe sandbox ou producao com base em `PAGBANK_ENVIRONMENT`.
- O webhook continua entrando em `/webhooks/pagseguro`.
- O checkout real pode ser gerado pela rota `POST /checkout/<public_token>/pay`.

## Recomendacao arquitetural

Para acelerar a operacao comercial, a estrategia ideal e:

1. manter a escolha de plano no seu sistema
2. usar checkout hospedado do gateway
3. enviar `checkout_session_token` e `plan_code` como metadata
4. deixar o webhook ativar a assinatura

Assim voce controla produto e ativacao sem assumir a complexidade de PCI, antifraude e parcelamento manual.
