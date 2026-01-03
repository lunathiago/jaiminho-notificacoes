# Daily Digest Agent

## Visão Geral

O **Daily Digest Agent** é responsável por gerar resumos diários personalizados das mensagens do WhatsApp, agrupadas por categoria cognitiva. Ele produz textos otimizados para entrega via WhatsApp, minimizando a carga cognitiva do usuário.

### Funcionalidades Principais

1. **Agrupamento por Categoria**: Organiza mensagens usando as categorias do Classification Agent
2. **Formatação WhatsApp**: Produz texto formatado com emojis, negrito e estrutura clara
3. **Isolamento por Usuário**: Opera estritamente por `user_id`, garantindo privacidade
4. **Minimização de Carga Cognitiva**: Limita visualização a 3 mensagens por categoria
5. **Singleton Pattern**: Instância única compartilhada para eficiência

---

## Arquitetura

### Classes e Modelos

#### 1. DigestMessage (dataclass)
```python
@dataclass
class DigestMessage:
    """Simplified message for digest display."""
    sender: str
    summary: str
    timestamp: int
```

Representa uma mensagem simplificada para o digest.

#### 2. CategoryDigest (dataclass)
```python
@dataclass
class CategoryDigest:
    """Messages grouped by category."""
    category: str
    messages: List[DigestMessage]
    total_count: int
```

Agrupa mensagens de uma categoria específica.

#### 3. UserDigest (dataclass)
```python
@dataclass
class UserDigest:
    """Complete daily digest for a user."""
    user_id: str
    tenant_id: str
    date: str
    categories: List[CategoryDigest]
    total_messages: int
```

Representa o digest completo de um usuário, com método `to_whatsapp_text()` para formatação.

#### 4. DigestAgent (class)

A classe principal que gera os digests.

---

## Uso Básico

### Importação
```python
from jaiminho_notificacoes.processing.digest_generator import get_digest_agent
from jaiminho_notificacoes.persistence.models import NormalizedMessage
```

### Gerar Digest Simples
```python
# Obter instância singleton
agent = get_digest_agent()

# Gerar digest
digest = await agent.generate_digest(
    user_id="user_123",
    tenant_id="tenant_abc",
    messages=messages  # List[NormalizedMessage]
)

# Formatar para WhatsApp
whatsapp_text = digest.to_whatsapp_text()
print(whatsapp_text)
```

### Exemplo de Saída
```
📬 *Seu Digest Diário*
📅 Sábado, 03/01/2026
📊 7 mensagens

*💼 Trabalho e Negócios* (2)
  • RH: Relatório mensal precisa ser entregue hoje
  • Gerente: Reunião às 10h cancelada

*👨‍👩‍👧 Família e Amigos* (2)
  • Mãe: Jantar domingo em casa?
  • Amigo João: Almoço amanhã?

*📦 Entregas e Compras* (1)
  • Mercado Livre: Pedido chegará amanhã entre 14h e 18h

─────────────────
💡 _Dica: Responda diretamente às mensagens importantes_
```

---

## Estratégia de Formatação

### 1. Estrutura do Digest

O digest é estruturado em seções:

1. **Cabeçalho**:
   - Emoji de caixa de correio (📬/📭)
   - Título em negrito
   - Data em português
   - Contagem total de mensagens

2. **Categorias**:
   - Nome da categoria com emoji em negrito
   - Contador de mensagens
   - Até 3 mensagens mais recentes
   - Indicador de mensagens adicionais (se > 3)

3. **Rodapé**:
   - Linha separadora
   - Dica de ação

### 2. Minimização de Carga Cognitiva

O design do digest segue princípios de UX cognitiva:

- **Limite de 3 mensagens por categoria**: Evita sobrecarga informacional
- **Ordenação cronológica reversa**: Mensagens mais recentes primeiro
- **Emojis consistentes**: Identificação visual rápida
- **Negrito para destaque**: Hierarquia visual clara
- **Bullet points**: Escaneabilidade melhorada

### 3. Ordenação de Categorias

As categorias são ordenadas por:
1. Número de mensagens (descendente)
2. Nome da categoria (alfabético)

Isso coloca as categorias mais "ativas" no topo.

### 4. Formatação de Texto

- **Negrito**: `*Texto*` para títulos e categorias
- **Itálico**: `_Texto_` para dicas
- **Bullet Points**: `•` para itens de lista
- **Linhas separadoras**: `─────────────────`

---

## Isolamento e Segurança

### Validação de User ID

```python
def _validate_user_isolation(
    self,
    user_id: str,
    messages: List[NormalizedMessage]
) -> None:
    """Validate that all messages belong to the specified user."""
    for message in messages:
        if message.user_id != user_id:
            raise ValueError(
                f"Message {message.message_id} belongs to user "
                f"{message.user_id}, not {user_id}. "
                f"Cross-user data access not allowed."
            )
```

### Princípios de Segurança

1. **Validação Estrita**: Todo digest valida que `message.user_id == user_id`
2. **Falha Rápida**: Primeira mensagem incompatível gera erro imediato
3. **Log de Erro**: Tentativas de acesso cruzado são logadas
4. **Sem Fallback**: Não há comportamento de recuperação - segurança primeiro

---

## Integração com Classification Agent

O Digest Agent depende dos dados do Classification Agent:

```python
# Classification Agent adiciona metadados
message.classification_category = "💼 Trabalho e Negócios"
message.classification_summary = "João: Reunião amanhã"

# Digest Agent usa esses metadados
category_digest = CategoryDigest(
    category=message.classification_category,
    messages=[
        DigestMessage(
            sender=message.sender_name,
            summary=message.classification_summary,
            timestamp=message.timestamp
        )
    ],
    total_count=1
)
```

### Pipeline Completo

```
WhatsApp Message
      ↓
Classification Agent (categoriza + resume)
      ↓
NormalizedMessage (com classification_*)
      ↓
Digest Agent (agrupa + formata)
      ↓
WhatsApp Text (pronto para envio)
```

---

## API Reference

### get_digest_agent() → DigestAgent

Retorna a instância singleton do Digest Agent.

```python
agent = get_digest_agent()
```

### DigestAgent.generate_digest()

```python
async def generate_digest(
    self,
    user_id: str,
    tenant_id: str,
    messages: List[NormalizedMessage],
    date: Optional[str] = None
) -> UserDigest:
    """
    Generate a daily digest for a user.
    
    Args:
        user_id: User identifier (must match all messages)
        tenant_id: Tenant identifier
        messages: List of normalized messages with classification data
        date: Optional date string (YYYY-MM-DD). Defaults to today.
    
    Returns:
        UserDigest object with categories and WhatsApp-formatted text
    
    Raises:
        ValueError: If any message belongs to a different user
    """
```

**Parâmetros**:
- `user_id` (str): Identificador do usuário
- `tenant_id` (str): Identificador do tenant
- `messages` (List[NormalizedMessage]): Mensagens normalizadas com dados de classificação
- `date` (Optional[str]): Data do digest (formato: YYYY-MM-DD)

**Retorna**: `UserDigest`

**Exceções**:
- `ValueError`: Se alguma mensagem pertencer a outro usuário

### UserDigest.to_whatsapp_text() → str

```python
def to_whatsapp_text(self) -> str:
    """
    Format digest as WhatsApp-ready text.
    
    Returns:
        Formatted string with emojis, bold, and structure
    """
```

Converte o digest em texto formatado para WhatsApp.

---

## Testes

### Executar Testes

```bash
pytest tests/unit/test_digest_generator.py -v
```

### Cobertura de Testes

Os testes cobrem:

1. ✅ Geração básica de digest
2. ✅ Digest vazio (sem mensagens)
3. ✅ Múltiplas mensagens na mesma categoria
4. ✅ Validação de isolamento por usuário
5. ✅ Formatação de texto WhatsApp
6. ✅ Singleton pattern

### Exemplo de Teste

```python
@pytest.mark.asyncio
async def test_generate_basic_digest():
    """Test basic digest generation with multiple categories."""
    agent = get_digest_agent()
    
    messages = [
        create_test_message(
            "msg_1", "user_1", "Reunião amanhã",
            category="💼 Trabalho e Negócios"
        ),
        create_test_message(
            "msg_2", "user_1", "Pedido enviado",
            category="📦 Entregas e Compras"
        ),
    ]
    
    digest = await agent.generate_digest(
        user_id="user_1",
        tenant_id="tenant_1",
        messages=messages
    )
    
    assert digest.total_messages == 2
    assert len(digest.categories) == 2
```

---

## Exemplos Práticos

### Exemplo 1: Digest Diário Completo

```python
from jaiminho_notificacoes.processing.digest_generator import get_digest_agent

async def generate_daily_digest(user_id: str, tenant_id: str):
    """Generate and send daily digest."""
    
    # Buscar mensagens do dia (pseudocódigo)
    messages = await get_todays_messages(user_id, tenant_id)
    
    # Gerar digest
    agent = get_digest_agent()
    digest = await agent.generate_digest(
        user_id=user_id,
        tenant_id=tenant_id,
        messages=messages
    )
    
    # Enviar via WhatsApp
    whatsapp_text = digest.to_whatsapp_text()
    await send_whatsapp_message(user_id, whatsapp_text)
    
    return digest
```

### Exemplo 2: Digest Vazio

```python
async def handle_empty_digest(user_id: str):
    """Handle case with no messages."""
    
    agent = get_digest_agent()
    digest = await agent.generate_digest(
        user_id=user_id,
        tenant_id="tenant_1",
        messages=[]  # Sem mensagens
    )
    
    # Retorna: "📭 *Digest Diário*\n\nNenhuma mensagem hoje!"
    print(digest.to_whatsapp_text())
```

### Exemplo 3: Filtrar por Categoria

```python
async def digest_for_category(user_id: str, category: str):
    """Generate digest for specific category."""
    
    # Buscar todas as mensagens
    all_messages = await get_messages(user_id)
    
    # Filtrar por categoria
    filtered = [
        m for m in all_messages 
        if m.classification_category == category
    ]
    
    # Gerar digest apenas dessa categoria
    agent = get_digest_agent()
    digest = await agent.generate_digest(
        user_id=user_id,
        tenant_id="tenant_1",
        messages=filtered
    )
    
    return digest
```

---

## Boas Práticas

### 1. Sempre Validar Usuário

```python
# ✅ Correto
digest = await agent.generate_digest(
    user_id="user_123",
    tenant_id="tenant_abc",
    messages=messages_for_user_123
)

# ❌ Incorreto - mistura mensagens de usuários
digest = await agent.generate_digest(
    user_id="user_123",
    tenant_id="tenant_abc",
    messages=all_messages  # Pode conter mensagens de outros usuários
)
```

### 2. Tratar Digest Vazio

```python
digest = await agent.generate_digest(user_id, tenant_id, messages)

if digest.total_messages == 0:
    # Digest vazio - talvez não enviar notificação
    logger.info("No messages for user", user_id=user_id)
else:
    # Enviar digest via WhatsApp
    await send_digest(digest.to_whatsapp_text())
```

### 3. Logar Geração de Digest

```python
from jaiminho_notificacoes.core.logger import get_logger

logger = get_logger(__name__)

try:
    digest = await agent.generate_digest(user_id, tenant_id, messages)
    logger.info(
        "Digest generated successfully",
        user_id=user_id,
        total_messages=digest.total_messages,
        categories=len(digest.categories)
    )
except ValueError as e:
    logger.error("User isolation violation", error=str(e))
```

### 4. Usar Instância Singleton

```python
# ✅ Correto - usa singleton
agent = get_digest_agent()

# ❌ Incorreto - cria instância nova
agent = DigestAgent()  # Não faça isso!
```

---

## Configuração e Customização

### Data Personalizada

```python
digest = await agent.generate_digest(
    user_id="user_123",
    tenant_id="tenant_abc",
    messages=messages,
    date="2026-01-15"  # Digest para data específica
)
```

### Limite de Mensagens por Categoria

Atualmente fixo em 3. Para alterar, modifique `MAX_MESSAGES_PER_CATEGORY` em `digest_generator.py`:

```python
MAX_MESSAGES_PER_CATEGORY = 5  # Exibir até 5 mensagens
```

### Customizar Emojis

Edite o método `to_whatsapp_text()` para alterar emojis:

```python
# Cabeçalho vazio
header = "📭 *Digest Diário*"  # Altere 📭 para outro emoji

# Rodapé
footer = "🎯 _Foco nas prioridades_"  # Altere a dica
```

---

## Troubleshooting

### Erro: "Cross-user data access not allowed"

**Causa**: Tentativa de gerar digest com mensagens de diferentes usuários.

**Solução**:
```python
# Filtrar mensagens antes
user_messages = [m for m in all_messages if m.user_id == target_user_id]
digest = await agent.generate_digest(target_user_id, tenant_id, user_messages)
```

### Categoria Ausente

**Causa**: Mensagem sem `classification_category`.

**Solução**:
```python
# Garantir que Classification Agent processou mensagens
for message in messages:
    if not message.classification_category:
        # Reclassificar ou usar categoria padrão
        message.classification_category = "❓ Outros"
        message.classification_summary = f"{message.sender_name}: {message.content.text[:50]}"
```

### Digest Vazio Inesperado

**Causa**: Todas as mensagens foram filtradas ou lista vazia.

**Solução**:
```python
logger.info(f"Processing {len(messages)} messages")
digest = await agent.generate_digest(user_id, tenant_id, messages)

if digest.total_messages == 0:
    logger.warning("No messages resulted in digest")
```

---

## Próximos Passos

### Melhorias Futuras

1. **Digest Multiidioma**: Suporte para outros idiomas além de português
2. **Personalização de Formato**: Permitir usuário escolher estilo de digest
3. **Filtros Avançados**: Digest apenas de categorias específicas
4. **Resumo LLM**: Usar LLM para gerar resumo geral do dia
5. **Priorização Inteligente**: Ordenar mensagens por urgência dentro de cada categoria

### Integração com Scheduler

```python
# Lambda function para envio diário
async def daily_digest_lambda_handler(event, context):
    """Send daily digest to all users."""
    
    users = await get_all_active_users()
    agent = get_digest_agent()
    
    for user in users:
        messages = await get_user_messages_today(user.id)
        
        if messages:
            digest = await agent.generate_digest(
                user_id=user.id,
                tenant_id=user.tenant_id,
                messages=messages
            )
            
            await send_whatsapp(user.phone, digest.to_whatsapp_text())
```

---

## Referências

- [Classification Agent Documentation](CLASSIFICATION_AGENT.md)
- [WhatsApp Formatting Guide](https://faq.whatsapp.com/539178204879377)
- [Cognitive Load Theory](https://en.wikipedia.org/wiki/Cognitive_load)
- [UX Writing Best Practices](https://uxwritinghub.com/)

---

## Changelog

### v1.0.0 (2026-01-03)
- ✅ Implementação inicial do Digest Agent
- ✅ Agrupamento por categoria
- ✅ Formatação para WhatsApp
- ✅ Isolamento por usuário
- ✅ Testes unitários completos
- ✅ Exemplos práticos

---

## Suporte

Para dúvidas ou problemas:
1. Consulte a [documentação completa](../docs/)
2. Execute os [exemplos](../examples/digest_agent_demo.py)
3. Verifique os [testes](../tests/unit/test_digest_generator.py)
