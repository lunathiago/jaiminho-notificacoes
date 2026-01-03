# Classification Agent - Documentação

## Visão Geral

O **Classification Agent** é um agente LLM inteligente responsável por:
- ✅ Atribuir **categorias cognitivas** amigáveis às mensagens
- ✅ Gerar **resumos curtos** (1-2 frases) para digest diário
- ✅ Determinar **roteamento final** (immediate/digest/spam)
- ✅ **NUNCA** usar dados cross-user (isolamento total de tenant)

## Características Principais

### 1. Categorias Cognitivas

O agente utiliza categorias com emojis para facilitar o reconhecimento visual:

- 💼 **Trabalho e Negócios** - Reuniões, projetos, contratos
- 👨‍👩‍👧 **Família e Amigos** - Mensagens pessoais
- 📦 **Entregas e Compras** - Rastreio, pedidos, compras online
- 💰 **Financeiro** - Pagamentos, boletos, PIX
- 🏥 **Saúde** - Consultas, exames, medicamentos
- 🎉 **Eventos e Convites** - Festas, celebrações
- 📰 **Informação Geral** - Notícias, informações diversas
- 🤖 **Automação e Bots** - Mensagens automáticas
- ❓ **Outros** - Categoria padrão quando nada se aplica

### 2. Geração de Resumos

Resumos são criados seguindo diretrizes específicas:
- **Comprimento**: Máximo 150 caracteres
- **Formato**: "Nome do Remetente: [essência da mensagem]"
- **Estilo**: Natural, objetivo, útil para digest
- **Exemplos**:
  - "João: Reunião confirmada para amanhã às 14h"
  - "Correios: Sua encomenda foi enviada e chega em 2 dias"
  - "Grupo Família: Discussão sobre churrasco no sábado"

### 3. Roteamento Inteligente

O agente determina o destino final da mensagem:

| Decisão | Quando | Destino |
|---------|--------|---------|
| `immediate` | Alta urgência + confiança > 0.75 | SendPulse (notificação imediata) |
| `digest` | Não urgente ou baixa confiança | Digest diário por email |
| `spam` | Mensagens promocionais/spam | Filtrado (não entregue) |

**Lógica de Negócio**:
- Se urgência é URGENT e confiança > 0.75 → `immediate`
- Se urgência é NOT_URGENT → `digest`
- Se confiança < 0.5 → `digest` (conservador)
- Em caso de dúvida → `digest` (nunca interromper desnecessariamente)

### 4. Isolamento de Tenant (Segurança)

**CRÍTICO**: O agente NUNCA usa dados de outros usuários.

Validações implementadas:
```python
def _validate_tenant_isolation(self, message):
    if not message.tenant_id or not message.user_id:
        raise ValueError("ClassificationAgent requires tenant_id and user_id")
```

O que o agente **PODE** usar:
- ✅ Conteúdo da mensagem atual
- ✅ Metadados da mensagem (remetente, timestamp, tipo)
- ✅ Configurações do tenant (não dados de usuários)

O que o agente **NUNCA** usa:
- ❌ Histórico de outros usuários
- ❌ Padrões agregados cross-tenant
- ❌ Dados de comportamento de outros usuários

## Arquitetura

### Fluxo de Processamento

```
┌─────────────────────┐
│  Mensagem +         │
│  Decisão Urgência   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────┐
│  ClassificationAgent.run()  │
│  1. Valida isolamento        │
│  2. Constrói prompt          │
│  3. Chama LLM                │
│  4. Parseia resposta         │
│  5. Aplica regras negócio    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────┐
│ ClassificationResult │
│ - category           │
│ - summary            │
│ - routing            │
│ - reasoning          │
│ - confidence         │
└─────────────────────┘
```

### Integração com Orchestrator

O Classification Agent é o **último estágio** do pipeline de processamento:

```
Rule Engine → Urgency Agent → Classification Agent → Router
```

O orchestrator atualiza o estado com todas as informações:
```python
state["classification_result"] = result
state["classification_category"] = result.category
state["classification_summary"] = result.summary
state["classification_routing"] = result.routing
state["classification_reasoning"] = result.reasoning
```

## Uso

### Exemplo Básico

```python
from jaiminho_notificacoes.processing.agents import (
    get_classification_agent,
    ClassificationResult
)
from jaiminho_notificacoes.processing.urgency_engine import UrgencyDecision

# Obter agente (singleton)
agent = get_classification_agent()

# Classificar mensagem
result: ClassificationResult = await agent.run(
    message=normalized_message,
    urgency_decision=UrgencyDecision.NOT_URGENT,
    urgency_confidence=0.8
)

# Usar resultado
print(f"Categoria: {result.category}")
print(f"Resumo: {result.summary}")
print(f"Roteamento: {result.routing}")
print(f"Confiança: {result.confidence}")
```

### Exemplo com Orchestrator

```python
from jaiminho_notificacoes.processing.orchestrator import get_orchestrator

# Processar mensagem completa
orchestrator = get_orchestrator()
result = await orchestrator.process(normalized_message)

# Acessar classificação do estado
print(f"Categoria: {result.audit_trail[-2]['category']}")
print(f"Resumo: {result.audit_trail[-2]['summary']}")
```

## Testes

### Executar Testes

```bash
# Todos os testes do Classification Agent
pytest tests/unit/test_classification_agent.py -v

# Teste específico
pytest tests/unit/test_classification_agent.py::TestClassificationAgent::test_category_assignment_work -v

# Com cobertura
pytest tests/unit/test_classification_agent.py --cov=jaiminho_notificacoes.processing.agents
```

### Cobertura de Testes

Os testes cobrem:
- ✅ Inicialização do agente
- ✅ Validação de isolamento de tenant
- ✅ Atribuição de categorias (9 categorias)
- ✅ Geração de resumos
- ✅ Lógica de roteamento
- ✅ Regras de negócio (overrides)
- ✅ Fallback em caso de erro
- ✅ Parsing de respostas (válidas e inválidas)
- ✅ Serialização JSON
- ✅ Segurança (sem cross-user data)

**Total**: 20 testes, 100% passando

## Configuração

### Variáveis de Ambiente

```bash
# API Key para OpenAI (opcional - tem fallback inteligente)
export OPENAI_API_KEY="sk-..."

# Modelo LLM (padrão: gpt-4)
export LLM_MODEL="gpt-4"
```

### Fallback sem API Key

Quando `OPENAI_API_KEY` não está configurada, o agente usa um **fallback inteligente** baseado em análise de palavras-chave:

- ✅ Classifica categorias via pattern matching
- ✅ Gera resumos baseados em conteúdo
- ✅ Mantém funcionalidade completa
- ✅ Perfeito para desenvolvimento e testes

## Boas Práticas

### 1. Sempre Validar Tenant

```python
# ✅ BOM - Mensagem com tenant_id e user_id
message = NormalizedMessage(
    tenant_id="tenant_123",
    user_id="user_456",
    # ... outros campos
)

# ❌ MAU - Faltando tenant_id
message = NormalizedMessage(
    tenant_id="",  # Vai falhar!
    user_id="user_456",
    # ...
)
```

### 2. Usar Resultado Completo

```python
# ✅ BOM - Usar objeto completo
result = await agent.run(...)
store_in_db(
    category=result.category,
    summary=result.summary,
    routing=result.routing,
    confidence=result.confidence
)

# ❌ MAU - Ignorar informações importantes
routing = await agent.run(...)  # Perde category, summary, etc.
```

### 3. Tratar Erros Adequadamente

```python
# ✅ BOM - Try/catch com fallback
try:
    result = await agent.run(message, urgency, confidence)
except Exception as e:
    logger.error(f"Classification failed: {e}")
    # O agente já tem fallback interno, mas você pode adicionar lógica extra
```

## Performance

### Métricas Esperadas

- **Latência**: 100-300ms (sem API key) / 500-1500ms (com LLM)
- **Throughput**: Limitado pela API do LLM (~10-50 req/s)
- **Precisão**: 85-95% (depende do LLM usado)

### Otimizações

1. **Caching**: Mensagens idênticas podem ser cacheadas
2. **Batching**: Processar múltiplas mensagens em lote
3. **Async**: Sempre usar `await` para non-blocking I/O

## Próximos Passos

### Melhorias Futuras

1. **Fine-tuning**: Treinar modelo específico para categorização
2. **Multi-idioma**: Suporte completo para inglês, espanhol, etc.
3. **Feedback Loop**: Usar feedback do usuário para melhorar
4. **A/B Testing**: Testar diferentes prompts e modelos
5. **Cache Inteligente**: Redis cache para respostas recentes

### Integração com Digest Generator

O Classification Agent alimenta o Digest Generator com:
- **Categorias**: Para agrupar mensagens por tipo
- **Resumos**: Para exibir no email de digest
- **Prioridade**: Baseado em confidence scores

```python
# Exemplo de uso no Digest Generator
messages_by_category = {}
for msg in messages:
    category = msg.classification_category
    if category not in messages_by_category:
        messages_by_category[category] = []
    messages_by_category[category].append({
        'summary': msg.classification_summary,
        'sender': msg.sender_name,
        'timestamp': msg.timestamp
    })

# Renderizar digest agrupado por categoria
```

## Referências

- [agents.py](../src/jaiminho_notificacoes/processing/agents.py) - Implementação
- [orchestrator.py](../src/jaiminho_notificacoes/processing/orchestrator.py) - Integração
- [test_classification_agent.py](../tests/unit/test_classification_agent.py) - Testes
- [ARCHITECTURE.md](ARCHITECTURE.md) - Arquitetura geral
- [TENANT_ISOLATION.md](TENANT_ISOLATION.md) - Segurança multi-tenant
