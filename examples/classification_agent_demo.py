"""
Example demonstrating the Classification Agent for Jaiminho Notificações.

This example shows how to:
1. Use the Classification Agent to categorize messages
2. Generate summaries for daily digests
3. Ensure proper tenant isolation
"""

import asyncio
from datetime import datetime

from jaiminho_notificacoes.processing.agents import (
    get_classification_agent,
    ClassificationResult
)
from jaiminho_notificacoes.processing.urgency_engine import UrgencyDecision
from jaiminho_notificacoes.processing.orchestrator import get_orchestrator
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageContent,
    MessageType,
    MessageSource,
    MessageMetadata,
    MessageSecurity
)


def create_sample_message(
    text: str,
    sender_name: str,
    sender_phone: str,
    is_group: bool = False
) -> NormalizedMessage:
    """Create a sample normalized message for testing."""
    return NormalizedMessage(
        message_id=f"msg_{datetime.now().timestamp()}",
        tenant_id="demo_tenant",
        user_id="demo_user",
        sender_phone=sender_phone,
        sender_name=sender_name,
        message_type=MessageType.TEXT,
        content=MessageContent(text=text),
        timestamp=int(datetime.now().timestamp()),
        source=MessageSource(
            platform="wapi",
            instance_id="demo_instance"
        ),
        metadata=MessageMetadata(is_group=is_group),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )


async def example_basic_classification():
    """Example 1: Basic classification with the agent."""
    print("\n" + "="*80)
    print("Example 1: Basic Message Classification")
    print("="*80)
    
    # Create agent
    agent = get_classification_agent()
    
    # Create sample message
    message = create_sample_message(
        text="Reunião de projeto amanhã às 14h no escritório. Confirme presença!",
        sender_name="João Silva",
        sender_phone="5511999999999"
    )
    
    # Classify
    result: ClassificationResult = await agent.run(
        message=message,
        urgency_decision=UrgencyDecision.NOT_URGENT,
        urgency_confidence=0.8
    )
    
    # Display results
    print(f"\n📋 Classificação:")
    print(f"   Categoria: {result.category}")
    print(f"   Resumo: {result.summary}")
    print(f"   Roteamento: {result.routing}")
    print(f"   Confiança: {result.confidence:.2f}")
    print(f"   Justificativa: {result.reasoning}")


async def example_multiple_categories():
    """Example 2: Classify messages across different categories."""
    print("\n" + "="*80)
    print("Example 2: Multiple Category Classification")
    print("="*80)
    
    agent = get_classification_agent()
    
    # Sample messages from different categories
    test_messages = [
        {
            "text": "Seu pedido #12345 foi enviado! Código rastreio: BR987654321",
            "sender": "Loja Online",
            "phone": "5511888888888",
            "expected_category": "📦 Entregas e Compras"
        },
        {
            "text": "Boleto de R$ 350,00 vence amanhã. Pague via PIX: chave@email.com",
            "sender": "Banco XYZ",
            "phone": "5511777777777",
            "expected_category": "💰 Financeiro"
        },
        {
            "text": "Mamãe, vou chegar tarde hoje. Beijos!",
            "sender": "Filho",
            "phone": "5511666666666",
            "expected_category": "👨‍👩‍👧 Família e Amigos"
        },
        {
            "text": "Resultado do seu exame está disponível no portal. Consulta dia 10.",
            "sender": "Dr. Paulo",
            "phone": "5511555555555",
            "expected_category": "🏥 Saúde"
        }
    ]
    
    print("\n📊 Classificando mensagens:\n")
    
    for idx, msg_data in enumerate(test_messages, 1):
        message = create_sample_message(
            text=msg_data["text"],
            sender_name=msg_data["sender"],
            sender_phone=msg_data["phone"]
        )
        
        result = await agent.run(
            message=message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.7
        )
        
        match = "✅" if msg_data["expected_category"] in result.category else "❌"
        
        print(f"{idx}. {msg_data['sender']}")
        print(f"   Categoria: {result.category} {match}")
        print(f"   Resumo: {result.summary}")
        print(f"   Roteamento: {result.routing}")
        print()


async def example_urgent_routing():
    """Example 3: Urgent message routing."""
    print("\n" + "="*80)
    print("Example 3: Urgent Message Routing")
    print("="*80)
    
    agent = get_classification_agent()
    
    # Urgent message
    message = create_sample_message(
        text="URGENTE: Sistema fora do ar! Clientes reportando erros críticos.",
        sender_name="Monitoramento",
        sender_phone="5511444444444"
    )
    
    # Classify as urgent with high confidence
    result = await agent.run(
        message=message,
        urgency_decision=UrgencyDecision.URGENT,
        urgency_confidence=0.9
    )
    
    print(f"\n🚨 Mensagem Urgente:")
    print(f"   Categoria: {result.category}")
    print(f"   Resumo: {result.summary}")
    print(f"   Roteamento: {result.routing} {'✅ (immediate)' if result.routing == 'immediate' else '❌'}")
    print(f"   Confiança: {result.confidence:.2f}")
    print(f"   Ação: {'Enviar notificação imediata via SendPulse' if result.routing == 'immediate' else 'Adicionar ao digest'}")


async def example_full_orchestration():
    """Example 4: Full orchestration pipeline."""
    print("\n" + "="*80)
    print("Example 4: Full Orchestration Pipeline")
    print("="*80)
    
    orchestrator = get_orchestrator()
    
    # Create message
    message = create_sample_message(
        text="Convite: Aniversário do Pedro no sábado às 19h. Confirme!",
        sender_name="Maria",
        sender_phone="5511333333333"
    )
    
    print("\n📨 Processando mensagem através do pipeline completo...\n")
    
    # Process through full pipeline
    result = await orchestrator.process(message)
    
    print(f"✅ Processamento Completo!")
    print(f"\n📊 Resultados:")
    print(f"   Decisão Final: {result.decision.value}")
    print(f"   Rule Engine: {result.rule_engine_decision}")
    print(f"   LLM Usado: {result.llm_used}")
    print(f"   Confiança: {result.rule_confidence:.2f}")
    
    # Find classification step in audit trail
    classification_step = next(
        (step for step in result.audit_trail if step.get("step") == "classification_agent"),
        None
    )
    
    if classification_step:
        print(f"\n🏷️  Classificação:")
        print(f"   Categoria: {classification_step.get('category', 'N/A')}")
        print(f"   Resumo: {classification_step.get('summary', 'N/A')}")
        print(f"   Roteamento: {classification_step.get('routing', 'N/A')}")


async def example_tenant_isolation():
    """Example 5: Demonstrate tenant isolation."""
    print("\n" + "="*80)
    print("Example 5: Tenant Isolation (Security)")
    print("="*80)
    
    agent = get_classification_agent()
    
    print("\n🔒 Demonstrando isolamento de tenant:\n")
    
    # Valid message with proper tenant isolation
    valid_message = create_sample_message(
        text="Mensagem de teste",
        sender_name="Usuario",
        sender_phone="5511222222222"
    )
    
    try:
        result = await agent.run(
            message=valid_message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.7
        )
        print("✅ Mensagem válida processada com sucesso")
        print(f"   Tenant: {valid_message.tenant_id}")
        print(f"   User: {valid_message.user_id}")
        print(f"   Categoria: {result.category}")
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # Invalid message without tenant_id
    print("\n🚫 Testando mensagem SEM tenant_id (deve falhar):")
    invalid_message = valid_message.model_copy(update={"tenant_id": ""})
    
    try:
        result = await agent.run(
            message=invalid_message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.7
        )
        print("❌ ERRO: Mensagem inválida foi processada (não deveria)")
    except ValueError as e:
        print(f"✅ Validação funcionou corretamente!")
        print(f"   Erro capturado: {str(e)}")


async def example_digest_generation():
    """Example 6: Generate digest summaries."""
    print("\n" + "="*80)
    print("Example 6: Digest Summary Generation")
    print("="*80)
    
    agent = get_classification_agent()
    
    # Multiple messages for digest
    messages = [
        ("Reunião confirmada para amanhã", "Chefe", "5511111111111"),
        ("Seu pedido chegou!", "Correios", "5511111111112"),
        ("Boleto vence dia 15", "Banco", "5511111111113"),
        ("Oi tudo bem? Vamos marcar um café", "Amigo", "5511111111114"),
    ]
    
    print("\n📧 Gerando resumos para digest diário:\n")
    print("="*80)
    
    categories_digest = {}
    
    for text, sender, phone in messages:
        message = create_sample_message(text, sender, phone)
        
        result = await agent.run(
            message=message,
            urgency_decision=UrgencyDecision.NOT_URGENT,
            urgency_confidence=0.8
        )
        
        # Group by category
        if result.category not in categories_digest:
            categories_digest[result.category] = []
        
        categories_digest[result.category].append(result.summary)
    
    # Display as digest
    print("\n📬 Seu Digest Diário\n")
    
    for category, summaries in categories_digest.items():
        print(f"\n{category}")
        print("-" * 60)
        for summary in summaries:
            print(f"  • {summary}")
    
    print("\n" + "="*80)


async def main():
    """Run all examples."""
    print("\n" + "🤖 CLASSIFICATION AGENT - EXAMPLES 🤖".center(80))
    
    await example_basic_classification()
    await example_multiple_categories()
    await example_urgent_routing()
    # await example_full_orchestration()  # Requires AWS DynamoDB setup
    await example_tenant_isolation()
    await example_digest_generation()
    
    print("\n" + "="*80)
    print("✅ All examples completed successfully!")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
