# Arquitetura de IA

## Objetivo

A camada de IA da plataforma deve evoluir em etapas, sem espalhar chamadas de modelo por rotas, webhooks e telas.

## Etapa Atual

Hoje a base de IA deve ficar concentrada em:

- `core/ai_service.py`
- `core/ai.py`

### `core/ai_service.py`

Responsavel por:

- descobrir os setores reais da empresa
- preparar o prompt de classificacao
- chamar o provedor de IA
- normalizar a resposta do modelo
- aplicar fallback seguro quando a IA nao puder ser usada

### `core/ai.py`

Responsavel por:

- decidir se a conversa pode ou nao ser classificada
- aplicar o resultado na conversa
- registrar log da decisao

## Fluxo de Triagem

1. mensagem entra pelo webhook
2. a conversa e encontrada ou criada na central
3. se `CompanySettings.central_ai_enabled` estiver ativo, a mensagem vai para `core.ai.classify_conversation_sector`
4. a classificacao so acontece se a conversa ainda estiver na central
5. a conversa e movida para o setor classificado

## Regras Arquiteturais

- o webhook nao deve conter logica de prompt
- a rota nao deve saber como o modelo foi chamado
- a lista de setores nunca deve ser hardcoded no codigo da IA
- fallback deve sempre ser seguro e previsivel
- erros da IA nao podem derrubar o webhook

## Proximas Etapas Recomendadas

1. adicionar configuracao de prompt e modelo por empresa
2. enriquecer `ai_logs` com provider, motivo, fallback e erro
3. criar sugestao de resposta para o atendente
4. criar resumo automatico da conversa
5. implementar RAG usando `Company.rag_document_path`
