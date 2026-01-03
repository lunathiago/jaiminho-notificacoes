# Learning Agent - Processamento de Feedback de Usuário

## Visão Geral

O **Learning Agent** é um componente que processa feedback binário de usuários sobre a urgência das mensagens e mantém estatísticas de interrupção agregadas.

**Características principais:**
- ✅ Processa feedback binário (importante / não importante)
- ✅ Atualiza estatísticas em 3 níveis: remetente, categoria, usuário
- ✅ Calcula métricas de acurácia do sistema
- ✅ **SEM machine learning ou fine-tuning**
- ✅ Isolamento total por tenant
- ✅ Auditoria completa de feedback

## Arquitetura

### Fluxo de Processamento

```
┌──────────────────────────────────────────────────────────┐
│         Webhook POST /feedback                           │
│  {                                                       │
│    tenant_id, user_id, message_id,                       │
│    sender_phone, feedback_type,                          │
│    was_interrupted, user_response_time                   │
│  }                                                       │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────┐
│   Lambda: process_feedback.handler                       │
│   - Validar request                                      │
│   - Validar contexto do tenant                           │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────┐
│   LearningAgent.process_feedback()                       │
│   - Criar UserFeedback                                   │
│   - Persistir feedback                                   │
│   - Atualizar estatísticas                               │
└────────────────┬─────────────────────────────────────────┘
                 │
        ┌────────┴────────────┬──────────┬──────────┐
        │                     │          │          │
        ▼                     ▼          ▼          ▼
    Persistir          Atualizar    Atualizar   Atualizar
    Feedback           Sender      Category    User
    (DynamoDB)         Stats       Stats       Stats
    - UserFeedback     - Counts    - Counts    - Counts
    - TTL 90 dias     - Accuracy  - Accuracy  - Metrics
```

### Modelos de Dados

#### 1. UserFeedback (Tabela: jaiminho-feedback)

Armazena cada feedback individual do usuário.

```python
@dataclass
class UserFeedback:
    feedback_id: str              # UUID único
    tenant_id: str                # Isolamento de tenant
    user_id: str                  # Isolamento de usuário
    message_id: str               # ID da mensagem
    sender_phone: str             # Remetente
    sender_name: Optional[str]    # Nome do remetente
    feedback_type: str            # "important" | "not_important"
    message_category: Optional[str]  # "financial", "marketing", etc
    was_interrupted: bool         # Sistema marcou como urgente?
    user_response_time_seconds: Optional[float]  # Tempo de reação
    feedback_timestamp: int       # Unix timestamp
    feedback_reason: Optional[str]  # Justificativa do usuário
    created_at: str              # ISO timestamp
```

**DynamoDB Schema:**
```
PK: FEEDBACK#{tenant_id}#{user_id}
SK: MESSAGE#{timestamp}#{feedback_id}
TTL: 90 dias (permite análise histórica)
```

**GSI:**
- `TenantUserIndex`: Query por tenant e user
- `SenderIndex`: Query por remetente

#### 2. InterruptionStatistics (Tabela: jaiminho-interruption-stats)

Agregações de feedback em 3 níveis.

```python
@dataclass
class InterruptionStatistics:
    tenant_id: str
    user_id: str
    sender_phone: Optional[str]  # None = category ou user level
    category: Optional[str]       # None = sender ou user level

    # Contadores
    total_feedback_count: int
    important_count: int
    not_important_count: int

    # Métricas de Acurácia
    correct_interrupts: int       # ✅ Marcou urgent, usuário confirmou
    incorrect_interrupts: int     # ❌ Marcou urgent, usuário disse não
    correct_digests: int          # ✅ Marcou digest, usuário confirmou
    missed_urgent: int            # ❌ Missed urgent

    # Tempo de Resposta
    avg_response_time_seconds: float
    total_response_time_seconds: float
    response_count: int

    # Janela Temporal
    window_start_timestamp: int   # Início (30 dias)
    window_end_timestamp: int     # Fim (agora)
    last_updated: str
```

**Níveis de Aggregação:**

1. **Nível Sender**: `STATS#{tenant_id}#{user_id}` / `SENDER#{phone}`
   - Estatísticas por remetente específico
   - Usado para contexto do Urgency Agent
   - Atualizado a cada feedback

2. **Nível Category**: `STATS#{tenant_id}#{user_id}` / `CATEGORY#{cat}`
   - Estatísticas por categoria de mensagem
   - Ajuda a entender padrões por tipo
   - Atualizado se categoria fornecida

3. **Nível User**: `STATS#{tenant_id}#{user_id}` / `USER#OVERALL`
   - Estatísticas gerais do usuário
   - Métricas de performance geral
   - Sempre atualizado

**DynamoDB Schema:**
```
PK: STATS#{tenant_id}#{user_id}
SK: SENDER#{phone} | CATEGORY#{cat} | USER#OVERALL
TTL: 90 dias
```

## Métricas Calculadas

### 1. Important Rate
```
important_rate = important_count / (important_count + not_important_count)
```
Percentual de mensagens que o usuário marcou como importantes.

**Interpretação:**
- **< 10%**: Remetente raramente importante
- **10-30%**: Remetente ocasionalmente importante
- **> 30%**: Remetente frequentemente importante

### 2. Accuracy (Acurácia)
```
accuracy = (correct_interrupts + correct_digests) / (total_decisions)
```
Percentual de decisões corretas do sistema.

**Interpretação:**
- **< 70%**: Sistema precisa melhorias
- **70-85%**: Aceitável
- **> 85%**: Excelente

### 3. Precision (Precisão)
```
precision = correct_interrupts / (correct_interrupts + incorrect_interrupts)
```
De todos os interrupts que fizemos, quantos eram realmente importantes?

**Impacto:** Altos falsos positivos irritam usuário.

### 4. Recall (Sensibilidade)
```
recall = correct_interrupts / (correct_interrupts + missed_urgent)
```
De todas as mensagens importantes, quantas detectamos?

**Impacto:** Altos falsos negativos = mensagens importantes perdidas.

## API Webhook

### POST /feedback

Recebe feedback de usuário sobre urgência de mensagem.

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
  "feedback_reason": "Realmente era importante, ótima detecção"
}
```

**Campos:**
- `feedback_type`: `"important"` ou `"not_important"` (obrigatório)
- `was_interrupted`: `true` se sistema marcou como urgente (obrigatório)
- `message_category`: Opcional, ajuda a agregar por tipo
- `user_response_time_seconds`: Opcional, tempo até ação do usuário
- `feedback_reason`: Opcional, justificativa

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Feedback {feedback_id} processed",
  "feedback_id": "{uuid}"
}
```

**Response (400 Bad Request):**
```json
{
  "success": false,
  "message": "Invalid request: ..."
}
```

## Integração com Urgency Agent

O Learning Agent fornece contexto histórico para o Urgency Agent via `HistoricalDataProvider`.

### Fluxo:

```
Urgency Agent precisa classificar mensagem
         │
         ▼
HistoricalDataProvider.get_sender_context()
         │
         ├─→ DynamoDB: Buscar stats do remetente
         │
         └─→ Retorna HistoricalInterruptionData
                      │
                      ├─ total_messages: 45
                      ├─ urgent_count: 9
                      ├─ urgency_rate: 20%
                      ├─ avg_response_time: 2.5 min
                      └─ user_feedback_count: 45

Urgency Agent:
  - Inclui histórico no prompt do LLM
  - Se "taxa histórica < 10%" → mais conservador
  - Se "primeiro contato" → requer confiança 0.85+
  - Se "taxa > 50%" → pode usar threshold mais baixo
```

### Dados Disponíveis para Contexto:

```python
# Informações do remetente
- total_messages: Quantas mensagens desta fonte
- urgent_count: Quantas confirmadas como urgentes
- not_urgent_count: Quantas confirmadas como não urgentes
- urgency_rate: Taxa de urgência (%)
- avg_response_time_seconds: Tempo médio de resposta

# Informações da categoria
- total_messages por categoria
- urgent_count por categoria
- urgency_rate por categoria

# Performance geral
- accuracy: Acurácia do sistema
- precision: Quantas interrupções eram certas
- recall: Quantas importâncias detectamos
```

## Banco de Dados

### DynamoDB Tables

#### 1. jaiminho-feedback
- **Propósito:** Armazenar cada feedback individual
- **Partition Key:** PK (FEEDBACK#{tenant}#{user})
- **Sort Key:** SK (MESSAGE#{timestamp}#{id})
- **TTL:** 90 dias
- **GSI:** TenantUserIndex, SenderIndex

#### 2. jaiminho-interruption-stats
- **Propósito:** Agregações para contexto
- **Partition Key:** PK (STATS#{tenant}#{user})
- **Sort Key:** SK (SENDER#{phone} | CATEGORY#{cat} | USER#OVERALL)
- **TTL:** 90 dias
- **GSI:** TenantUserIndex

### Capacidade

- Ambas em modo **PAY_PER_REQUEST** (on-demand)
- Sem limite de capacidade
- Escala automaticamente

### Retenção

- Feedback mantido por **90 dias** (TTL)
- Estatísticas mantidas por **90 dias** (TTL)
- Permite análise histórica sem crescimento indefinido

## Exemplo de Uso

### Processamento de Feedback

```python
from src.jaiminho_notificacoes.processing.learning_agent import (
    LearningAgent,
    FeedbackType,
)

agent = LearningAgent()

# Usuário marcou como importante
success, message = await agent.process_feedback(
    tenant_id="tenant-001",
    user_id="user-001",
    message_id="msg-12345",
    sender_phone="5511987654321",
    sender_name="Maria",
    feedback_type=FeedbackType.IMPORTANT,
    was_interrupted=True,  # Sistema já havia marcado como urgente ✅
    message_category="financial",
    user_response_time_seconds=15.0,
)
# Resultado: correct_interrupts += 1
```

### Retrieving Context

```python
from src.jaiminho_notificacoes.processing.learning_integration import (
    HistoricalDataProvider,
)

provider = HistoricalDataProvider()

# Get sender context
context = await provider.generate_historical_context_prompt(
    tenant_id="tenant-001",
    user_id="user-001",
    sender_phone="5511987654321",
    category="financial",
)
# Returns text like:
# "HISTÓRICO:
#  Remetente: 45 mensagens, 20% importantes
#  Categoria Financial: 12 mensagens, 35% importantes"
```

## Segurança

### Tenant Isolation
- Todos os dados são particionados por `tenant_id`
- Query sempre inclui filtro de tenant
- Impossível acessar dados de outro tenant

### User Privacy
- Feedback é scoped a `user_id`
- Um usuário vê apenas seu feedback
- TTL de 90 dias garante limpeza automática

### Data Validation
- Pydantic valida todos os inputs
- Phone numbers validados
- Feedback type é enum (apenas 2 valores)

## Monitoramento

### CloudWatch Metrics

```
JaininhoNotificacoes/LearningAgent/FeedbackReceived
- MetricName: FeedbackReceived
- Dimensions:
  - TenantId
  - FeedbackType (important | not_important)
  - WasInterrupted (true | false)
```

### Logs

```
INFO: "Feedback processed successfully"
  - feedback_id
  - tenant_id
  - user_id
  - feedback_type
  - was_interrupted

WARNING: "Failed to update statistics"
  - reason
  - feedback_id
```

## Troubleshooting

### Problema: "No statistics found"
**Causa:** Nenhum feedback foi processado para esta combinação
**Solução:** Processar alguns feedbacks primeiro

### Problema: Latência alta ao processar feedback
**Causa:** Leitura de DynamoDB ao update de stats
**Solução:** Normal (consistent reads habilitados)

### Problema: Feedback não persiste
**Causa:** Permissões IAM insuficientes
**Solução:** Verificar role `lambda-feedback` tem `dynamodb:PutItem`

## Limitações Atuais

1. **Sem ML:** Apenas agregação e cálculo de métricas
2. **Sem recomendações automáticas:** Apenas fornece dados ao Urgency Agent
3. **Sem detecção de anomalias:** Não detecta padrões anormais automaticamente
4. **Sem feedback on feedback:** Não há mecanismo de "você acertou ao marcar"

## Roadmap Futuro

- [ ] Detectar anomalias em padrões de feedback
- [ ] Sugerir ajustes de threshold ao Urgency Agent
- [ ] API de analytics para dashboard
- [ ] Modelo de feedback em cascata (mais detalhado)
- [ ] A/B testing de estratégias
- [ ] Feedback com score (0-10) em vez de binário
