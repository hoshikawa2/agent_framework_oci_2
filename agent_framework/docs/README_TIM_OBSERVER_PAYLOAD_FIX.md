# Correção TIM Observer Payload / NOC OTel

Esta versão corrige dois gaps da migração do `agent_framework_oci`:

1. **Pub/Sub flat**: eventos IC/GRL/analytics passam a ser publicados no contrato flat combinado com Data/TIM, sem envelope `{type, payload}` e sem `payload.payload`.
2. **NOC em OpenTelemetry Logs**: eventos NOC passam a ter caminho dedicado para OTel Logs, separado de traces/spans.
3. **Sequence automático**: eventos Pub/Sub flat passam a receber `sequence` incremental por `agentId/sessionId`, preservando valor explícito quando já vier no evento.

## Arquivos alterados/adicionados

- `src/agent_framework/analytics/tim_payload_mapper.py`
  - Novo mapper canônico para converter o envelope interno do framework para o payload TIM flat.
  - Mantém campos canônicos na raiz.
  - Mantém apenas `agentSpecificData` como objeto aninhado.

- `src/agent_framework/analytics/providers/pubsub.py`
  - Publica flat por padrão.
  - Mantém modo legado por configuração.
  - Exclui `NOC.*` do Pub/Sub por padrão, seguindo a lib antiga.
  - Injeta `sequence` automaticamente no payload flat antes do publish.

- `src/agent_framework/analytics/tim_sequence.py`
  - Novo gerador de sequence por `agentId/sessionId`.
  - Usa Redis `INCR` como contador atômico cross-worker/cross-pod.
  - Usa fallback em memória quando Redis não estiver disponível, sem quebrar o fluxo de observabilidade.
  - Preserva `sequence` explícito quando o chamador já informou o campo.

- `src/agent_framework/observability/noc_otel.py`
  - Novo exportador dedicado de NOC para OpenTelemetry Logs.
  - Usa `OTLPLogExporter` e `LoggingHandler`.
  - Aplica DE/PARA flat com `keep_none=True`.
  - Achata dict/list para string JSON antes de enviar ao OTel.

- `src/agent_framework/observability/observer.py`
  - `emit_noc()` agora dispara o canal dedicado de OTel Logs antes da publicação analytics.

- `src/agent_framework/config/settings.py`
  - Novas variáveis de configuração.

## Novas variáveis

```env
# Pub/Sub: padrão corrigido para TIM/Data
PUBSUB_PAYLOAD_MODE=flat
PUBSUB_EXCLUDE_NOC=true

# Sequence automático por sessão no payload Pub/Sub flat
PUBSUB_SEQUENCE_ENABLED=true
PUBSUB_SEQUENCE_REDIS_URL=redis://localhost:6379/0
PUBSUB_SEQUENCE_TTL_SECONDS=86400
PUBSUB_SEQUENCE_MEMORY_FALLBACK=true
PUBSUB_SEQUENCE_KEY_PREFIX=observer:sequence

# Para voltar temporariamente ao formato antigo envelopado
# PUBSUB_PAYLOAD_MODE=legacy

# NOC via OpenTelemetry Logs
ENABLE_NOC_OTEL_LOGS=true
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=http://10.153.35.23/v1/logs
OTEL_EXPORTER_OTLP_HOST_HEADER=tim-ai-atend-agnt-opentelemetry
OTEL_SERVICE_NAME=ai-agent-template
```

## Exemplo de Pub/Sub corrigido

```json
{
  "eventType": "IC.FATURA_CONSULTADA",
  "version": "1.0",
  "eventDate": "2026-06-19T12:00:00+00:00",
  "sessionId": "sess-789",
  "channelId": "whatsapp",
  "agentId": "billing-agent",
  "tag": "IC.FATURA_CONSULTADA",
  "sequence": 12,
  "agentSpecificData": {
    "invoiceId": "INV-001"
  }
}
```

## Observação

O envelope interno retornado pelo `observer.emit(...)` foi mantido para não quebrar EventBus, Langfuse ou consumidores internos. A correção ocorre no provider Pub/Sub e no novo canal NOC OTel.


## Sequence automático

No modo flat, o provider Pub/Sub chama `ensure_sequence(message)` antes de publicar.

Com `sessionId` presente e sem `sequence` explícito, o framework gera:

```text
observer:sequence:<agentId>:<sessionId> -> INCR
```

Exemplo:

```json
{ "eventType": "IC.001", "sessionId": "sess-1", "agentId": "billing", "sequence": 1 }
{ "eventType": "IC.002", "sessionId": "sess-1", "agentId": "billing", "sequence": 2 }
{ "eventType": "IC.003", "sessionId": "sess-1", "agentId": "billing", "sequence": 3 }
```

Regras:

- Se `sequence` já vier no metadata/payload, ele é preservado.
- Se `sessionId` não existir, o campo não é gerado.
- Redis é o caminho recomendado para produção, pois `INCR` é atômico entre workers/pods.
- O fallback em memória é apenas best-effort local para ambientes de desenvolvimento ou contingência.
