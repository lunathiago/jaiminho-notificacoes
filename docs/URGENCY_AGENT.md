# Urgency Agent - Documentação

## Visão Geral

O **Urgency Agent** é um componente inteligente do sistema Jaiminho Notificações que decide se uma mensagem é importante o suficiente para interromper o usuário imediatamente.

## Filosofia: Conservador por Padrão

O agente segue uma filosofia **conservadora**: quando há dúvida, **NÃO interrompe** o usuário. Interrupções são invasivas e devem ser reservadas apenas para situações genuinamente urgentes.

## Inputs

O Urgency Agent recebe os seguintes dados de entrada:

1. **Conteúdo da mensagem**: Texto completo da mensagem
2. **Número do remetente**: Telefone de quem enviou
3. **Contexto do chat**: Se é grupo ou privado
4. **Dados históricos de interrupção**: Estatísticas do mesmo remetente (somente do usuário atual)

## Output (JSON)

```json
{
  "urgent": boolean,      // true se deve interromper, false caso contrário
  "reason": string,       // Explicação clara em português
  "confidence": float     // Confiança na decisão (0.0 a 1.0)
}
```

## Arquitetura

### 1. Análises Rápidas (Short-circuit)

Antes de chamar o LLM, o agente faz verificações rápidas:

- **Mensagens vazias/curtas** (<5 caracteres): Sempre não urgente
- **Mensagens de grupo**: Sempre não urgente (por padrão)
- Essas análises têm confiança alta (≥0.85)

### 2. Busca de Dados Históricos

O agente busca informações sobre o remetente:

```python
@dataclass
class HistoricalInterruptionData:
    sender_phone: str
    total_messages: int                    # Total de mensagens deste remetente
    urgent_count: int                      # Quantas foram urgentes
    not_urgent_count: int                  # Quantas foram não urgentes
    avg_response_time_seconds: float       # Tempo médio de resposta
    last_urgent_timestamp: int             # Última mensagem urgente
    user_feedback_count: int               # Feedback explícito do usuário
```

### 3. Classificação via LLM

Se necessário, chama um LLM (GPT-4, Claude, etc.) com um prompt estruturado que inclui:

- Metadados da mensagem
- Conteúdo (primeiros 800 caracteres)
- Dados históricos formatados
- Critérios rigorosos de urgência
- Instruções para ser conservador

### 4. Lógica Conservadora Pós-LLM

Mesmo que o LLM sugira urgência, o agente aplica filtros adicionais:

#### Limiar de Confiança
- **Geral**: Confiança ≥ 0.75 para interromper
- **Remetente conhecido** (≥5 mensagens): Confiança ≥ 0.65
- **Primeiro contato**: Confiança ≥ 0.85 (muito conservador)

#### Regras Específicas

1. **Primeiro Contato**
   - Requer confiança ≥ 0.85
   - Exceção: Códigos de segurança muito óbvios
   
2. **Baixa Taxa Histórica de Urgência** (<10%)
   - Se o remetente historicamente envia poucas mensagens urgentes
   - Requer confiança ≥ 0.85
   
3. **Mensagens de Grupo**
   - Requer confiança ≥ 0.90 (bar muito alto)
   - Raramente interrompe para grupos

4. **Tratamento de Erros**
   - Qualquer erro → sempre retorna `urgent: false`
   - Confiança reduzida (≤0.5)

## Critérios de Urgência

### ✅ URGENTE (deve interromper)

- Alertas financeiros **CRÍTICOS**:
  - Fraude detectada
  - Conta bloqueada
  - Transação suspeita grande
  
- Códigos de verificação/autenticação:
  - Com prazo curto (<15 minutos)
  - Para ações sensíveis
  
- Emergências genuínas:
  - Saúde, segurança
  - Problemas graves
  
- Comunicação sensível ao tempo:
  - Reunião em 15 minutos
  - Prazo expirando hoje
  - Confirmação que expira rapidamente

### ❌ NÃO URGENTE (pode esperar)

- Marketing, promoções, ofertas
- Mensagens informativas gerais
- Conversas casuais
- Confirmações de ações já realizadas
- Lembretes sem prazo imediato
- Mensagens de grupo (exceto emergências óbvias)
- **Primeiro contato de remetente desconhecido** (ser cauteloso)

## Exemplo de Uso

```python
import asyncio
from jaiminho_notificacoes.processing.agents import (
    UrgencyAgent,
    HistoricalInterruptionData
)

async def classify_message():
    # Criar agente
    agent = UrgencyAgent()
    
    # Criar mensagem (NormalizedMessage)
    message = create_message(
        text="ALERTA: Transação suspeita de R$ 5.000,00",
        sender_phone="5511999999999"
    )
    
    # Dados históricos (opcional)
    history = HistoricalInterruptionData(
        sender_phone="5511999999999",
        total_messages=15,
        urgent_count=12,
        not_urgent_count=3
    )
    
    # Classificar
    result = await agent.run(message, history)
    
    print(f"Urgente: {result.urgent}")
    print(f"Razão: {result.reason}")
    print(f"Confiança: {result.confidence:.2f}")
    
    # Output JSON
    json_output = result.to_json()
    # {
    #   "urgent": true,
    #   "reason": "Alerta financeiro crítico detectado",
    #   "confidence": 0.95
    # }

asyncio.run(classify_message())
```

## Integração com Rule Engine

O Urgency Agent trabalha em conjunto com o Rule Engine:

1. **Rule Engine** (determinístico, rápido):
   - Verifica padrões óbvios
   - Keywords financeiras, de segurança, marketing
   - Retorna `URGENT`, `NOT_URGENT` ou `UNDECIDED`

2. **Urgency Agent** (LLM, mais lento):
   - Chamado apenas quando Rule Engine retorna `UNDECIDED`
   - Analisa casos ambíguos
   - Aplica inteligência contextual

## Fluxo Completo

```
Mensagem
    ↓
Rule Engine
    ↓
┌───────────────────────┐
│  URGENT?              │
├───────────────────────┤
│  ✓ Sim → Interromper  │
│  ✗ Não → Digest       │
│  ? Indeciso → ↓       │
└───────────────────────┘
    ↓
Urgency Agent (LLM)
    ↓
┌───────────────────────┐
│  Análise Contextual   │
│  + Dados Históricos   │
│  + Lógica Conservadora│
└───────────────────────┘
    ↓
Decisão Final
```

## Métricas e Monitoramento

### Métricas Importantes

- **Taxa de interrupção geral**: % de mensagens marcadas como urgentes
- **Taxa de interrupção por remetente**: Histórico de cada contato
- **Confiança média**: Distribuição de confiança nas decisões
- **Uso de LLM**: % de mensagens que precisaram do LLM
- **Tempo de resposta**: Latência média da classificação

### Logs Estruturados

```python
logger.info(
    "Urgency agent decision",
    urgent=result.urgent,
    confidence=result.confidence,
    sender=message.sender_phone,
    has_history=bool(historical_data),
    llm_used=True
)
```

## Configuração

### Variáveis de Ambiente

```bash
# API Key para LLM (OpenAI, Anthropic, etc.)
OPENAI_API_KEY=sk-...

# Opcional: Modelo a usar
URGENCY_AGENT_MODEL=gpt-4  # default: gpt-4
```

### Thresholds Configuráveis

No código, você pode ajustar:

```python
class UrgencyAgent:
    CONFIDENCE_THRESHOLD_URGENT = 0.75           # Geral
    CONFIDENCE_THRESHOLD_KNOWN_SENDER = 0.65     # Remetente conhecido
    CONFIDENCE_THRESHOLD_FIRST_CONTACT = 0.85    # Primeiro contato (não configurável atualmente)
    CONFIDENCE_THRESHOLD_GROUP = 0.90            # Grupo (não configurável atualmente)
```

## Testes

### Executar Testes Unitários

```bash
pytest tests/unit/test_urgency_agent.py -v
```

### Executar Demo

```bash
python examples/urgency_agent_demo.py
```

## Limitações Conhecidas

1. **Dados Históricos**: Atualmente retorna vazio (TODO: integrar com DynamoDB)
2. **Chamada LLM**: Usa mock em desenvolvimento (TODO: integrar OpenAI/Claude)
3. **Contexto Limitado**: Apenas mensagem atual (futuro: thread completa)
4. **Idioma**: Otimizado para português brasileiro
5. **Multi-modal**: Apenas texto (futuro: imagens, áudio)

## Roadmap

- [ ] Integração com DynamoDB para dados históricos reais
- [ ] Implementação de chamadas LLM reais (OpenAI/Claude)
- [ ] Suporte a contexto de conversa (últimas N mensagens)
- [ ] Análise de imagens (OCR + Vision API)
- [ ] Feedback loop: aprender com correções do usuário
- [ ] A/B testing de diferentes prompts
- [ ] Cache de decisões para mensagens similares
- [ ] Suporte a múltiplos idiomas

## Segurança e Privacidade

- ✅ **Isolamento por tenant**: Cada usuário vê apenas seus dados
- ✅ **Dados históricos isolados**: Sem cross-contamination
- ✅ **Sem compartilhamento de dados**: Cada análise é independente
- ✅ **Logs auditáveis**: Todas as decisões são registradas
- ⚠️ **Atenção**: Dados enviados para LLM externo (OpenAI/Claude)
  - Considere usar deployment privado para dados sensíveis
  - Implemente data masking para informações críticas

## Suporte

Para dúvidas ou problemas:
- Consulte os testes: `tests/unit/test_urgency_agent.py`
- Execute o exemplo: `examples/urgency_agent_demo.py`
- Veja logs: `logger.info/error` com contexto estruturado

---

**Última atualização**: Janeiro 2026  
**Versão**: 1.0.0
