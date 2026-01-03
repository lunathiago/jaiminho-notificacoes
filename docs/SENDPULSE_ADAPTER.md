# SendPulse WhatsApp Adapter

Adaptador Python para a API WhatsApp da SendPulse para o **Jaiminho Notificações**.

## Responsabilidades

- ✅ Enviar notificações urgentes (imediatamente)
- ✅ Enviar digests diários (em lote)
- ✅ Enviar botões interativos de feedback (confirmação)
- ✅ Resolver número de telefone usando user_id
- ✅ Apenas saída (nunca recebe mensagens)
- ✅ Isolamento de tenant em todas as operações
- ✅ Métricas no CloudWatch

## Arquitetura

```
SendPulseManager (High-level API)
    ├── SendPulseUserResolver (Resolve user_id → phone)
    ├── SendPulseNotificationFactory
    │   ├── SendPulseUrgentNotifier
    │   ├── SendPulseDigestSender
    │   └── SendPulseFeedbackSender
    └── SendPulseAuthenticator (OAuth + token management)
```

## Tipos de Notificação

### 1. Urgent (Urgente)

Entrega imediata com prioridade alta.

```python
from jaiminho_notificacoes.outbound.sendpulse import SendPulseManager, NotificationType

manager = SendPulseManager()

response = await manager.send_notification(
    tenant_id='tenant_1',
    user_id='user_123',
    content_text='System alert: High priority item',
    message_type=NotificationType.URGENT
)
```

**Características:**
- Prioridade: HIGH
- Entrega: Imediata
- TTL: Sem limite
- Com ou sem botões

### 2. Digest (Digest Diário)

Resumo agrupado de notificações.

```python
response = await manager.send_notification(
    tenant_id='tenant_1',
    user_id='user_123',
    content_text='📅 Daily Digest\n1. Item A\n2. Item B',
    message_type=NotificationType.DIGEST,
    metadata={'schedule_time': '09:00'}  # Optional
)
```

**Características:**
- Prioridade: MEDIUM
- Entrega: Agendada
- Formato: Texto multi-linha
- Ideal para resumos

### 3. Feedback (Botões Interativos)

Mensagem com botões para coleta de feedback.

```python
from jaiminho_notificacoes.outbound.sendpulse import SendPulseButton

buttons = [
    SendPulseButton(id='important', title='Important', action='reply'),
    SendPulseButton(id='not_important', title='Not Important', action='reply')
]

response = await manager.send_notification(
    tenant_id='tenant_1',
    user_id='user_123',
    content_text='Is this notification important?',
    message_type=NotificationType.FEEDBACK,
    buttons=buttons
)
```

**Características:**
- Máximo 3 botões
- Título: Máximo 20 caracteres
- Padrão para Learning Agent

## Resolução de Usuário

O adaptador resolve automaticamente o número de WhatsApp através do `user_id`:

```python
# Lookup automático via DynamoDB
# Tabela: jaiminho-user-profiles
# Chave: tenant_id + user_id
# Campo: whatsapp_phone

# Você também pode fornecer o telefone manualmente
response = await manager.send_notification(
    tenant_id='tenant_1',
    user_id='user_123',
    content_text='Hello',
    recipient_phone='554899999999'  # Override
)
```

**Schema DynamoDB (user-profiles):**

```python
{
    'tenant_id': 'str',           # PK
    'user_id': 'str',             # SK
    'whatsapp_phone': 'str',      # E.g., '554899999999'
    'name': 'str',
    'email': 'str',
    'created_at': 'str',
    'updated_at': 'str'
}
```

## Validação de Formato de Telefone

O adaptador valida automaticamente os números de telefone:

```python
# Formatos válidos (10-15 dígitos)
'554899999999'        ✅
'55 48 9 9999-9999'   ✅ (formatação removida)
'48999999999'         ✅

# Formatos inválidos
'123'                 ❌ (muito curto)
'1234567890123456'    ❌ (muito longo)
```

## Enviando em Lote

Envie notificações para múltiplos usuários:

```python
responses = await manager.send_batch(
    tenant_id='tenant_1',
    user_ids=['user_1', 'user_2', 'user_3'],
    content_text='Digest diário',
    message_type=NotificationType.DIGEST
)

# Resultados
for i, response in enumerate(responses):
    print(f"User {i}: {response.success}")
```

## Lambda Handler

### Single Notification

```python
event = {
    'tenant_id': 'tenant_1',
    'user_id': 'user_123',
    'notification_type': 'urgent',
    'content_text': 'Alert message',
    'buttons': [
        {'id': 'yes', 'title': 'Yes', 'action': 'reply'},
        {'id': 'no', 'title': 'No', 'action': 'reply'}
    ]
}

response = handler(event, context)
# {
#     'statusCode': 200,
#     'body': {
#         'success': true,
#         'message_id': 'sendpulse_123',
#         'status': 'sent',
#         'sent_at': '2024-01-15T10:30:00'
#     }
# }
```

### Batch Notifications

```python
event = {
    'tenant_id': 'tenant_1',
    'user_ids': ['user_1', 'user_2', 'user_3'],
    'notification_type': 'digest',
    'content_text': 'Daily digest'
}

response = handler(event, context)
# {
#     'statusCode': 200,
#     'body': {
#         'success': true,
#         'total': 3,
#         'successful': 3,
#         'failed': 0,
#         'results': [...]
#     }
# }
```

## Classe de Resposta

```python
@dataclass
class SendPulseResponse:
    success: bool                          # Enviado com sucesso?
    message_id: Optional[str]              # ID da SendPulse
    status: Optional[str]                  # 'sent', 'queued', 'failed'
    error: Optional[str]                   # Mensagem de erro
    api_response: Optional[Dict]           # Resposta bruta da API
    sent_at: str                           # Timestamp UTC
```

## Autenticação

### Configuração

A autenticação é feita via OAuth 2.0 com credenciais armazenadas no AWS Secrets Manager:

```bash
# Variável de ambiente
export SENDPULSE_SECRET_ARN=arn:aws:secretsmanager:...

# Schema do secret
{
    "client_id": "seu_client_id",
    "client_secret": "seu_client_secret",
    "api_url": "https://api.sendpulse.com"
}
```

### Token Management

- **Caching automático**: Tokens reutilizados enquanto válidos
- **Refresh automático**: Novo token quando expirado
- **TTL**: Padrão 3600 segundos

## Limites e Restrições

| Limite | Valor |
|--------|-------|
| Texto da mensagem | 4.096 caracteres |
| Botões por mensagem | 3 máximo |
| Caracteres por botão | 20 máximo |
| Dígitos do telefone | 10-15 dígitos |
| Timeout da API | 30 segundos |

## Tratamento de Erros

### Tipos de Erro

```python
# Phone não resolvido
{
    'success': False,
    'error': 'Could not resolve recipient phone number'
}

# Conteúdo inválido
{
    'success': False,
    'error': 'Text content is required'
}

# API Error
{
    'success': False,
    'error': 'API returned error',
    'api_response': {'error': 'Invalid recipient'}
}

# Erro de tenant
{
    'success': False,
    'error': 'Tenant validation failed'
}
```

### Retry Strategy

O adaptador trata automaticamente:
- ❌ Timeouts (> 30s)
- ❌ Erros de rede
- ❌ Throttling (429)
- ⚠️ Não retry automático (cliente decide)

## Logging

Estruturado via `TenantContextLogger`:

```python
# Info
"Sending urgent notification"
tenant_id=tenant_1
user_id=user_1
recipient_phone=554899999999

# Warning
"Failed to resolve recipient phone"
tenant_id=tenant_1
user_id=user_1

# Error
"Failed to send urgent notification"
error: Exception message
```

## Métricas CloudWatch

Namespace: `JaininhoNotificacoes/SendPulse`

| Métrica | Tipo | Descrição |
|---------|------|-----------|
| UrgentNotificationSent | Count | Notificações urgentes enviadas |
| DigestSent | Count | Digests enviados |
| FeedbackButtonsSent | Count | Mensagens com botões enviadas |
| SendError | Count | Erros de envio |

## Exemplo Completo: Integração com Learning Agent

```python
from jaiminho_notificacoes.outbound.sendpulse import (
    SendPulseManager,
    SendPulseButton,
    NotificationType
)

# Enviar com botões para feedback
async def send_feedback_request(user_id: str, tenant_id: str, notification_id: str):
    manager = SendPulseManager()
    
    buttons = [
        SendPulseButton(id='important', title='Important', action='reply'),
        SendPulseButton(id='not_important', title='Not Important', action='reply')
    ]
    
    response = await manager.send_notification(
        tenant_id=tenant_id,
        user_id=user_id,
        content_text=f'Is notification {notification_id} important to you?',
        message_type=NotificationType.FEEDBACK,
        buttons=buttons,
        metadata={'notification_id': notification_id}
    )
    
    if response.success:
        print(f"Feedback request sent: {response.message_id}")
    else:
        print(f"Failed: {response.error}")
```

## Exemplo: Envio de Digest Diário

```python
from datetime import datetime
from jaiminho_notificacoes.digest_agent import DigestAgent
from jaiminho_notificacoes.outbound.sendpulse import SendPulseManager, NotificationType

async def send_daily_digest(tenant_id: str, user_id: str):
    # Gerar digest
    agent = DigestAgent()
    digest = await agent.generate_digest(tenant_id, user_id)
    
    # Enviar via SendPulse
    manager = SendPulseManager()
    response = await manager.send_notification(
        tenant_id=tenant_id,
        user_id=user_id,
        content_text=digest.to_whatsapp_text(),
        message_type=NotificationType.DIGEST,
        metadata={
            'digest_id': digest.id,
            'generated_at': digest.generated_at
        }
    )
    
    return response
```

## Troubleshooting

### "Could not resolve recipient phone number"

**Causa**: Usuário não encontrado em `jaiminho-user-profiles`

**Solução**:
1. Verificar se user_id existe na tabela
2. Verificar se `whatsapp_phone` está preenchido
3. Usar `recipient_phone` manualmente

### "Text content is required"

**Causa**: Content_text vazio ou None

**Solução**:
```python
# Validar sempre
if not content_text or len(content_text.strip()) == 0:
    raise ValueError("Content required")
```

### "Invalid phone number"

**Causa**: Formato de telefone inválido

**Solução**:
```python
# Formato esperado: 10-15 dígitos (sem formatação)
phone = re.sub(r'\D', '', input_phone)  # Remove formatação
```

### Timeout na API

**Causa**: SendPulse API lenta

**Solução**: Aumentar timeout (padrão: 30s)
```python
response = await self._make_request(..., timeout=60)
```

## Integração com EventBridge

Dispare notificações via events:

```json
{
  "source": "jaiminho.notifications",
  "detail-type": "SendNotification",
  "detail": {
    "tenant_id": "tenant_1",
    "user_id": "user_1",
    "notification_type": "urgent",
        "content_text": "Message",
        "wapi_instance_id": "instance-abc"
  }
}
```

## Segurança

- ✅ Validação de tenant em todas operações
- ✅ Credentials em Secrets Manager (nunca em código)
- ✅ Tokens OAuth com expiration
- ✅ Logging estruturado (sem dados sensíveis)
- ✅ Validação de entrada (Pydantic)

## Performance

- **Phone caching**: 1.000 usuários em memória
- **Token reuse**: Até 3.600 segundos
- **Batch processing**: Até 100 usuários/segundo
- **Async I/O**: Non-blocking

## Próximas Melhorias

- [ ] Retry logic com backoff exponencial
- [ ] Circuit breaker para API
- [ ] Message queuing (SQS)
- [ ] Webhook de status (delivery confirmation)
- [ ] A/B testing de mensagens
- [ ] Template library
