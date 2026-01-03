"""Integration between Learning Agent and Urgency Agent.

This module bridges the feedback learning system with the urgency detection,
allowing historical statistics to inform urgency decisions.
"""

import os
from typing import Optional
from dataclasses import asdict

from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.core.tenant import TenantContext
from jaiminho_notificacoes.processing.learning_agent import (
    LearningAgent,
    HistoricalInterruptionData,
)

logger = TenantContextLogger(__name__)


class HistoricalDataProvider:
    """
    Provides historical interruption data to Urgency Agent.

    Bridges Learning Agent's statistics with Urgency Agent's decisions.
    """

    def __init__(self):
        """Initialize provider."""
        self.learning_agent = LearningAgent()

    async def get_sender_context(
        self,
        tenant_context: TenantContext,
        sender_phone: str,
    ) -> Optional[HistoricalInterruptionData]:
        """
        Get historical data for a sender to inform urgency decisions.

        Args:
            tenant_context: Verified tenant context
            sender_phone: Sender's phone number

        Returns:
            HistoricalInterruptionData or None if no history available
        """
        try:
            stats = await self.learning_agent.get_sender_statistics(
                tenant_context=tenant_context,
                sender_phone=sender_phone,
            )

            if not stats:
                logger.debug(
                    "No historical data found for sender",
                    tenant_id=tenant_context.tenant_id,
                    user_id=tenant_context.user_id,
                    sender_phone=sender_phone
                )
                return None

            # Convert to HistoricalInterruptionData
            return HistoricalInterruptionData(
                sender_phone=sender_phone,
                total_messages=stats.get('total_feedback_count', 0),
                urgent_count=stats.get('important_count', 0),
                not_urgent_count=stats.get('not_important_count', 0),
                avg_response_time_seconds=stats.get('avg_response_time_seconds', None),
                last_urgent_timestamp=None,  # Could be tracked if needed
                user_feedback_count=stats.get('total_feedback_count', 0),
            )

        except Exception as e:
            logger.error(f"Error getting sender context: {e}")
            return None

    async def get_category_context(
        self,
        tenant_context: TenantContext,
        category: str,
    ) -> Optional[HistoricalInterruptionData]:
        """
        Get historical data for a category to inform urgency decisions.

        Args:
            tenant_context: Verified tenant context
            category: Message category (e.g., "financial", "marketing")

        Returns:
            HistoricalInterruptionData or None if no history available
        """
        try:
            stats = await self.learning_agent.get_category_statistics(
                tenant_context=tenant_context,
                category=category,
            )

            if not stats:
                logger.debug(
                    "No historical data found for category",
                    tenant_id=tenant_context.tenant_id,
                    user_id=tenant_context.user_id,
                    category=category
                )
                return None

            # Convert to HistoricalInterruptionData
            return HistoricalInterruptionData(
                sender_phone=None,
                total_messages=stats.get('total_feedback_count', 0),
                urgent_count=stats.get('important_count', 0),
                not_urgent_count=stats.get('not_important_count', 0),
                avg_response_time_seconds=stats.get('avg_response_time_seconds', None),
                last_urgent_timestamp=None,
                user_feedback_count=stats.get('total_feedback_count', 0),
            )

        except Exception as e:
            logger.error(f"Error getting category context: {e}")
            return None

    async def generate_historical_context_prompt(
        self,
        tenant_context: TenantContext,
        sender_phone: str,
        category: Optional[str] = None,
    ) -> str:
        """
        Generate a text prompt section with historical context.

        Used by Urgency Agent to include in its LLM prompt.

        Args:
            tenant_context: Verified tenant context
            sender_phone: Sender's phone number
            category: Optional message category

        Returns:
            Formatted string with historical context
        """
        try:
            sender_data = await self.get_sender_context(
                tenant_context=tenant_context,
                sender_phone=sender_phone,
            )

            category_data = None
            if category:
                category_data = await self.get_category_context(
                    tenant_context=tenant_context,
                    category=category,
                )

            prompt = "CONTEXTO HISTÓRICO DO FEEDBACK:\n\n"

            # Sender context
            if sender_data and sender_data.total_messages > 0:
                prompt += f"Remetente ({sender_phone}):\n"
                prompt += f"  - Total de mensagens: {sender_data.total_messages}\n"
                prompt += f"  - Taxa de importância: {sender_data.urgency_rate:.1%}\n"
                prompt += f"  - Confirmadas como importantes: {sender_data.urgent_count}\n"
                prompt += f"  - Confirmadas como não importantes: {sender_data.not_urgent_count}\n"

                if sender_data.avg_response_time_seconds:
                    avg_mins = sender_data.avg_response_time_seconds / 60
                    prompt += f"  - Tempo médio de resposta: {avg_mins:.1f} min\n"

                prompt += "\n"
            else:
                prompt += f"Remetente ({sender_phone}): Nenhum histórico disponível (primeiro contato ou dados insuficientes)\n\n"

            # Category context
            if category_data and category_data.total_messages > 0:
                prompt += f"Categoria '{category}':\n"
                prompt += f"  - Total de mensagens: {category_data.total_messages}\n"
                prompt += f"  - Taxa de importância: {category_data.urgency_rate:.1%}\n"
                prompt += f"  - Confirmadas como importantes: {category_data.urgent_count}\n"
                prompt += f"  - Confirmadas como não importantes: {category_data.not_urgent_count}\n\n"

            return prompt

        except Exception as e:
            logger.error(f"Error generating historical context: {e}")
            return ""

    async def get_performance_metrics(
        self,
        tenant_context: TenantContext,
    ) -> dict:
        """
        Get overall performance metrics for the system.

        Returns metrics like:
        - Overall accuracy rate
        - False positive rate
        - False negative rate
        """
        try:
            user_stats = await self.learning_agent.get_user_statistics(
                tenant_context=tenant_context,
            )

            if not user_stats:
                logger.debug(
                    "No user statistics available",
                    tenant_id=tenant_context.tenant_id,
                    user_id=tenant_context.user_id
                )
                return {}

            # Calculate derived metrics
            total = (
                user_stats.get('correct_interrupts', 0) +
                user_stats.get('incorrect_interrupts', 0) +
                user_stats.get('correct_digests', 0) +
                user_stats.get('missed_urgent', 0)
            )

            if total == 0:
                return {}

            correct = (
                user_stats.get('correct_interrupts', 0) +
                user_stats.get('correct_digests', 0)
            )

            accuracy = correct / total if total > 0 else 0

            # Precision: of interrupts we made, how many were correct
            total_interrupts = (
                user_stats.get('correct_interrupts', 0) +
                user_stats.get('incorrect_interrupts', 0)
            )
            precision = (
                user_stats.get('correct_interrupts', 0) / total_interrupts
                if total_interrupts > 0
                else 0
            )

            # Recall: of actual important messages, how many did we catch
            total_important = (
                user_stats.get('correct_interrupts', 0) +
                user_stats.get('missed_urgent', 0)
            )
            recall = (
                user_stats.get('correct_interrupts', 0) / total_important
                if total_important > 0
                else 0
            )

            return {
                'total_feedback': user_stats.get('total_feedback_count', 0),
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'correct_interrupts': user_stats.get('correct_interrupts', 0),
                'incorrect_interrupts': user_stats.get('incorrect_interrupts', 0),
                'correct_digests': user_stats.get('correct_digests', 0),
                'missed_urgent': user_stats.get('missed_urgent', 0),
            }

        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {}
