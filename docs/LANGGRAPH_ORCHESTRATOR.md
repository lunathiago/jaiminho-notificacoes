# LangGraph Message Processing Orchestration

## Visão Geral

O **MessageProcessingOrchestrator** é um workflow determinístico baseado em LangGraph que orquestra a classificação de mensagens através de múltiplos agentes, garantindo decisões auditáveis e totalmente scoped por `user_id`.

## Arquitetura do Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                   MESSAGE PROCESSING FLOW                        │
└──────────────────────────────────────────────────────────────────┘

   ┌─────────────────────────┐
   │   NormalizedMessage     │
   │ (validated + tenant OK) │
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────────────────────┐
   │  1. RULE ENGINE (Deterministic)         │
   │  • Grupo? → NOT_URGENT                  │
   │  • Financeiro? → URGENT                 │
   │  • Marketing? → NOT_URGENT              │
   │  • Segurança? → URGENT                  │
   │  • Sem match? → UNDECIDED               │
   └────────────┬────────────────────────────┘
                │
         ┌──────┴──────┐
         │             │
      FINAL        UNDECIDED
    (confident)       │
         │            ▼
         │  ┌─────────────────────────────────┐
         │  │ 2. URGENCY AGENT (LLM)          │
         │  │ • Analyze text semantics        │
         │  │ • Contextual urgency inference  │
         │  │ • Confidence score              │
         │  └────────────┬────────────────────┘
         │               │
         └───────┬───────┘
                 │
                 ▼
   ┌─────────────────────────────────────────┐
   │  3. CLASSIFICATION AGENT (Final Route)  │
   │  • URGENT → "immediate"                 │
   │  • NOT_URGENT → "digest"                │
   │  • Confidence < 0.6 → "digest" (safer)  │
   └────────────┬────────────────────────────┘
                │
                ▼
   ┌─────────────────────────────────────────┐
   │  4. ROUTE DECISION                      │
   │  immediate | digest | spam              │
   └────────────┬────────────────────────────┘
                │
                ▼
   ┌─────────────────────────────────────────┐
   │  5. AUDIT LOG                           │
   │  • Complete trail persisted             │
   │  • DynamoDB + CloudWatch                │
   │  • User-scoped, immutable               │
   └────────────┬────────────────────────────┘
                │
                ▼
   ┌──────────────────────────────────────────────┐
   │  ProcessingResult (Ready for routing)       │
   │  {decision, confidence, audit_trail, ...}   │
   └──────────────────────────────────────────────┘
```

## Estados do Workflow

### ProcessingState

TypedDict que mantém estado durante o workflow:

```python
{
    # Input
    "message": NormalizedMessage,
    
    # Rule Engine Results
    "rule_decision": UrgencyDecision,
    "rule_confidence": float,
    "rule_matched_keywords": list[str],
    "rule_reasoning": str,
    
    # Agent Decisions  
    "urgency_agent_decision": UrgencyDecision,
    "urgency_agent_reasoning": str,
    "urgency_agent_confidence": float,
    
    "classification_agent_decision": str,  # immediate|digest|spam
    "classification_agent_reasoning": str,
    
    # Final Result
    "final_decision": str,
    "audit_trail": list[dict]
}
```

## Nós do Workflow

### 1. Rule Engine Node
- **Entrada:** NormalizedMessage
- **Lógica:** Executa regras determinísticas (regex + keywords)
- **Saída:** decision, confidence, reasoning
- **Skip:** Não (sempre executado)

```python
# Resultado típico:
{
    "rule_decision": "urgent",
    "rule_confidence": 0.95,
    "rule_matched_keywords": ["PIX", "fatura", "vence"],
    "rule_reasoning": "Financial content detected",
    "audit_trail": [{
        "step": "rule_engine",
        "decision": "urgent",
        "confidence": 0.95,
        "rule_name": "financial_content"
    }]
}
```

### 2. Urgency Agent Node
- **Entrada:** message + rule_decision
- **Condição:** Só executa se rule_decision == UNDECIDED
- **Lógica:** Usa LLM para análise semântica/contextual
- **Saída:** decision, confidence, reasoning
- **Skip:** Se rule engine foi decisivo (confident)

```python
# Se já decided:
{
    "urgency_agent_decision": "urgent",  # Cópia de rule_decision
    "urgency_agent_confidence": 0.95,     # Cópia
    "urgency_agent_reasoning": "Skipped - rule engine was decisive",
    "audit_trail": [{
        "step": "urgency_agent",
        "skipped": true,
        "reason": "rule_engine_decisive"
    }]
}

# Se UNDECIDED:
{
    "urgency_agent_decision": "not_urgent",
    "urgency_agent_confidence": 0.72,
    "urgency_agent_reasoning": "Contextual analysis: conversational tone",
    "audit_trail": [{
        "step": "urgency_agent",
        "decision": "not_urgent",
        "confidence": 0.72,
        "llm_called": true
    }]
}
```

### 3. Classification Agent Node
- **Entrada:** urgency_decision + urgency_confidence
- **Lógica:** Mapeia urgency para ação (immediate/digest/spam)
- **Saída:** classification, reasoning

```python
# Mapeamento lógico:
URGENT + conf > 0.8    → "immediate"
NOT_URGENT + conf > 0.8 → "digest"
Conf < 0.6              → "digest" (conservative)

{
    "classification_agent_decision": "immediate",
    "classification_agent_reasoning": "High urgency - send immediately",
    "audit_trail": [{
        "step": "classification_agent",
        "classification": "immediate",
        "urgency_input": "urgent",
        "confidence": 0.95
    }]
}
```

### 4. Route Decision Node
- **Entrada:** classification
- **Lógica:** Confirma decisão final
- **Saída:** final_decision

### 5. Audit Log Node
- **Entrada:** Todos os passos anteriores
- **Lógica:** Compila audit trail completo
- **Saída:** Persiste em DynamoDB (opcional)

## User Scope Guarantees

Todas as decisões são **totalmente scoped por user_id**:

```python
# Contexto tenant + usuário mantido em todos os nós
logger.set_context(
    tenant_id=message.tenant_id,
    user_id=message.user_id,
    message_id=message.message_id
)

# Audit trail inclui user_id
audit_summary = {
    "message_id": message.message_id,
    "tenant_id": message.tenant_id,
    "user_id": message.user_id,  # ← User scoped
    "final_decision": "immediate",
    ...
}

# Todos os logs incluem user_id
logger.info(
    "Processing completed",
    user_id=message.user_id,  # ← Rastreabilidade
    decision=final_decision
)
```

## Auditabilidade Completa

Cada decisão é rastreável através do audit_trail:

```python
{
    "message_id": "msg-12345",
    "tenant_id": "tenant-abc",
    "user_id": "user-xyz",
    "final_decision": "immediate",
    "processing_time_ms": 156,
    "audit_trail": [
        {
            "step": "rule_engine",
            "timestamp": "2024-01-02T10:30:45.123Z",
            "decision": "urgent",
            "confidence": 0.95,
            "rule_name": "financial_content",
            "keyword_count": 3
        },
        {
            "step": "urgency_agent",
            "timestamp": "2024-01-02T10:30:45.124Z",
            "skipped": true,
            "reason": "rule_engine_decisive"
        },
        {
            "step": "classification_agent",
            "timestamp": "2024-01-02T10:30:45.125Z",
            "classification": "immediate",
            "urgency_input": "urgent",
            "confidence": 0.95
        },
        {
            "step": "route_decision",
            "timestamp": "2024-01-02T10:30:45.126Z",
            "final_decision": "immediate"
        },
        {
            "step": "audit_log",
            "timestamp": "2024-01-02T10:30:45.127Z",
            "summary": {...}
        }
    ]
}
```

## Integração

### Com Webhook Handler

```python
from jaiminho_notificacoes.processing.orchestrator import get_orchestrator

async def process_validated_message(message: NormalizedMessage):
    """Main webhook handler."""
    
    # Message already validated for tenant isolation
    orchestrator = get_orchestrator()
    result = await orchestrator.process(message)
    
    # Route based on final decision
    if result.decision == ProcessingDecision.IMMEDIATE:
        await send_immediate_notification(message)
    elif result.decision == ProcessingDecision.DIGEST:
        await add_to_daily_digest(message)
    elif result.decision == ProcessingDecision.SPAM:
        logger.warning(f"Message filtered as spam: {message.message_id}")
    
    # Persist result
    await persist_processing_result(result)
```

### Com SQS

```python
# Message é enriched com ProcessingResult antes de enviar para SQS
message_with_result = {
    "message": message.dict(),
    "processing_result": result.dict(),
    "route": result.decision.value
}

sqs.send_message(
    QueueUrl=ROUTING_QUEUE_URL,
    MessageBody=json.dumps(message_with_result)
)
```

## Performance

### Latência por Nó

- Rule Engine: 2-5ms
- Urgency Agent (LLM): 500-2000ms (only if needed)
- Classification Agent: < 1ms
- Total: 5-10ms (80% casos) ou 500-2000ms (20% com LLM)

### Cache Otimizações

- Rule Engine patterns compilados (regex)
- LLM responses cached por 1 hora
- Tenant resolver com DynamoDB cache

## Tratamento de Erros

### Fallbacks

```
Rule Engine Error        → Conservative NOT_URGENT
Urgency Agent Error      → NOT_URGENT (conservative)
Classification Error     → DIGEST (safe default)
Audit Log Error          → Log warning but continue
```

### Retry Logic

```python
# Builtin exponential backoff (tenacity)
@retry(stop=stop_after_attempt(3), 
       wait=wait_exponential(multiplier=1, min=2, max=10))
async def process(message: NormalizedMessage):
    ...
```

## Monitoramento

### CloudWatch Metrics

```
jaiminho-notificacoes/orchestrator/decisions
├── immediate (tags: user_id, tenant_id)
├── digest
└── spam

jaiminho-notificacoes/orchestrator/llm_usage
├── calls (count)
├── latency_ms (histogram)
└── cost_estimate (sum)

jaiminho-notificacoes/orchestrator/errors
├── rule_engine_errors
├── agent_errors
└── routing_errors
```

### Alertas

- LLM latency > 5s
- Error rate > 1%
- Audit trail write failures
- Cost per message > $0.10
