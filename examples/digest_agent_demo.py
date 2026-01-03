"""
Example demonstrating the Daily Digest Agent for Jaiminho Notificações.

This example shows how to:
1. Generate daily digests per user
2. Group messages by category
3. Format for WhatsApp delivery
4. Ensure proper user isolation
"""

import asyncio
from datetime import datetime, timedelta

from jaiminho_notificacoes.processing.digest_generator import (
    get_digest_agent,
    DigestAgent,
    UserDigest
)
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageContent,
    MessageType,
    MessageSource,
    MessageMetadata,
    MessageSecurity
)


def create_sample_message(
    message_id: str,
    text: str,
    sender_name: str,
    sender_phone: str,
    user_id: str,
    category: str,
    summary: str,
    timestamp_offset: int = 0
) -> NormalizedMessage:
    """Create a sample normalized message for testing."""
    base_time = int(datetime.now().timestamp()) + timestamp_offset
    
    msg = NormalizedMessage(
        message_id=message_id,
        tenant_id="demo_tenant",
        user_id=user_id,
        sender_phone=sender_phone,
        sender_name=sender_name,
        message_type=MessageType.TEXT,
        content=MessageContent(text=text),
        timestamp=base_time,
        source=MessageSource(
            platform="evolution_api",
            instance_id="demo_instance"
        ),
        metadata=MessageMetadata(is_group=False),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )
    
    # Add classification data
    msg.classification_category = category
    msg.classification_summary = summary
    
    return msg


async def example_basic_digest():
    """Example 1: Generate a basic daily digest."""
    print("\n" + "="*80)
    print("Example 1: Basic Daily Digest Generation")
    print("="*80)
    
    # Create sample messages for a user
    messages = [
        create_sample_message(
            "msg_1", 
            "Reunião de projeto amanhã às 14h",
            "João Silva", 
            "5511999999999",
            "user_1",
            "💼 Trabalho e Negócios",
            "João Silva: Reunião de projeto amanhã às 14h"
        ),
        create_sample_message(
            "msg_2",
            "Seu pedido #12345 foi enviado",
            "Loja Online",
            "5511888888888",
            "user_1",
            "📦 Entregas e Compras",
            "Loja Online: Seu pedido #12345 foi enviado"
        ),
        create_sample_message(
            "msg_3",
            "Oi filho, tudo bem?",
            "Mãe",
            "5511777777777",
            "user_1",
            "👨‍👩‍👧 Família e Amigos",
            "Mãe: Oi filho, tudo bem?"
        ),
    ]
    
    # Generate digest
    agent = get_digest_agent()
    digest = await agent.generate_digest(
        user_id="user_1",
        tenant_id="demo_tenant",
        messages=messages
    )
    
    # Display WhatsApp-formatted text
    print(f"\n📧 Digest para user_1 ({digest.total_messages} mensagens):\n")
    print(digest.to_whatsapp_text())


async def example_multiple_messages_same_category():
    """Example 2: Digest with multiple messages in same category."""
    print("\n" + "="*80)
    print("Example 2: Multiple Messages Per Category")
    print("="*80)
    
    # Create several work messages
    messages = [
        create_sample_message(
            f"msg_work_{i}",
            f"Mensagem de trabalho {i}",
            f"Colega{i}",
            f"551199999999{i}",
            "user_1",
            "💼 Trabalho e Negócios",
            f"Colega{i}: Mensagem de trabalho {i}",
            timestamp_offset=i*3600  # Each message 1 hour apart
        )
        for i in range(1, 6)
    ]
    
    # Add messages from other categories
    messages.extend([
        create_sample_message(
            "msg_delivery",
            "Pacote chegou",
            "Correios",
            "5511888888888",
            "user_1",
            "📦 Entregas e Compras",
            "Correios: Pacote chegou"
        ),
        create_sample_message(
            "msg_family",
            "Jantar domingo?",
            "Irmã",
            "5511777777777",
            "user_1",
            "👨‍👩‍👧 Família e Amigos",
            "Irmã: Jantar domingo?"
        ),
    ])
    
    # Generate digest
    agent = get_digest_agent()
    digest = await agent.generate_digest(
        user_id="user_1",
        tenant_id="demo_tenant",
        messages=messages
    )
    
    print(f"\n📧 Digest com {digest.total_messages} mensagens:\n")
    print(digest.to_whatsapp_text())
    
    print("\n💡 Note: Only first 3 messages per category are shown!")


async def example_user_isolation():
    """Example 3: Demonstrate user isolation."""
    print("\n" + "="*80)
    print("Example 3: User Isolation (Security)")
    print("="*80)
    
    # Messages for user_1
    user1_messages = [
        create_sample_message(
            "msg_u1_1",
            "Mensagem para user_1",
            "Sender A",
            "5511111111111",
            "user_1",
            "📰 Informação Geral",
            "Sender A: Mensagem para user_1"
        ),
    ]
    
    # Messages for user_2
    user2_messages = [
        create_sample_message(
            "msg_u2_1",
            "Mensagem para user_2",
            "Sender B",
            "5511222222222",
            "user_2",
            "📰 Informação Geral",
            "Sender B: Mensagem para user_2"
        ),
    ]
    
    agent = get_digest_agent()
    
    # Generate digest for user_1 - should work
    print("\n✅ Generating digest for user_1:")
    digest1 = await agent.generate_digest(
        user_id="user_1",
        tenant_id="demo_tenant",
        messages=user1_messages
    )
    print(f"Success! {digest1.total_messages} mensagem(ns) processada(s)")
    
    # Try to generate digest for user_1 with user_2's messages - should fail
    print("\n❌ Trying to process user_2 messages for user_1 (should fail):")
    try:
        await agent.generate_digest(
            user_id="user_1",
            tenant_id="demo_tenant",
            messages=user2_messages  # Wrong user!
        )
        print("ERROR: Should have failed!")
    except ValueError as e:
        print(f"✅ Correctly rejected: {e}")


async def example_empty_digest():
    """Example 4: Empty digest (no messages)."""
    print("\n" + "="*80)
    print("Example 4: Empty Digest (No Messages)")
    print("="*80)
    
    agent = get_digest_agent()
    
    digest = await agent.generate_digest(
        user_id="user_1",
        tenant_id="demo_tenant",
        messages=[]
    )
    
    print(f"\n📧 Digest vazio ({digest.total_messages} mensagens):\n")
    print(digest.to_whatsapp_text())


async def example_category_distribution():
    """Example 5: Messages across all categories."""
    print("\n" + "="*80)
    print("Example 5: Messages Across All Categories")
    print("="*80)
    
    categories = [
        ("💼 Trabalho e Negócios", "Reunião amanhã", "Chefe"),
        ("👨‍👩‍👧 Família e Amigos", "Tudo bem?", "Primo"),
        ("📦 Entregas e Compras", "Pedido enviado", "Loja"),
        ("💰 Financeiro", "Fatura vencendo", "Banco"),
        ("🏥 Saúde", "Consulta marcada", "Clínica"),
        ("🎉 Eventos e Convites", "Festa sábado", "Amigo"),
        ("📰 Informação Geral", "Notícia importante", "Canal"),
        ("🤖 Automação e Bots", "Alerta sistema", "Bot"),
        ("❓ Outros", "Mensagem qualquer", "Desconhecido"),
    ]
    
    messages = []
    for i, (category, text, sender) in enumerate(categories):
        messages.append(
            create_sample_message(
                f"msg_cat_{i}",
                text,
                sender,
                f"55119999999{i:02d}",
                "user_1",
                category,
                f"{sender}: {text}"
            )
        )
    
    agent = get_digest_agent()
    digest = await agent.generate_digest(
        user_id="user_1",
        tenant_id="demo_tenant",
        messages=messages
    )
    
    print(f"\n📧 Digest com todas as {len(categories)} categorias:\n")
    print(digest.to_whatsapp_text())
    
    print(f"\n📊 Estatísticas:")
    print(f"   Total de mensagens: {digest.total_messages}")
    print(f"   Total de categorias: {len(digest.categories)}")


async def example_realistic_day():
    """Example 6: Realistic daily digest."""
    print("\n" + "="*80)
    print("Example 6: Realistic Daily Digest")
    print("="*80)
    
    # Simulate a realistic day with various messages
    messages = [
        # Morning - Work messages
        create_sample_message(
            "msg_1", "Bom dia! Reunião às 10h cancelada", "Gerente",
            "5511111111111", "user_1", "💼 Trabalho e Negócios",
            "Gerente: Bom dia! Reunião às 10h cancelada", -21600
        ),
        create_sample_message(
            "msg_2", "Relatório mensal precisa ser entregue hoje", "RH",
            "5511111111112", "user_1", "💼 Trabalho e Negócios",
            "RH: Relatório mensal precisa ser entregue hoje", -18000
        ),
        
        # Afternoon - Personal
        create_sample_message(
            "msg_3", "Almoço amanhã?", "Amigo João",
            "5511222222221", "user_1", "👨‍👩‍👧 Família e Amigos",
            "Amigo João: Almoço amanhã?", -10800
        ),
        create_sample_message(
            "msg_4", "Seu pedido chegará amanhã entre 14h e 18h", "Mercado Livre",
            "5511333333331", "user_1", "📦 Entregas e Compras",
            "Mercado Livre: Seu pedido chegará amanhã entre 14h e 18h", -7200
        ),
        
        # Evening - Financial and health
        create_sample_message(
            "msg_5", "Fatura do cartão: R$ 1.250,00. Vence dia 15", "Banco Inter",
            "5511444444441", "user_1", "💰 Financeiro",
            "Banco Inter: Fatura do cartão R$ 1.250,00. Vence dia 15", -3600
        ),
        create_sample_message(
            "msg_6", "Resultado do exame disponível no app", "Laboratório",
            "5511555555551", "user_1", "🏥 Saúde",
            "Laboratório: Resultado do exame disponível no app", -1800
        ),
        
        # Late - Family
        create_sample_message(
            "msg_7", "Jantar domingo em casa?", "Mãe",
            "5511666666661", "user_1", "👨‍👩‍👧 Família e Amigos",
            "Mãe: Jantar domingo em casa?", 0
        ),
    ]
    
    agent = get_digest_agent()
    digest = await agent.generate_digest(
        user_id="user_1",
        tenant_id="demo_tenant",
        messages=messages,
        date=datetime.now().strftime("%Y-%m-%d")
    )
    
    print(f"\n📧 Seu Digest do Dia ({digest.total_messages} mensagens):\n")
    print(digest.to_whatsapp_text())
    
    print("\n" + "="*80)
    print("💡 Este digest está pronto para ser enviado via WhatsApp!")
    print("   - Formatação otimizada para mobile")
    print("   - Emojis para identificação rápida")
    print("   - Agrupamento por categoria")
    print("   - Máximo 3 mensagens por categoria")
    print("="*80)


async def main():
    """Run all examples."""
    print("\n" + "🗓️  DAILY DIGEST AGENT - EXAMPLES 🗓️".center(80))
    
    await example_basic_digest()
    await example_multiple_messages_same_category()
    await example_user_isolation()
    await example_empty_digest()
    await example_category_distribution()
    await example_realistic_day()
    
    print("\n" + "="*80)
    print("✅ All examples completed successfully!")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
