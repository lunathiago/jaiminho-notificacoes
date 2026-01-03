"""Exemplo de uso do Urgency Agent.

Este exemplo demonstra como usar o Urgency Agent para classificar
a urgência de mensagens do WhatsApp.
"""

import asyncio
import json
from datetime import datetime

from jaiminho_notificacoes.processing.agents import (
    UrgencyAgent,
    HistoricalInterruptionData,
)
from jaiminho_notificacoes.persistence.models import (
    NormalizedMessage,
    MessageType,
    MessageContent,
    MessageMetadata,
    MessageSecurity,
    MessageSource as MessageSourceModel
)


def create_sample_message(
    text: str,
    sender_phone: str = "5511999999999",
    sender_name: str = "João Silva",
    is_group: bool = False
) -> NormalizedMessage:
    """Create a sample message for testing."""
    return NormalizedMessage(
        message_id=f"msg-{datetime.now().timestamp()}",
        tenant_id="tenant-example",
        user_id="user-123",
        sender_phone=sender_phone,
        sender_name=sender_name,
        message_type=MessageType.TEXT,
        content=MessageContent(text=text),
        timestamp=int(datetime.now().timestamp()),
        source=MessageSourceModel(
            platform="evolution_api",
            instance_id="instance-001"
        ),
        metadata=MessageMetadata(is_group=is_group, from_me=False),
        security=MessageSecurity(
            validated_at=datetime.now().isoformat(),
            validation_passed=True,
            instance_verified=True,
            tenant_resolved=True,
            phone_ownership_verified=True
        )
    )


async def main():
    """Demonstração do Urgency Agent."""
    
    print("=" * 80)
    print("URGENCY AGENT - DEMONSTRAÇÃO")
    print("=" * 80)
    print()
    
    # Criar instância do agente
    agent = UrgencyAgent()
    
    # Exemplo 1: Mensagem financeira urgente
    print("1. ALERTA FINANCEIRO")
    print("-" * 80)
    msg1 = create_sample_message(
        "ALERTA: Transação suspeita de R$ 5.000,00 detectada em sua conta. "
        "Código de verificação: 123456. Expira em 5 minutos."
    )
    
    # Criar dados históricos simulados (remetente confiável)
    history1 = HistoricalInterruptionData(
        sender_phone="5511999999999",
        total_messages=15,
        urgent_count=12,
        not_urgent_count=3,
        avg_response_time_seconds=300.0
    )
    
    result1 = await agent.run(msg1, history1)
    print(f"Mensagem: {msg1.content.text[:100]}...")
    print(f"Resultado: {json.dumps(result1.to_json(), indent=2, ensure_ascii=False)}")
    print()
    
    # Exemplo 2: Marketing/Promoção (não urgente)
    print("2. MENSAGEM DE MARKETING")
    print("-" * 80)
    msg2 = create_sample_message(
        "🎉 PROMOÇÃO ESPECIAL! 50% de desconto em todos os produtos! "
        "Não perca essa oportunidade incrível! Compre 2 leve 3!",
        sender_phone="5511888888888",
        sender_name="Loja ABC"
    )
    
    # Histórico com baixa taxa de urgência
    history2 = HistoricalInterruptionData(
        sender_phone="5511888888888",
        total_messages=30,
        urgent_count=1,
        not_urgent_count=29
    )
    
    result2 = await agent.run(msg2, history2)
    print(f"Mensagem: {msg2.content.text[:100]}...")
    print(f"Resultado: {json.dumps(result2.to_json(), indent=2, ensure_ascii=False)}")
    print()
    
    # Exemplo 3: Mensagem de grupo (conservador)
    print("3. MENSAGEM DE GRUPO")
    print("-" * 80)
    msg3 = create_sample_message(
        "Pessoal, reunião urgente amanhã às 9h! Por favor confirmar presença.",
        is_group=True
    )
    
    result3 = await agent.run(msg3)
    print(f"Mensagem: {msg3.content.text}")
    print(f"Resultado: {json.dumps(result3.to_json(), indent=2, ensure_ascii=False)}")
    print()
    
    # Exemplo 4: Primeiro contato (muito conservador)
    print("4. PRIMEIRO CONTATO")
    print("-" * 80)
    msg4 = create_sample_message(
        "Olá! Vi seu anúncio e tenho interesse no produto. Podemos conversar?",
        sender_phone="5511777777777",
        sender_name="Desconhecido"
    )
    
    # Sem histórico (primeiro contato)
    history4 = HistoricalInterruptionData(sender_phone="5511777777777")
    
    result4 = await agent.run(msg4, history4)
    print(f"Mensagem: {msg4.content.text}")
    print(f"Resultado: {json.dumps(result4.to_json(), indent=2, ensure_ascii=False)}")
    print()
    
    # Exemplo 5: Mensagem muito curta
    print("5. MENSAGEM CURTA")
    print("-" * 80)
    msg5 = create_sample_message("Ok")
    
    result5 = await agent.run(msg5)
    print(f"Mensagem: {msg5.content.text}")
    print(f"Resultado: {json.dumps(result5.to_json(), indent=2, ensure_ascii=False)}")
    print()
    
    # Exemplo 6: Código de verificação (urgente)
    print("6. CÓDIGO DE VERIFICAÇÃO")
    print("-" * 80)
    msg6 = create_sample_message(
        "Seu código de verificação é: 987654\n"
        "Não compartilhe este código com ninguém.\n"
        "Válido por 10 minutos.",
        sender_phone="551133334444",
        sender_name="Banco XYZ"
    )
    
    history6 = HistoricalInterruptionData(
        sender_phone="551133334444",
        total_messages=8,
        urgent_count=7,
        not_urgent_count=1
    )
    
    result6 = await agent.run(msg6, history6)
    print(f"Mensagem: {msg6.content.text[:100]}...")
    print(f"Resultado: {json.dumps(result6.to_json(), indent=2, ensure_ascii=False)}")
    print()
    
    print("=" * 80)
    print("DEMONSTRAÇÃO CONCLUÍDA")
    print("=" * 80)
    print()
    print("OBSERVAÇÕES:")
    print("- O agente é conservador por padrão")
    print("- Considera dados históricos do remetente")
    print("- Mensagens de grupo têm limiar mais alto")
    print("- Primeiro contato requer confiança muito alta (>0.85)")
    print("- Em caso de erro, sempre opta por NÃO interromper")


if __name__ == "__main__":
    asyncio.run(main())
