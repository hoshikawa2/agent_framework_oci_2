# Correção TIM Observer Payload / NOC OTel

Esta versão corrige dois gaps da migração do `agent_framework_oci`:

1. **Pub/Sub flat**: eventos IC/GRL/analytics passam a ser publicados no contrato flat combinado com Data/TIM, sem envelope `{type, payload}` e sem `payload.payload`.
2. **NOC em OpenTelemetry Logs**: eventos NOC passam a ter caminho dedicado para OTel Logs, separado de traces/spans.

## Arquivos alterados/adicionados

- `src/agent_framework/analytics/tim_payload_mapper.py`
  - Novo mapper canônico para converter o envelope interno do framework para o payload TIM flat.
  - Mantém campos canônicos na raiz.
  - Mantém apenas `agentSpecificData` como objeto aninhado.

- `src/agent_framework/analytics/providers/pubsub.py`
  - Publica flat por padrão.
  - Mantém modo legado por configuração.
  - Exclui `NOC.*` do Pub/Sub por padrão, seguindo a lib antiga.

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
  "agentSpecificData": {
    "invoiceId": "INV-001"
  }
}
```

## Observação

O envelope interno retornado pelo `observer.emit(...)` foi mantido para não quebrar EventBus, Langfuse ou consumidores internos. A correção ocorre no provider Pub/Sub e no novo canal NOC OTel.
