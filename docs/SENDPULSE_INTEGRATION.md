# SendPulse WhatsApp Adapter - Integration Guide

Este guia descreve como integrar o adaptador SendPulse com o restante do **Jaiminho Notificações**.

## Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────┐
│                   Message Processing Pipeline                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Ingestion          2. Processing      3. Outbound        │
│  ┌──────────────┐      ┌──────────────┐   ┌──────────────┐  │
│  │ W-API│─────▶│ Classif.     │──▶│ SendPulse    │  │
│  │ (WhatsApp)   │      │ Urgency      │   │ Adapter      │  │
│  └──────────────┘      │ Rules Engine │   │ (WhatsApp)   │  │
│                        │ Learning Ag. │   └──────────────┘  │
│                        └──────────────┘         ▲             │
│                               ▲                 │             │
│                               │                 │             │
│                        ┌──────┴─────────────┐   │             │
│                        │ Feedback System    │───┘             │
│                        │ (Learning Agent)   │                 │
│                        └────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

## Fluxos de Integração

### 1. Notificações Urgentes

```
┌─────────────────────────┐
│ Urgency Agent           │  Detecta evento com alta urgência
│ (urgency_score > 0.8)   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Lambda Handler          │  Dispara envio via EventBridge
│ send_notifications      │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ SendPulseUrgentNotifier │  Envia imediatamente
│ (HIGH priority)         │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ User (WhatsApp)         │  Recebe notificação urgente
└─────────────────────────┘
```

### 2. Digests Diários

```
┌─────────────────────────┐
│ CloudWatch Event        │  Dispara diariamente (ex: 9 AM)
│ (EventBridge schedule)  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Digest Agent            │  Agrupa notificações do dia
│ generate_daily_digest   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ SendPulseDigestSender   │  Envia em lote
│ (MEDIUM priority)       │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ User (WhatsApp)         │  Recebe digest formatado
└─────────────────────────┘
```

### 3. Coleta de Feedback (Learning Agent)

```
┌─────────────────────────┐
│ Notification Event      │  Nova notificação chegou
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ SendPulseFeedbackSender │  Envia com botões interativos
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ User Response (webhook) │  Usuário clica em botão
│ /feedback               │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Lambda: process_feedback│  Persiste resposta
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Learning Agent          │  Atualiza estatísticas
│ update_statistics       │
└─────────────────────────┘
```

## Pré-requisitos

### AWS Infrastructure

1. **DynamoDB Tables**
   - `jaiminho-user-profiles`: Perfis de usuários com número WhatsApp
   - `jaiminho-notifications`: Log de notificações enviadas (opcional)

2. **Lambda Functions**
   - `send_notifications`: Handler para enviar notificações
   - `generate_digest`: Digest scheduler (ou EventBridge rule)

3. **Secrets Manager**
   - SendPulse credentials (client_id, client_secret)

4. **IAM Roles**
   - Permissões para ler de Secrets Manager
   - Permissões para ler de DynamoDB
   - Permissões para escrever em CloudWatch

### SendPulse Setup

1. Criar conta em sendpulse.com
2. Configurar WhatsApp Business Account
3. Gerar OAuth credentials (client_id, client_secret)
4. Armazenar em AWS Secrets Manager

```bash
# Exemplo de criação do secret
aws secretsmanager create-secret \
  --name sendpulse-credentials \
  --secret-string '{
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "api_url": "https://api.sendpulse.com"
  }'
```

## Configuração de Ambiente

### Variáveis de Ambiente

```bash
# .env local
export SENDPULSE_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:name
export DYNAMODB_USER_PROFILES_TABLE=jaiminho-user-profiles
export AWS_REGION=us-east-1
```

### Terraform Variables

```hcl
# terraform/variables.tf
variable "sendpulse_secret_arn" {
  description = "ARN of SendPulse credentials in Secrets Manager"
  type        = string
}

variable "sendpulse_secret_region" {
  description = "Region where secret is stored"
  type        = string
  default     = "us-east-1"
}
```

### Terraform Configuration

```hcl
# terraform/lambda.tf

resource "aws_lambda_function" "send_notifications" {
  function_name = "jaiminho-send-notifications-${var.environment}"
  role          = aws_iam_role.lambda_sendpulse.arn
  handler       = "send_notifications.handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      SENDPULSE_SECRET_ARN          = var.sendpulse_secret_arn
      DYNAMODB_USER_PROFILES_TABLE  = aws_dynamodb_table.user_profiles.name
      ENVIRONMENT                   = var.environment
    }
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_sendpulse_secrets]
}

# IAM Role com permissões mínimas
resource "aws_iam_role" "lambda_sendpulse" {
  name = "jaiminho-lambda-sendpulse-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Acesso a Secrets Manager
resource "aws_iam_policy" "lambda_sendpulse_secrets" {
  name = "jaiminho-lambda-sendpulse-secrets-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = [var.sendpulse_secret_arn]
    }]
  })
}

# Acesso a DynamoDB
resource "aws_iam_policy" "lambda_sendpulse_dynamodb" {
  name = "jaiminho-lambda-sendpulse-dynamodb-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:Query"
      ]
      Resource = [aws_dynamodb_table.user_profiles.arn]
    }]
  })
}

# CloudWatch Logs
resource "aws_iam_policy" "lambda_sendpulse_logs" {
  name = "jaiminho-lambda-sendpulse-logs-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Resource = "arn:aws:logs:*:*:*"
    }]
  })
}

# CloudWatch Metrics
resource "aws_iam_policy" "lambda_sendpulse_metrics" {
  name = "jaiminho-lambda-sendpulse-metrics-${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "cloudwatch:PutMetricData"
      ]
      Resource = "*"
    }]
  })
}

# Attach policies
resource "aws_iam_role_policy_attachment" "lambda_sendpulse_secrets" {
  role       = aws_iam_role.lambda_sendpulse.name
  policy_arn = aws_iam_policy.lambda_sendpulse_secrets.arn
}

resource "aws_iam_role_policy_attachment" "lambda_sendpulse_dynamodb" {
  role       = aws_iam_role.lambda_sendpulse.name
  policy_arn = aws_iam_policy.lambda_sendpulse_dynamodb.arn
}

resource "aws_iam_role_policy_attachment" "lambda_sendpulse_logs" {
  role       = aws_iam_role.lambda_sendpulse.name
  policy_arn = aws_iam_policy.lambda_sendpulse_logs.arn
}

resource "aws_iam_role_policy_attachment" "lambda_sendpulse_metrics" {
  role       = aws_iam_role.lambda_sendpulse.name
  policy_arn = aws_iam_policy.lambda_sendpulse_metrics.arn
}
```

## Uso na Prática

### 1. Em Lambda Handlers

```python
# Lambda: send_notifications
from jaiminho_notificacoes.lambda_handlers.send_notifications import handler

def lambda_handler(event, context):
    return handler(event, context)
```

### 2. Integrando com Urgency Agent

```python
from jaiminho_notificacoes.processing.urgency import UrgencyAgent
from jaiminho_notificacoes.outbound.sendpulse import SendPulseManager, NotificationType

async def process_and_send_urgent(message: Message):
    # Avaliar urgência
    urgency_agent = UrgencyAgent()
    result = await urgency_agent.evaluate(message)
    
    # Se urgente, enviar via SendPulse
    if result.urgency_score > 0.8:
        manager = SendPulseManager()
        response = await manager.send_notification(
            tenant_id=message.tenant_id,
            user_id=message.user_id,
            content_text=message.content.text,
            message_type=NotificationType.URGENT,
            metadata={'urgency_score': result.urgency_score}
        )
        
        return response
```

### 3. Integrando com Digest Agent

```python
from jaiminho_notificacoes.processing.digest import DigestAgent
from jaiminho_notificacoes.outbound.sendpulse import SendPulseManager, NotificationType

async def send_daily_digest(tenant_id: str):
    # Gerar digest
    digest_agent = DigestAgent()
    digest = await digest_agent.generate(tenant_id)
    
    # Enviar para todos os usuários
    manager = SendPulseManager()
    responses = await manager.send_batch(
        tenant_id=tenant_id,
        user_ids=digest.user_ids,
        content_text=digest.to_whatsapp_text(),
        message_type=NotificationType.DIGEST
    )
    
    return responses
```

### 4. Integrando com Learning Agent

```python
from jaiminho_notificacoes.outbound.sendpulse import (
    SendPulseManager,
    SendPulseButton,
    NotificationType
)

async def send_feedback_request(notification_id: str, tenant_id: str, user_id: str):
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
    
    return response
```

## EventBridge Rules

### Rule: Digests Diários

```json
{
  "Name": "jaiminho-daily-digest",
  "ScheduleExpression": "cron(0 9 * * ? *)",
  "State": "ENABLED",
  "Targets": [{
    "Arn": "arn:aws:lambda:region:account:function:generate_digest",
    "RoleArn": "arn:aws:iam::account:role/eventbridge-invoke-lambda"
  }]
}
```

### Rule: Enviar Notificações Urgentes

```json
{
  "Name": "jaiminho-urgent-notifications",
  "EventPattern": {
    "source": ["jaiminho.urgency"],
    "detail-type": ["UrgentNotification"],
    "detail": {
      "urgency_score": [{"numeric": [">", 0.8]}]
    }
  },
  "State": "ENABLED",
  "Targets": [{
    "Arn": "arn:aws:lambda:region:account:function:send_notifications",
    "RoleArn": "arn:aws:iam::account:role/eventbridge-invoke-lambda"
  }]
}
```

## DynamoDB Schema

### User Profiles Table

```python
# Existing or new table
table_name = "jaiminho-user-profiles"

# Schema
{
    "TableName": "jaiminho-user-profiles",
    "KeySchema": [
        {"AttributeName": "tenant_id", "KeyType": "HASH"},
        {"AttributeName": "user_id", "KeyType": "RANGE"}
    ],
    "AttributeDefinitions": [
        {"AttributeName": "tenant_id", "AttributeType": "S"},
        {"AttributeName": "user_id", "AttributeType": "S"}
    ],
    "BillingMode": "PAY_PER_REQUEST"
}

# Exemplo de item
{
    "tenant_id": "acme_corp",
    "user_id": "user_123",
    "whatsapp_phone": "554899999999",
    "name": "João Silva",
    "email": "joao@acme.com",
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-15T10:30:00Z"
}
```

## Logging e Monitoring

### CloudWatch Logs

```
Namespace: /aws/lambda/jaiminho-send-notifications

Campos estruturados:
- tenant_id
- user_id
- notification_type
- message_id
- success
- error (se houver)
```

### CloudWatch Metrics

```
Namespace: JaininhoNotificacoes/SendPulse

Métricas:
- UrgentNotificationSent (Count)
- DigestSent (Count)
- FeedbackButtonsSent (Count)
- SendError (Count)
```

### Exemplo de Consulta CloudWatch Insights

```
fields @timestamp, tenant_id, user_id, success
| filter notification_type = "urgent"
| stats count() by tenant_id
```

## Segurança

### Isolamento de Tenant

```python
from jaiminho_notificacoes.core.tenant import TenantIsolationMiddleware

middleware = TenantIsolationMiddleware()

# Ao receber feedback dos botões, resolva o contexto via W-API instance
tenant_context, errors = await middleware.validate_and_resolve(
  instance_id=metadata['wapi_instance_id'],
  payload={'tenant_id': metadata.get('tenant_id')}
)

if not tenant_context:
  raise SecurityError(errors)
```

### Credenciais

- Nunca hardcode SendPulse credentials
- Use AWS Secrets Manager
- Rotação automática recomendada

### Validação de Entrada

```python
from jaiminho_notificacoes.outbound.sendpulse import SendPulseMessage

message = SendPulseMessage(...)
valid, error = message.validate()

if not valid:
    raise ValueError(f"Invalid message: {error}")
```

## Troubleshooting

### "SENDPULSE_SECRET_ARN not configured"

```bash
# Verificar variável de ambiente
echo $SENDPULSE_SECRET_ARN

# Configurar no Lambda
export SENDPULSE_SECRET_ARN=arn:aws:secretsmanager:...
```

### "Could not resolve recipient phone number"

```python
# Verificar se usuário existe em user-profiles
aws dynamodb get-item \
  --table-name jaiminho-user-profiles \
  --key '{"tenant_id": {"S": "tenant_1"}, "user_id": {"S": "user_1"}}'

# Verificar se whatsapp_phone está preenchido
```

### Credenciais inválidas

```bash
# Verificar credenciais no Secrets Manager
aws secretsmanager get-secret-value --secret-id sendpulse-credentials
```

## Próximas Etapas

1. Implementar persistência de notificações (DynamoDB)
2. Adicionar tracking de delivery status
3. Implementar retry logic com exponential backoff
4. Criar circuit breaker para API
5. Implementar webhook de status da SendPulse
