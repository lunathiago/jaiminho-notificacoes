# Lambda Handler: WhatsApp Ingestion

## Visão Geral

Handler principal para ingestão de mensagens WhatsApp da W-API com **validação de segurança rigorosa** e **isolamento de tenants**.

## 🔒 Segurança

### Fluxo de Validação

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. Webhook Recebido                           │
│                   (W-API)                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              2. Validação de Schema (Pydantic)                   │
│         - Estrutura do payload                                   │
│         - Tipos de dados                                         │
│         - Campos obrigatórios                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         3. Validação de instance_id (DynamoDB)                   │
│         - Instance existe?                                       │
│         - API key válida?                                        │
│         - Status ativo?                                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│      4. Resolução Interna de tenant_id e user_id                 │
│         ⚠️  NUNCA confia no payload                              │
│         ✅  Resolve via instance_id mapping                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         5. Validação de Propriedade do Telefone                  │
│         - Telefone pertence ao instance?                         │
│         - Previne injeção cross-tenant                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         6. Detecção de Tentativa Cross-Tenant                    │
│         - Payload tenta especificar outro tenant?                │
│         - Payload contém user_id suspeito?                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         7. Normalização da Mensagem                              │
│         - Extrai texto/mídia                                     │
│         - Schema unificado                                       │
│         - Adiciona metadados de segurança                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         8. Forward para SQS (Processamento)                      │
│         - Message attributes com tenant_id                       │
│         - Body serializado                                       │
└─────────────────────────────────────────────────────────────────┘
```

## 🛡️ Componentes de Segurança

### 1. TenantIsolationMiddleware

**Responsabilidade**: Garantir que cada mensagem seja associada ao tenant correto.

**Validações**:
- ✅ Instance ID existe no banco
- ✅ API Key corresponde (hash SHA-256)
- ✅ Status do tenant está ativo
- ✅ Telefone pertence ao instance
- ✅ Nenhuma tentativa cross-tenant

### 2. TenantResolver

**Responsabilidade**: Resolver tenant_id e user_id de forma **autoritativa**.

**NUNCA confia em**:
- ❌ `user_id` no payload
- ❌ `tenant_id` no payload
- ❌ Qualquer identificador fornecido pelo cliente

**Sempre resolve via**:
- ✅ `instance_id` → DynamoDB → `tenant_id` + `user_id`
- ✅ Validação de API key hash
- ✅ Cache interno para performance

### 3. MessageNormalizer

**Responsabilidade**: Converter formatos diversos da W-API em schema unificado.

**Suporta**:
- Texto (conversation, extendedTextMessage)
- Imagem (com caption)
- Vídeo (com caption)
- Documento
- Áudio
- Localização
- Contato

**Adiciona**:
- Metadados de segurança
- Timestamp normalizado
- Source tracking (raw event preservado)

## 📝 Exemplo de Uso

### Payload da W-API

```json
{
  "instance": "my-instance-123",
  "event": "messages.upsert",
  "apikey": "secret-api-key",
  "data": {
    "key": {
      "remoteJid": "5511999999999@s.whatsapp.net",
      "fromMe": false,
      "id": "3EB0C3A5F2E0F8E0B0F0"
    },
    "message": {
      "conversation": "Olá, preciso de ajuda!"
    },
    "messageTimestamp": 1704240000,
    "pushName": "João Silva"
  }
}
```

### Mensagem Normalizada (após validação)

```json
{
  "message_id": "3EB0C3A5F2E0F8E0B0F0",
  "tenant_id": "tenant-abc-123",
  "user_id": "user-xyz-456",
  "sender_phone": "5511999999999",
  "sender_name": "João Silva",
  "message_type": "text",
  "content": {
    "text": "Olá, preciso de ajuda!"
  },
  "timestamp": 1704240000,
  "source": {
    "platform": "wapi",
    "instance_id": "my-instance-123",
    "raw_event": {...}
  },
  "metadata": {
    "is_group": false,
    "from_me": false,
    "forwarded": false
  },
  "security": {
    "validated_at": "2024-01-02T10:00:00Z",
    "validation_passed": true,
    "instance_verified": true,
    "tenant_resolved": true,
    "phone_ownership_verified": true
  }
}
```

## 🚨 Cenários de Rejeição

### 1. Instance ID Inválido

```
Status: 403 Forbidden
Mensagem: "Invalid or unauthorized instance"
Log: security_event=invalid_instance
```

### 2. API Key Incorreta

```
Status: 403 Forbidden
Mensagem: "API key mismatch"
Log: security_event=validation_failed
```

### 3. Tentativa Cross-Tenant

```
Status: 403 Forbidden
Mensagem: "Cross-tenant access attempt detected"
Log: security_event=cross_tenant_attempt, severity=critical
```

### 4. Telefone Não Pertence ao Instance

```
Status: 403 Forbidden
Mensagem: "Phone does not belong to this instance"
Log: security_event=validation_failed
```

### 5. Tenant Inativo/Suspenso

```
Status: 403 Forbidden
Mensagem: "Tenant status is suspended"
Log: security_event=validation_failed
```

## 🔍 Logging de Segurança

Todos os eventos de segurança são logados com estrutura JSON:

```json
{
  "timestamp": "2024-01-02T10:00:00Z",
  "level": "CRITICAL",
  "security_event": "cross_tenant_attempt",
  "severity": "critical",
  "instance_id": "my-instance-123",
  "details": {
    "attempted_tenant": "tenant-xyz",
    "actual_tenant": "tenant-abc"
  }
}
```

## 📊 Métricas e Alarmes

### CloudWatch Metrics

- `webhook.received` - Total de webhooks recebidos
- `webhook.rejected` - Webhooks rejeitados (segurança)
- `webhook.processed` - Webhooks processados com sucesso
- `validation.instance_failed` - Falhas de validação de instance
- `validation.cross_tenant` - Tentativas cross-tenant
- `normalization.failed` - Falhas de normalização

### Alarmes Recomendados

1. **Taxa de Rejeição Alta** (> 10%)
2. **Tentativas Cross-Tenant** (> 0)
3. **Instâncias Inválidas** (> 5/min)
4. **Latência Alta** (> 1s p99)

## 🧪 Testes

### Teste de Validação

```python
# Teste: Instance válido
event = {
    "body": json.dumps({
        "instance": "valid-instance",
        "event": "messages.upsert",
        "apikey": "valid-key",
        "data": {...}
    })
}
response = handler(event, context)
assert response['statusCode'] == 200
```

### Teste de Segurança

```python
# Teste: Instance inválido
event = {
    "body": json.dumps({
        "instance": "invalid-instance",
        ...
    })
}
response = handler(event, context)
assert response['statusCode'] == 403
assert 'unauthorized' in response['body']
```

## 🔐 Variáveis de Ambiente

```bash
# Obrigatórias
DYNAMODB_WAPI_INSTANCES_TABLE=jaiminho-dev-wapi-instances
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/.../message-buffer
DYNAMODB_MESSAGES_TABLE=jaiminho-dev-messages

# Opcionais
ENVIRONMENT=prod  # dev, staging, prod
LOG_LEVEL=INFO    # DEBUG, INFO, WARNING, ERROR
```

## ⚠️ Considerações de Segurança

1. **NUNCA confie em user_id do payload** - Sempre resolva internamente
2. **Sempre valide API key** - Use hash SHA-256 para comparação
3. **Valide propriedade do telefone** - Previne injeção cross-tenant
4. **Log todos eventos de segurança** - Crucial para auditoria
5. **Use HTTPS apenas** - Nunca aceite HTTP em produção
6. **Rate limiting** - Configure no API Gateway
7. **Cache com TTL** - Não cache indefinidamente

## 🚀 Deployment

O handler é deployado automaticamente via Terraform como Lambda `jaiminho_message_orchestrator`.

**Handler**: `lambda_handlers.ingest_whatsapp.handler`
**Runtime**: Python 3.11
**Memory**: 512 MB (configrável)
**Timeout**: 60s (configurável)

## 📚 Referências

- [W-API Webhooks](https://wapi.chat/webhooks)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Multi-tenant Security](https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html)
