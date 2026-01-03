# Feedback Handler para SendPulse

## Visão Geral

O **Feedback Handler** é o componente final do pipeline de processamento de notificações. Ele:

1. **Recebe respostas de botões** do SendPulse (Important / Not Important)
2. **Associa feedback** com a mensagem original e o user_id
3. **Atualiza estatísticas** de interrupção via Learning Agent
4. **Influencia decisões** futuras de urgência

## Arquitetura

```
SendPulse Webhook
       ↓
Feedback Handler
       ├─→ Webhook Validator (validação de estrutura)
       ├─→ Message Resolver (contexto da mensagem)
       ├─→ Feedback Processor (processamento)
       └─→ Learning Agent (atualizar estatísticas)
```

## Estrutura do Webhook

O SendPulse envia os eventos de botão como webhooks HTTP POST:

```json
{
  "event": "message.reaction",
  "recipient": "+554899999999",
  "message_id": "sendpulse_msg_123",
  "button_reply": {
    "id": "important",
    "title": "Important"
  },
  "timestamp": 1705340400,
  "metadata": {
    "message_id": "jaiminho_notif_456",
    "user_id": "user_1",
    "tenant_id": "tenant_1"
  }
}
```

### Campos Obrigatórios

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `event` | string | Tipo do evento (sempre "message.reaction") |
| `recipient` | string | Número de telefone do usuário |
| `message_id` | string | ID da mensagem do SendPulse |
| `button_reply.id` | string | ID do botão ("important" ou "not_important") |
| `button_reply.title` | string | Título exibido no botão |
| `timestamp` | integer | Unix timestamp da resposta |
| `metadata.message_id` | string | ID da mensagem original (Jaiminho) |
| `metadata.user_id` | string | ID do usuário |
| `metadata.tenant_id` | string | ID do tenant |

## Componentes

### 1. SendPulseWebhookValidator

Valida a estrutura do webhook e mapeia botões para tipos de feedback.

```python
from jaiminho_notificacoes.processing.feedback_handler import (
    SendPulseWebhookValidator
)

# Validar evento
validator = SendPulseWebhookValidator()
valid, error = validator.validate_event(event)

if not valid:
    print(f"Erro na validação: {error}")
else:
    # Mapear botão para tipo de feedback
    feedback_type = validator.map_button_to_feedback('important')
    # FeedbackType.IMPORTANT
```

### 2. FeedbackMessageResolver

Resolve o contexto da mensagem original (remetente, categoria, etc).

```python
from jaiminho_notificacoes.processing.feedback_handler import (
    FeedbackMessageResolver
)

resolver = FeedbackMessageResolver()
message_context = await resolver.resolve_message_context(
    tenant_id='tenant_1',
    message_id='jaiminho_456'
)

# Retorna:
# {
#     'message_id': 'jaiminho_456',
#     'sender_phone': '+1234567890',
#     'sender_name': 'System',
#     'category': 'system_alert',
#     'sent_at': '2024-01-15T10:00:00'
# }
```

### 3. UserFeedbackProcessor

Processa o feedback e atualiza o Learning Agent.

```python
from jaiminho_notificacoes.processing.feedback_handler import (
    UserFeedbackProcessor
)

processor = UserFeedbackProcessor()
result = await processor.process_feedback(webhook_event)

if result.success:
    print(f"Feedback processado: {result.feedback_id}")
    print(f"Tipo: {result.feedback_type}")
    print(f"Tempo de processamento: {result.processing_time_ms}ms")
else:
    print(f"Erro: {result.error}")
```

### 4. FeedbackHandler

Interface de alto nível para processamento de feedback.

```python
from jaiminho_notificacoes.processing.feedback_handler import (
    get_feedback_handler
)

# Obter instância singleton
handler = get_feedback_handler()

# Processar um webhook
result = await handler.handle_webhook(event)

# Processar múltiplos webhooks
results = await handler.handle_batch_webhooks([event1, event2, event3])
```

## Lambda Handler

O Lambda handler processa webhooks enviados pelo SendPulse:

```python
# process_feedback_webhook.py

def lambda_handler(event, context):
    """
    Processa webhook de feedback do SendPulse.
    
    Evento esperado:
    {
        "body": "{...webhook json...}"  # ou JSON direto se via API Gateway
    }
    
    Retorna:
    {
        "statusCode": 200,
        "body": "{\"status\": \"success\", \"feedback_id\": \"...\", ...}"
    }
    """
    pass
```

## Fluxo de Processamento

```
1. Webhook recebido
   ↓
2. Validação da estrutura
   - Campos obrigatórios
   - Tipos de dados
   - ID do botão conhecido
   ↓
3. Mapeamento para FeedbackType
   - "important" → IMPORTANT
   - "not_important" → NOT_IMPORTANT
   ↓
4. Resolução do contexto
   - Query: mensagem original
   - Obter: remetente, categoria
   ↓
5. Criação do feedback record
   - feedback_id único
   - Timestamp da resposta
   - Tempo de resposta calculado
   ↓
6. Atualizar Learning Agent
   - UserFeedbackRecord salvo
   - InterruptionStatisticsRecord atualizado
   - 3 níveis: user, sender, category
   ↓
7. Responder ao SendPulse
   - 200 OK com feedback_id
```

## Tipos de Feedback

### IMPORTANT (Importante)

Indica que a notificação foi relevante e não deveria ter sido interrompida (se foi).

**Impacto nas estatísticas:**
- Incrementa `important_count`
- Calcula accuracy: foi urgente?
- Influencia `urgency_score` do sender

```python
feedback_type = FeedbackType.IMPORTANT  # "important"
```

### NOT_IMPORTANT (Não Importante)

Indica que a notificação não era relevante e/ou poderia ter sido resumida em um digest.

**Impacto nas estatísticas:**
- Incrementa `not_important_count`
- Marca como "false positive"
- Reduz `urgency_score` do sender

```python
feedback_type = FeedbackType.NOT_IMPORTANT  # "not_important"
```

## Integração com Urgency Agent

O feedback influencia decisões futuras de urgência:

```python
from jaiminho_notificacoes.processing.urgency_agent import (
    UrgencyAgent
)

# O Urgency Agent consulta estatísticas atualizadas
agent = UrgencyAgent()

# Ao processar nova mensagem:
urgency_score = await agent.calculate_urgency(
    message=message,
    user_id=user_id,
    tenant_id=tenant_id
    # ← Consulta InterruptionStatisticsRecord atualizado
)
```

## Integração com Learning Agent

O Learning Agent recebe os feedback records:

```python
from jaiminho_notificacoes.processing.learning_agent import (
    LearningAgent
)

agent = LearningAgent()

# Ao processar feedback
await agent.process_feedback(feedback_record)
# ← Atualiza InterruptionStatisticsRecord
# ← Calcula métricas de 3 níveis
```

## Tratamento de Erros

### Webhook Inválido

```json
{
  "statusCode": 400,
  "body": {
    "status": "error",
    "error": "Missing required field: button_reply"
  }
}
```

### Botão Desconhecido

```json
{
  "statusCode": 400,
  "body": {
    "status": "error",
    "error": "Unknown button type: custom_button"
  }
}
```

### Erro Interno

```json
{
  "statusCode": 500,
  "body": {
    "status": "error",
    "error": "Internal server error: ..."
  }
}
```

## Configuração

### Variáveis de Ambiente

```bash
# DynamoDB tables
FEEDBACK_TABLE_NAME=feedback-records
INTERRUPTION_STATS_TABLE_NAME=interruption-stats
MESSAGE_TRACKING_TABLE_NAME=notifications-sent

# AWS region
AWS_REGION=us-east-1

# Tenant isolation
ENFORCE_TENANT_ISOLATION=true
```

### Webhook Secret (Segurança)

Para validar que o webhook veio realmente do SendPulse:

```python
import hmac
import hashlib

def validate_webhook_signature(payload, signature, secret):
    """Valida assinatura do webhook SendPulse."""
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)
```

## Exemplos de Uso

### Processar Webhook Simples

```python
from jaiminho_notificacoes.processing.feedback_handler import (
    get_feedback_handler
)

event = {
    'event': 'message.reaction',
    'recipient': '+554899999999',
    'message_id': 'sendpulse_123',
    'button_reply': {
        'id': 'important',
        'title': 'Important'
    },
    'timestamp': 1705340400,
    'metadata': {
        'message_id': 'jaiminho_456',
        'user_id': 'user_1',
        'tenant_id': 'tenant_1'
    }
}

handler = get_feedback_handler()
result = await handler.handle_webhook(event)

print(f"Feedback ID: {result.feedback_id}")
print(f"Tipo: {result.feedback_type}")
print(f"Tempo: {result.processing_time_ms}ms")
print(f"Estatísticas atualizadas: {result.statistics_updated}")
```

### Processar Batch de Webhooks

```python
events = [
    { ... webhook 1 ... },
    { ... webhook 2 ... },
    { ... webhook 3 ... }
]

handler = get_feedback_handler()
results = await handler.handle_batch_webhooks(events)

for i, result in enumerate(results):
    if result.success:
        print(f"Evento {i}: OK - {result.feedback_id}")
    else:
        print(f"Evento {i}: ERRO - {result.error}")
```

### Validação Customizada

```python
from jaiminho_notificacoes.processing.feedback_handler import (
    SendPulseWebhookValidator
)

validator = SendPulseWebhookValidator()

# Validar evento
valid, error = validator.validate_event(my_event)

if valid:
    # Mapear botão
    feedback_type = validator.map_button_to_feedback(
        my_event['button_reply']['id']
    )
    
    print(f"Feedback type: {feedback_type.value}")
else:
    print(f"Validation error: {error}")
```

## Testes

Executar testes:

```bash
pytest tests/unit/test_feedback_handler.py -v

# Com cobertura
pytest tests/unit/test_feedback_handler.py --cov=jaiminho_notificacoes.processing.feedback_handler
```

Principais cenários testados:

- ✅ Validação de eventos válidos
- ✅ Rejeição de eventos inválidos
- ✅ Mapeamento de botões para tipos de feedback
- ✅ Processamento de feedback IMPORTANT
- ✅ Processamento de feedback NOT_IMPORTANT
- ✅ Resolução de contexto da mensagem
- ✅ Atualização do Learning Agent
- ✅ Tratamento de exceções
- ✅ Isolamento de tenant
- ✅ Batch processing

## Métricas CloudWatch

O handler emite métricas para CloudWatch:

```
jaiminho-notificacoes/feedback:
  - ProcessedCount (count)
  - SuccessfulCount (count)
  - FailureCount (count)
  - ProcessingTime (ms)
  - FeedbackType.IMPORTANT (count)
  - FeedbackType.NOT_IMPORTANT (count)
  - StatisticsUpdateFailures (count)
```

## Monitoramento

### CloudWatch Logs

```
2024-01-15T10:30:45.123Z Processing feedback
2024-01-15T10:30:45.456Z Learning Agent updated
2024-01-15T10:30:45.789Z Feedback processed successfully
```

### Alertas Recomendados

```
FailureCount > 10 in 5 minutes
ProcessingTime > 5000ms (SLA)
StatisticsUpdateFailures > 5 in 10 minutes
```

## Troubleshooting

### Feedback não está sendo processado

**Verificar:**
1. Webhook Secret está correto?
2. Endpoint Lambda está configurado no SendPulse?
3. Logs no CloudWatch mostram erros?

### Estatísticas não estão sendo atualizadas

**Verificar:**
1. DynamoDB table `INTERRUPTION_STATS_TABLE_NAME` existe?
2. IAM role tem permissões para DynamoDB?
3. Learning Agent está disponível?

### Resposta lenta (> 5000ms)

**Causas possíveis:**
1. DynamoDB throttling
2. Lambda timeout
3. Network latency para SendPulse

**Soluções:**
1. Aumentar DynamoDB capacity
2. Aumentar Lambda timeout
3. Usar Lambda VPC Endpoints

## Segurança

### Validação de Tenant

Todos os pedidos são validados contra `tenant_id` na metadata:

```python
self.middleware.validate_tenant_context({
    'tenant_id': tenant_id,
    'user_id': user_id
})
```

### Validação de Webhook

Assinatura SHA-256 pode ser validada:

```python
# Adicionar ao config
SENDPULSE_WEBHOOK_SECRET = "seu_secret_aqui"

# Validar no handler
def validate_signature(body, signature):
    ...
```

### Rate Limiting

Recomendado limitar:
- 100 webhooks por minuto por tenant
- 1000 webhooks por dia por tenant

## Próximas Etapas

1. **Message Tracking**: Armazenar message_id ao enviar notificação
2. **Urgency Integration**: Query Learning Agent stats no Urgency Agent
3. **Analytics**: Dashboard de feedback
4. **Webhook Retry**: Re-processar falhas com exponential backoff
5. **Batch Export**: Exportar feedback para análise
