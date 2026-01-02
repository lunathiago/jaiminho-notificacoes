# Rule Engine de Urgência

## Visão Geral

O **Rule Engine** é um sistema determinístico de classificação de urgência que analisa mensagens usando regex e keywords antes de qualquer processamento via LLM. Ele classifica mensagens como `urgent`, `not_urgent` ou `undecided`, permitindo que 70-80% das mensagens sejam processadas sem custo de inferência.

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                 UrgencyRuleEngine                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────────────────────────┐     │
│  │         KeywordMatcher                   │     │
│  │  • 50+ keywords financeiros              │     │
│  │  • 30+ keywords segurança                │     │
│  │  • 30+ keywords marketing                │     │
│  │  • Regex patterns compilados             │     │
│  └──────────────────────────────────────────┘     │
│                                                     │
│  ┌──────────────────────────────────────────┐     │
│  │   Prioridade de Avaliação (Short-Circuit)│     │
│  │                                            │     │
│  │  1. Mensagem de Grupo    → NOT_URGENT     │     │
│  │  2. Conteúdo Financeiro  → URGENT         │     │
│  │  3. Conteúdo Marketing   → NOT_URGENT     │     │
│  │  4. Conteúdo Segurança   → URGENT         │     │
│  │  5. Vazia/Curta          → NOT_URGENT     │     │
│  │  6. Sem Match            → UNDECIDED      │     │
│  └──────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

## Regras de Classificação

### 1. Mensagens de Grupo (NOT_URGENT)
- **Confidence:** 0.95
- **Lógica:** Mensagens em grupos são raramente urgentes por natureza
- **Exemplo:** Qualquer mensagem onde `is_group=True`

### 2. Conteúdo Financeiro (URGENT)
- **Confidence:** 0.85-0.99 (baseado em número de matches)
- **Keywords:** pix, transferência, pagamento, fatura, boleto, cartão, saldo, débito, crédito, banco, etc.
- **Patterns:**
  - `R$ X,XX` - Valores monetários
  - `XXXX XXXX XXXX XXXX` - Números de cartão
  - `PIX` - Transferências PIX
  - `fatura vence` - Vencimentos
  
**Exemplos:**
```
✅ URGENT: "Sua fatura de R$ 350,00 vence amanhã"
✅ URGENT: "PIX recebido de João Silva - R$ 1.500,00"
✅ URGENT: "Compra no cartão final 1234 - R$ 499,90"
```

### 3. Conteúdo Marketing (NOT_URGENT)
- **Confidence:** 0.75-0.95 (requer 2+ matches)
- **Keywords:** promoção, oferta, desconto, novidade, newsletter, campanha, black friday, cupom, etc.
- **Patterns:**
  - `X% OFF` - Descontos percentuais
  - `até X%` - Descontos
  - `compre X leve Y` - Promoções
  
**Exemplos:**
```
❌ NOT_URGENT: "Promoção Black Friday! 50% de desconto"
❌ NOT_URGENT: "Newsletter Semanal - Novidades da semana"
❌ NOT_URGENT: "Compre 2 e leve 3! Até 60% OFF"
```

### 4. Conteúdo Segurança (URGENT)
- **Confidence:** 0.80-0.99 (baseado em número de matches)
- **Keywords:** senha, token, código, verificação, autenticação, segurança, bloqueio, alerta, suspeito, etc.
- **Patterns:**
  - `\d{4,6}` - Códigos OTP
  - `[A-Z0-9]{6,}` - Tokens alfanuméricos
  - `senha: XXXX` - Credenciais
  - `expira em X minutos` - Urgência temporal
  
**Exemplos:**
```
✅ URGENT: "Seu código de verificação é 456789"
✅ URGENT: "Tentativa de acesso suspeito detectada"
✅ URGENT: "Código para redefinir sua senha: 789012"
```

### 5. Mensagens Vazias/Curtas (NOT_URGENT)
- **Confidence:** 0.70
- **Lógica:** Mensagens com menos de 10 caracteres ou apenas mídia
- **Exemplos:** "", "Ok", "👍", imagens sem caption

### 6. Sem Match (UNDECIDED)
- **Confidence:** 0.0
- **Lógica:** Nenhuma regra determinística aplicável → encaminha para LLM
- **Exemplos:** Conversas normais, perguntas genéricas

## Uso

### Código Básico

```python
from jaiminho_notificacoes.processing.urgency_engine import get_rule_engine
from jaiminho_notificacoes.persistence.models import NormalizedMessage

# Obter instância singleton
engine = get_rule_engine()

# Avaliar mensagem
result = engine.evaluate(message)

# Verificar resultado
if result.decision == UrgencyDecision.URGENT:
    # Processar imediatamente
    process_urgent_message(message)
elif result.decision == UrgencyDecision.NOT_URGENT:
    # Adicionar ao digest
    add_to_digest(message)
else:  # UNDECIDED
    # Enviar para LLM
    llm_result = llm_classify(message)
```

### Estrutura do Resultado

```python
@dataclass
class RuleMatch:
    decision: UrgencyDecision        # urgent | not_urgent | undecided
    rule_name: str                    # Nome da regra aplicada
    confidence: float                 # 0.0 - 1.0
    matched_keywords: List[str]       # Keywords que fizeram match
    reasoning: str                    # Explicação da decisão
```

## Estatísticas e Monitoramento

```python
# Obter estatísticas
stats = engine.get_stats()
print(stats)
# {
#     'total_evaluations': 1000,
#     'urgent_decisions': 150,
#     'not_urgent_decisions': 650,
#     'undecided': 200,
#     'rules_triggered': {
#         'financial_content': 120,
#         'marketing_content': 500,
#         'security_content': 30,
#         ...
#     }
# }

# Resetar estatísticas
engine.reset_stats()
```

## Performance

### Métricas Esperadas
- **Latência:** < 5ms por mensagem
- **Taxa de Determinação:** 70-80% das mensagens
- **False Positives (urgent):** < 5%
- **False Negatives (not_urgent):** < 2%

### Benchmarks
```
Tipo de Mensagem           | Determinação | LLM Necessário
---------------------------|--------------|---------------
Alertas Bancários          | 99%          | 1%
Códigos de Verificação     | 98%          | 2%
Promoções/Marketing        | 95%          | 5%
Newsletters                | 90%          | 10%
Conversas Normais          | 20%          | 80%
```

## Manutenção e Expansão

### Adicionar Novas Keywords

```python
# Em urgency_engine.py, método __init__ do KeywordMatcher

# Financeiro
self.financial_keywords = {
    'pix', 'boleto', 'fatura',
    'nova_keyword',  # ← Adicionar aqui
}

# Segurança
self.security_keywords = {
    'senha', 'token', 'código',
    'outra_keyword',  # ← Adicionar aqui
}

# Marketing
self.marketing_keywords = {
    'promoção', 'desconto', 'oferta',
    'mais_uma',  # ← Adicionar aqui
}
```

### Adicionar Novos Patterns

```python
# No método _compile_patterns()

# Padrão financeiro
self.financial_patterns.append(
    re.compile(r'\bNOVO_PADRAO\b', re.IGNORECASE)
)

# Padrão de segurança
self.security_patterns.append(
    re.compile(r'\d{8}')  # CPF sem formatação, por exemplo
)
```

### Ajustar Confidence Scores

```python
# Em _check_financial(), _check_security(), _check_marketing()

# Aumentar confidence para matches múltiplos
if len(all_matches) > 5:
    confidence = 0.99  # ← Ajustar aqui
elif len(all_matches) > 2:
    confidence = 0.90
else:
    confidence = 0.85
```

## Testes

### Executar Testes

```bash
# Todos os testes
pytest tests/unit/test_urgency_engine.py -v

# Teste específico
pytest tests/unit/test_urgency_engine.py::TestUrgencyRuleEngine::test_financial_message_urgent -v

# Com coverage
pytest tests/unit/test_urgency_engine.py --cov=jaiminho_notificacoes.processing.urgency_engine
```

### Estrutura de Testes

- **TestKeywordMatcher:** Validação de matching de keywords e patterns
- **TestUrgencyRuleEngine:** Testes básicos de cada regra
- **TestSpecificScenarios:** Casos reais (alertas bancários, newsletters, etc.)
- **TestEdgeCases:** Casos limites e ambíguos
- **TestEngineStats:** Estatísticas e tracking

## Integração com Pipeline

```python
# Em lambda_handlers/process_messages.py

from jaiminho_notificacoes.processing.urgency_engine import get_rule_engine

async def process_message(message: NormalizedMessage):
    engine = get_rule_engine()
    
    # 1. Avaliar urgência deterministicamente
    rule_result = engine.evaluate(message)
    
    # 2. Tomar decisão baseada no resultado
    if rule_result.decision == UrgencyDecision.URGENT:
        # Notificar imediatamente
        await send_immediate_notification(message)
        
    elif rule_result.decision == UrgencyDecision.NOT_URGENT:
        # Adicionar ao digest diário
        await add_to_digest_queue(message)
        
    else:  # UNDECIDED
        # Usar LLM para classificação final
        llm_result = await llm_classify(message)
        
        if llm_result.is_urgent:
            await send_immediate_notification(message)
        else:
            await add_to_digest_queue(message)
    
    # 3. Registrar métricas
    await log_classification_metrics(
        message_id=message.message_id,
        rule_decision=rule_result.decision,
        confidence=rule_result.confidence,
        llm_used=(rule_result.decision == UrgencyDecision.UNDECIDED)
    )
```

## Logging e Debugging

```python
# Ativar debug logging
import logging
logging.getLogger('jaiminho_notificacoes.processing.urgency_engine').setLevel(logging.DEBUG)

# Logs gerados:
# DEBUG: Evaluating urgency for message: msg-123 (type=text, has_text=True)
# INFO:  Rule engine decision: urgent (rule=financial_content, confidence=0.95)
```

## Considerações de Design

### Por que Marketing antes de Security?
Promoções frequentemente contêm palavras como "válido até" ou "expira em", que são keywords de segurança. Avaliando marketing primeiro, evitamos false positives para newsletters.

### Por que 2+ matches para Marketing?
Uma única keyword de marketing pode aparecer em contextos urgentes. Exigir 2+ matches garante que a mensagem é predominantemente promocional.

### Por que Groups são automático NOT_URGENT?
Mensagens em grupos geralmente são discussões, coordenação ou avisos gerais, raramente requerendo ação imediata individual.

## Roadmap

### Futuras Melhorias
- [ ] Machine Learning para ajuste automático de confidence scores
- [ ] Detecção de idioma e keywords multilíngues
- [ ] Análise de sentimento para urgência emocional
- [ ] Cache de resultados para mensagens similares
- [ ] Feedback loop: aprender com classificações LLM
- [ ] Detecção de spam/phishing

### Métricas a Coletar
- Taxa de cada regra acionada
- Distribuição de confidence scores
- Tempo de execução por mensagem
- Taxa de LLM fallback
- Feedback de usuários sobre classificações incorretas
