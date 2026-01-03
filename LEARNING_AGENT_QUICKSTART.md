# Learning Agent - Quick Start Guide

## 🚀 Overview Rápido

O Learning Agent foi **totalmente implementado** com:
- ✅ Processamento de feedback binário
- ✅ Atualização de estatísticas (sender, category, user)
- ✅ Integração com Urgency Agent
- ✅ Sem machine learning
- ✅ Production-ready

## 📁 Arquivos Principais

### Core
- `src/jaiminho_notificacoes/processing/learning_agent.py` - LearningAgent class
- `src/jaiminho_notificacoes/processing/learning_integration.py` - HistoricalDataProvider
- `src/jaiminho_notificacoes/lambda_handlers/process_feedback.py` - HTTP webhook

### Infrastructure
- `terraform/dynamodb.tf` - 2 novas tabelas
- `terraform/iam.tf` - IAM role lambda_feedback

### Documentation
- `docs/LEARNING_AGENT.md` - Completa
- `LEARNING_AGENT_IMPLEMENTATION.md` - Deploy guide
- `LEARNING_AGENT_ARCHITECTURE.md` - Diagrama visual
- `LEARNING_AGENT_SUMMARY.md` - Este arquivo

## 🔧 Deployment

### Step 1: Infrastructure
```bash
cd terraform/
terraform plan -var-file="environments/prod.tfvars"
terraform apply -var-file="environments/prod.tfvars"
```

Cria:
- Table: `jaiminho-feedback`
- Table: `jaiminho-interruption-stats`
- Role: `lambda_feedback`

### Step 2: Code
```bash
pip install -r requirements/prod.txt
zip -r lambda.zip src/
aws lambda update-function-code \
  --function-name jaiminho-feedback-handler \
  --zip-file fileb://lambda.zip
```

### Step 3: Environment
Lambda função: `jaiminho-feedback-handler`
```
LEARNING_AGENT_ENABLED=true
DYNAMODB_FEEDBACK_TABLE=jaiminho-feedback
DYNAMODB_INTERRUPTION_STATS_TABLE=jaiminho-interruption-stats
```

## 🧪 Testing

### Unit Tests
```bash
pytest tests/unit/test_learning_agent.py -v
```

### Integration
```bash
python examples/learning_agent_demo.py
```

### Manual
```bash
curl -X POST /feedback \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message_id": "msg-789",
    "sender_phone": "5511999999999",
    "sender_name": "João",
    "feedback_type": "important",
    "was_interrupted": true,
    "message_category": "financial",
    "user_response_time_seconds": 30.5
  }'
```

## 📊 API Webhook

### POST /feedback

**Request:**
```json
{
  "tenant_id": "tenant-123",
  "user_id": "user-456",
  "message_id": "msg-789",
  "sender_phone": "5511999999999",
  "sender_name": "João Silva",
  "feedback_type": "important",
  "was_interrupted": true,
  "message_category": "financial",
  "user_response_time_seconds": 30.5,
  "feedback_reason": "Era realmente importante"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Feedback {id} processed",
  "feedback_id": "{uuid}"
}
```

## 🎯 Como Funciona

### 1. User Feedback
Usuário marca: "Importante" ou "Não importante"

### 2. Processing
```
LearningAgent.process_feedback()
  ├─ Persist UserFeedback → jaiminho-feedback
  ├─ Update SENDER stats → jaiminho-interruption-stats
  ├─ Update CATEGORY stats → jaiminho-interruption-stats
  └─ Update USER stats → jaiminho-interruption-stats
```

### 3. Statistics Updated
- `important_count` / `not_important_count`
- `correct_interrupts` / `incorrect_interrupts`
- `correct_digests` / `missed_urgent`
- `accuracy`, `precision`, `recall`

### 4. Context for Urgency Agent
```python
context = await provider.generate_historical_context_prompt(...)
# Returns: "Remetente: 45 msgs, 20% importantes, resposta 2.5min"
```

### 5. Better Decisions
Urgency Agent usa contexto no LLM prompt → Melhores decisões

## 🔍 Data Models

### UserFeedback
```python
feedback_id: str
tenant_id: str
user_id: str
message_id: str
sender_phone: str
sender_name: Optional[str]
feedback_type: "important" | "not_important"
message_category: Optional[str]  # financial, marketing, etc
was_interrupted: bool
user_response_time_seconds: Optional[float]
feedback_timestamp: int
feedback_reason: Optional[str]
created_at: str
```

### InterruptionStatistics
```python
# Counts
total_feedback_count: int
important_count: int
not_important_count: int

# Accuracy
correct_interrupts: int      # TP: marked urgent, was important
incorrect_interrupts: int    # FP: marked urgent, was not
correct_digests: int         # TN: marked digest, was not important
missed_urgent: int           # FN: missed urgent

# Metrics
important_rate: % important
accuracy_rate: (TP + TN) / total
precision: TP / (TP + FP)
recall: TP / (TP + FN)

# Timing
avg_response_time_seconds: float
window_start_timestamp: int (30 days ago)
```

## 📈 Metrics Explained

### Important Rate
% de feedbacks que foram marcados como importante.
- < 10%: Remetente raramente importante
- 10-30%: Ocasionalmente importante
- > 30%: Frequentemente importante

### Accuracy
% de decisões corretas do sistema.
- < 70%: Precisa melhorias
- 70-85%: Aceitável
- > 85%: Excelente

### Precision
De todos os interrupts, quantos eram corretos?
- Alto = menos false positives (menos irritação)
- Target: > 75%

### Recall
De todas as importantes, quantas detectamos?
- Alto = menos missed urgents
- Target: > 85%

## 🔐 Security Features

- ✅ Tenant isolation: Filtro por tenant em todas queries
- ✅ Data validation: Pydantic validators
- ✅ IAM least privilege: Mínimo de permissions
- ✅ TTL cleanup: Auto-delete após 90 dias
- ✅ Encrypted at rest: DynamoDB encryption
- ✅ Log sanitization: Sem PII sensitiva

## 📊 Monitoring

### CloudWatch Metrics
```
Namespace: JaininhoNotificacoes/LearningAgent
MetricName: FeedbackReceived

Dimensions:
- TenantId
- FeedbackType
- WasInterrupted
```

### CloudWatch Logs
```
/aws/lambda/jaiminho-feedback-handler

Contém: timestamp, request_id, tenant, user, feedback_type, success
```

### Alarms (Recomendado)
```
- accuracy < 70% → Alert
- precision < 60% → Alert
- feedback rate anomaly → Alert
```

## 🐛 Troubleshooting

| Problema | Causa | Solução |
|----------|-------|---------|
| "No statistics found" | Sem feedback | Processar feedbacks |
| Latência alta | DynamoDB reads | Normal (<500ms) |
| Feedback não persiste | IAM permissions | Verificar lambda_feedback role |
| DynamoDB throttling | On-demand scaling | Verificar metrics |

## 📚 Documentation

### Completa
- `docs/LEARNING_AGENT.md` - Full documentation

### Deploy
- `LEARNING_AGENT_IMPLEMENTATION.md` - Step-by-step

### Architecture
- `LEARNING_AGENT_ARCHITECTURE.md` - Visual diagrams

### Examples
- `examples/learning_agent_demo.py` - Code example

## 🚀 Next Steps

1. **Review**: Ler docs/LEARNING_AGENT.md
2. **Deploy**: Seguir LEARNING_AGENT_IMPLEMENTATION.md
3. **Test**: Rodar testes e exemplo
4. **Monitor**: Configurar alarms
5. **Collect**: Começar a coletar feedback

## 📞 Help

### Quick Commands

```bash
# Syntax check
python -m py_compile src/jaiminho_notificacoes/processing/learning_agent.py

# Run tests
pytest tests/unit/test_learning_agent.py -v

# Run example
python examples/learning_agent_demo.py

# Check logs (local)
tail -f /tmp/learning_agent.log

# Check DynamoDB (prod)
aws dynamodb scan --table-name jaiminho-feedback --limit 10
```

### Key Files

1. `learning_agent.py` - Core logic
2. `learning_integration.py` - Urgency Agent bridge
3. `process_feedback.py` - Lambda handler
4. `docs/LEARNING_AGENT.md` - Full reference
5. `examples/learning_agent_demo.py` - Example code

---

## ✅ Status: Production Ready

Todos componentes implementados, testados e documentados.

Pronto para: ✅ Deploy
Pronto para: ✅ Production
Pronto para: ✅ Monitoring

**Começar em:** 
1. Review de código
2. Deploy em staging
3. Testes end-to-end
4. Production deploy

---

**Data:** January 2026  
**Version:** 1.0  
**Status:** ✅ COMPLETE
