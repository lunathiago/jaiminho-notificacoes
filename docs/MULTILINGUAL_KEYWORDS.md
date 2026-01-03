# Suporte Multilíngue - Keywords e Patterns

## Visão Geral

O Rule Engine agora suporta classificação de mensagens em **três idiomas**:
- 🇧🇷 **Português Brasileiro (PT-BR)** - Idioma padrão
- 🇪🇸 **Espanhol (ES)** - Principais variantes de América Latina e Espanha
- 🇬🇧 **Inglês (EN)** - Variante internacional

## Arquitetura de Suporte Multilíngue

### Keywords Structure

Cada categoria de keywords (financial, security, marketing) contém termos em todos os 3 idiomas:

```python
self.financial_keywords = {
    # Banking - Portuguese
    'banco', 'conta', 'saldo', 'transferência', 'pix', 'ted', 'doc',
    'cartão', 'crédito', 'débito', 'fatura', 'boleto', 'pagamento',
    
    # Banking - English
    'bank', 'account', 'balance', 'transfer', 'card', 'credit', 'debit',
    'invoice', 'payment', 'banking',
    
    # Banking - Spanish
    'banco', 'cuenta', 'saldo', 'transferencia', 'tarjeta', 'crédito',
    'débito', 'factura', 'pago', 'pagos',
    
    # ... (Transactions, Currency, Fraud sections similarly organized)
}
```

### Regex Patterns

Padrões regex foram expandidos para capturar estruturas multilíngues:

```python
# Financial patterns (PT-BR, EN, ES)
self.financial_patterns: List[Pattern] = [
    re.compile(r'[R$€£¥¢₹₽]\s*[\d.,]+', re.IGNORECASE),  # Símbolos de moeda
    re.compile(r'[\d.,]+\s*(?:reais|dólares|euros|pesos|euros)', re.IGNORECASE),
    # PT-BR patterns
    re.compile(r'\b(?:transferência|transfer|pago|pagamento)\s+(?:de|no valor|de\s*r\$)', re.IGNORECASE),
    # EN patterns
    re.compile(r'\b(?:transfer|payment|invoice)\s+(?:of|in|amount)', re.IGNORECASE),
    # ES patterns
    re.compile(r'\b(?:transferencia|pago|factura)\s+(?:de|en|cantidad)', re.IGNORECASE),
]
```

## Keywords por Categoria

### 1. Financial Keywords (129 termos)

#### Banking
- **PT-BR**: banco, conta, saldo, transferência, pix, ted, doc, cartão, crédito, débito, fatura, boleto, pagamento
- **EN**: bank, account, balance, transfer, card, credit, debit, invoice, payment, banking
- **ES**: banco, cuenta, saldo, transferencia, tarjeta, crédito, débito, factura, pago, pagos

#### Transactions
- **PT-BR**: transação, compra, cobrança, estorno, aprovado, negado, pendente, processando
- **EN**: transaction, purchase, charge, refund, approved, denied, pending, processing
- **ES**: transacción, compra, cobro, devolución, aprobado, negado, pendiente, procesando

#### Currency
- **Symbols**: R$, $, €, £, ¥, ¢, ₹, ₽
- **Codes**: BRL, USD, EUR, MXN, ARS, CLP, COP, EUR

#### Fraud & Security
- **PT-BR**: fraude, suspeito, bloqueio, bloqueado, tentativa, acesso não autorizado, roubo, furto
- **EN**: fraud, suspicious, blocked, attempt, unauthorized access, theft
- **ES**: fraude, sospechoso, bloqueado, intento, acceso no autorizado, robo, hurto

### 2. Security Keywords (88 termos)

#### Authentication
- **PT-BR**: senha, código, autenticação, verificação, verificar, confirmar, confirmação, token, 2fa, otp
- **EN**: password, code, authentication, verification, verify, confirm, confirmation, token, 2fa, otp
- **ES**: contraseña, código, autenticación, verificación, verificar, confirmar, confirmación, token, 2fa

#### Alerts
- **PT-BR**: alerta, aviso, emergência, urgente, crítico, importante, atenção, ação requerida, ação necessária, risco
- **EN**: alert, warning, emergency, urgent, critical, important, attention, action required, risk, immediately
- **ES**: alerta, advertencia, emergencia, urgente, crítico, importante, atención, acción requerida, riesgo

#### Expiration
- **PT-BR**: expira, expiração, vence, vencimento, válido, válidade, prazo, prazo limite
- **EN**: expires, expiration, valid, validity, deadline, time limit
- **ES**: expira, expiración, vence, vencimiento, válido, validez, plazo, límite de tiempo

### 3. Marketing Keywords (98 termos)

#### Promotions
- **PT-BR**: promoção, oferta, desconto, novidade, lançamento, newsletter, campanha, anúncio
- **EN**: promotion, offer, discount, news, launch, newsletter, campaign, advertisement
- **ES**: promoción, oferta, descuento, novedad, lanzamiento, boletín, campaña, anuncio

#### Time-Limited Offers
- **PT-BR**: aproveite, não perca, black friday, cyber monday, liquidação, cupom, voucher, grátis
- **EN**: take advantage, don't miss, black friday, cyber monday, sale, coupon, voucher, free
- **ES**: aproveche, no pierda, viernes negro, cyber lunes, liquidación, cupón, bono, gratis

#### Engagement
- **PT-BR**: confira, clique aqui, saiba mais, conheça, exclusivo, limitado, apenas hoje, enquanto durar
- **EN**: check out, click here, learn more, exclusive, limited, today only, while stocks last
- **ES**: revisa, haz clic aquí, aprende más, exclusivo, limitado, solo hoy, mientras exista

## Regex Patterns Compilados

### Financial Patterns (12 patterns)
```
1. [R$€£¥¢₹₽]\s*[\d.,]+         → Símbolos monetários com valores
2. [\d.,]+\s*(?:reais|dólares)   → Nomes de moedas em texto
3. \d{4}\s*\d{4}\s*\d{4}\s*\d{4}  → Números de cartão
4. \bPIX\b                        → PIX (padrão PT-BR)
5. transferência.*de valor        → Padrão PT-BR de transferência
6. transfer.*amount               → Padrão EN de transferência
7. transferencia.*cantidad        → Padrão ES de transferência
8. fatura.*vence                  → Vencimento de fatura PT-BR
9. bill.*due                      → Vencimento EN
10. factura.*vencido              → Vencimento ES
11. invoice.*updated              → Atualização EN
12. cobro.*actualizado            → Atualização ES
```

### Security Patterns (11 patterns)
```
1. \b\d{4,8}\b                    → Códigos OTP (4-8 dígitos)
2. \b[A-Z0-9]{6,}\b               → Tokens alfanuméricos
3. (?:senha|código)=\w+           → Padrão PT-BR de senha/código
4. (?:password|code)=\w+          → Padrão EN
5. (?:contraseña|código)=\w+      → Padrão ES
6. expira.*em                     → Expiração PT-BR
7. expires.*in                    → Expiração EN
8. expira.*en                     → Expiração ES
9. confirme.*sua                  → Confirmação PT-BR
10. confirm.*your                 → Confirmação EN
11. confirma.*su                  → Confirmação ES
```

### Marketing Patterns (9 patterns)
```
1. \b\d+%\s*(?:OFF|DESCONTO)      → Desconto percentual PT-BR
2. até\s+\d+%                     → "Até X%" PT-BR
3. up\s+to\s+\d+%                 → "Up to X%" EN
4. hasta\s+\d+%                   → "Hasta X%" ES
5. compre\s+\d+\s+leve\s+\d+     → "Compre X leve Y" PT-BR
6. buy\s+\d+\s+get\s+\d+         → "Buy X get Y" EN
7. compra\s+\d+\s+lleva\s+\d+    → "Compra X lleva Y" ES
8. não perca|don't miss|no pierda → Urgência de tempo
9. apenas hoje|today only|solo hoy → Oferta por tempo limitado
```

## Exemplos de Classificação Multilíngue

### Exemplo 1: Transferência Bancária

**PT-BR**: "Transferência de R$ 500,00 aprovada para João Silva"
- ✅ Matches: R$, 500,00, transferência, aprovado
- **Decision**: URGENT (0.95)

**EN**: "Bank transfer of $500.00 approved for John Smith"
- ✅ Matches: $, 500.00, transfer, approved
- **Decision**: URGENT (0.95)

**ES**: "Transferencia de $500,00 aprobada para Juan García"
- ✅ Matches: $, 500,00, transferencia, aprobado
- **Decision**: URGENT (0.95)

### Exemplo 2: Alerta de Segurança

**PT-BR**: "Alerta: Tentativa de acesso não autorizado detectada. Confirme sua identidade aqui"
- ✅ Matches: alerta, tentativa, acesso não autorizado, confirme
- **Decision**: URGENT (0.92)

**EN**: "Alert: Unauthorized access attempt detected. Confirm your identity now"
- ✅ Matches: alert, unauthorized, access, confirm
- **Decision**: URGENT (0.92)

**ES**: "Alerta: Intento de acceso no autorizado detectado. Confirma tu identidad aquí"
- ✅ Matches: alerta, intento, acceso no autorizado, confirma
- **Decision**: URGENT (0.92)

### Exemplo 3: Oferta de Marketing

**PT-BR**: "Não perca! Até 50% OFF em todos os produtos. Apenas hoje!"
- ✅ Matches: não perca, 50%, desconto, apenas hoje (2+ matches)
- **Decision**: NOT_URGENT (0.85)

**EN**: "Don't miss! Up to 50% OFF on all products. Today only!"
- ✅ Matches: don't miss, 50%, off, today only (2+ matches)
- **Decision**: NOT_URGENT (0.85)

**ES**: "¡No pierda! Hasta 50% de descuento en todos los productos. ¡Solo hoy!"
- ✅ Matches: no pierda, 50%, descuento, solo hoy (2+ matches)
- **Decision**: NOT_URGENT (0.85)

## Performance com Multilíngue

### Latência Esperada
- **Keyword matching**: 2-4ms (mesmo com 3 idiomas)
- **Regex patterns**: 1-3ms (10 patterns compilados por categoria)
- **Total Rule Engine**: 3-7ms (sem impacto significativo)

### Coverage por Idioma
- **PT-BR**: ~100 keywords + 12 financial patterns + 11 security patterns + 9 marketing patterns
- **EN**: ~80 keywords + padrões EN
- **ES**: ~85 keywords + padrões ES
- **Total**: ~315 keywords + 32 regex patterns

### Casos de Uso

#### 1. México (Espanhol + Peso Mexicano)
```python
message = "Transferencia de $500 MXN aprobada"
# Matches: $, 500, MXN, transferencia, aprobada
# Decision: URGENT (0.95)
```

#### 2. Argentina (Espanhol + Peso Argentino)
```python
message = "Débito de $150 ARS confirmado"
# Matches: $, 150, ARS, débito, confirmado
# Decision: URGENT (0.92)
```

#### 3. Chile (Espanhol + Peso Chileno)
```python
message = "Pago de $45.000 CLP procesado correctamente"
# Matches: $, 45000, CLP, pago, procesado
# Decision: URGENT (0.90)
```

#### 4. Colômbia (Espanhol + Peso Colombiano)
```python
message = "Tu compra de $25.000 COP ha sido aprobada"
# Matches: $, 25000, COP, compra, aprobada
# Decision: URGENT (0.92)
```

#### 5. EUA (Inglês + Dólar)
```python
message = "Payment of $100.00 USD confirmed"
# Matches: $, 100.00, USD, payment, confirmed
# Decision: URGENT (0.90)
```

#### 6. UE (Inglês/Espanhol + Euro)
```python
message = "Pago de €50,00 confirmado"
# Matches: €, 50,00, pago, confirmado
# Decision: URGENT (0.92)
```

## Roadmap Futuro

### Fase 2: Mais Idiomas
- 🇫🇷 Francês (FR)
- 🇮🇹 Italiano (IT)
- 🇩🇪 Alemão (DE)
- 🇯🇵 Japonês (JA)

### Fase 3: Detecção Automática de Idioma
```python
def detect_language(text: str) -> str:
    """Auto-detect message language using:
    1. Keywords matched
    2. Character patterns (accent marks, etc)
    3. Common word patterns
    """
    pass
```

### Fase 4: Multi-Language Classification
```python
def classify_multilingual(text: str) -> RuleMatch:
    """
    Para mensagens em idiomas múltiplos:
    - Separar por idioma usando delimitadores
    - Classificar cada parte
    - Retornar classificação consolidada (urgência = max)
    """
    pass
```

### Fase 5: Regional Customization
```python
# Currency by region
REGIONAL_CURRENCIES = {
    'PT-BR': {'BRL', 'USD'},
    'ES-MX': {'MXN', 'USD'},
    'ES-AR': {'ARS', 'USD'},
    'ES-CL': {'CLP', 'USD'},
    'EN-US': {'USD'},
    'EN-GB': {'GBP', 'EUR'},
}

# Marketing holidays by region
REGIONAL_EVENTS = {
    'PT-BR': ['black friday', 'cyber monday', 'dia das crianças'],
    'ES-MX': ['buen fin', 'día de reyes'],
    'ES-AR': ['día de la madre', 'día del padre'],
}
```

## Testes de Multilíngue

Testes incluem:
- ✅ Mensagens PT-BR puras
- ✅ Mensagens EN puras
- ✅ Mensagens ES puras
- ✅ Mensagens com moedas múltiplas
- ✅ Mensagens com código de país
- ✅ Caracteres especiais (©, ®, ™, ℠)
- ✅ Símbolos monetários (€, £, ¥, ₹)

Execute com:
```bash
pytest tests/unit/test_urgency_engine.py -v -k "multilingual or language"
```

## Contribuindo Keywords

Para adicionar keywords em novo idioma:

1. Abra `src/jaiminho_notificacoes/processing/urgency_engine.py`
2. Vá para classe `KeywordMatcher.__init__()`
3. Encontre a categoria (financial, security, marketing)
4. Adicione termos com comentário de idioma:

```python
self.financial_keywords = {
    # ... existing keywords ...
    
    # New Language - Category (e.g., Français - Banque)
    'terme1', 'terme2', 'terme3',
}
```

5. Envie um PR com:
   - Keywords em novo idioma
   - Regex patterns ajustados
   - Testes para novo idioma

---

**Última atualização**: 2024-01-02  
**Status**: ✅ PT-BR, EN, ES suportados  
**Coverage**: 315+ keywords, 32 regex patterns
