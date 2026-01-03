"""Daily digest generation and scheduling."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

from jaiminho_notificacoes.core.logger import TenantContextLogger
from jaiminho_notificacoes.core.tenant import TenantContext
from jaiminho_notificacoes.persistence.models import NormalizedMessage


logger = TenantContextLogger(__name__)


@dataclass
class DigestMessage:
    """Simplified message for digest."""
    message_id: str
    sender_name: str
    sender_phone: str
    summary: str
    category: str
    timestamp: int
    is_group: bool = False
    group_name: Optional[str] = None


@dataclass
class CategoryDigest:
    """Digest for a specific category."""
    category: str
    emoji: str
    message_count: int
    messages: List[DigestMessage] = field(default_factory=list)
    
    def get_display_name(self) -> str:
        """Get display name with emoji."""
        return self.category


@dataclass
class UserDigest:
    """Complete daily digest for a user."""
    user_id: str
    tenant_id: str
    date: str
    total_messages: int
    categories: List[CategoryDigest] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_whatsapp_text(self) -> str:
        """
        Generate WhatsApp-ready formatted text.
        
        Optimized for:
        - Mobile readability
        - Minimal cognitive load
        - Quick scanning
        - Emojis for visual cues
        """
        if self.total_messages == 0:
            return "📭 *Digest Diário*\n\nNenhuma mensagem hoje!"
        
        # Header
        msg_text = "mensagem" if self.total_messages == 1 else "mensagens"
        lines = [
            "📬 *Seu Digest Diário*",
            f"📅 {self._format_date()}",
            f"📊 {self.total_messages} {msg_text}",
            "",
        ]
        
        # Categories (sorted by message count, descending)
        sorted_categories = sorted(
            self.categories,
            key=lambda c: c.message_count,
            reverse=True
        )
        
        for cat in sorted_categories:
            lines.append(f"*{cat.get_display_name()}* ({cat.message_count})")
            
            # Show first 3 messages per category
            for i, msg in enumerate(cat.messages[:3]):
                # Format: "• Sender: summary"
                sender_display = self._format_sender(msg)
                lines.append(f"  • {sender_display}: {msg.summary}")
            
            # If more messages, show count
            if len(cat.messages) > 3:
                remaining = len(cat.messages) - 3
                lines.append(f"  ... e mais {remaining} mensagem{'ns' if remaining != 1 else ''}")
            
            lines.append("")  # Blank line between categories
        
        # Footer
        lines.append("─────────────────")
        lines.append("💡 _Dica: Responda diretamente às mensagens importantes_")
        
        return "\n".join(lines)
    
    def _format_date(self) -> str:
        """Format date in Brazilian Portuguese."""
        try:
            date_obj = datetime.fromisoformat(self.date)
            weekdays = {
                0: "Segunda", 1: "Terça", 2: "Quarta",
                3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"
            }
            weekday = weekdays[date_obj.weekday()]
            return f"{weekday}, {date_obj.strftime('%d/%m/%Y')}"
        except:
            return self.date
    
    def _format_sender(self, msg: DigestMessage) -> str:
        """Format sender name for display."""
        if msg.is_group and msg.group_name:
            return f"{msg.group_name}"
        return msg.sender_name or msg.sender_phone[-4:]


class DigestAgent:
    """
    Agent for generating daily digest summaries.
    
    Features:
    - Operates per user_id (no cross-user data)
    - Groups messages by category
    - Produces WhatsApp-ready formatted text
    - Minimizes cognitive load with emojis and structure
    - Concise summaries (3 messages per category max)
    """
    
    def __init__(self):
        """Initialize digest agent."""
        self.logger = logger
    
    async def generate_digest(
        self,
        tenant_context: TenantContext,
        messages: List[NormalizedMessage],
        date: Optional[str] = None
    ) -> UserDigest:
        """
        Generate daily digest for a specific user.
        
        Args:
            tenant_context: Verified tenant context resolved internally
            messages: List of messages (already filtered for this user)
            date: Date for digest (default: today)
        
        Returns:
            UserDigest with formatted content
        
        Security:
            - Only processes messages for the tenant/user pair in tenant_context
            - No cross-user data is accessed
            - Validates tenant isolation against W-API derived context
        """
        self.logger.set_context(
            tenant_id=tenant_context.tenant_id,
            user_id=tenant_context.user_id
        )
        
        try:
            # Validate all messages belong to this user
            self._validate_user_isolation(tenant_context, messages)
            
            # Use today if date not specified
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            self.logger.info(
                "Generating digest",
                user_id=user_id,
                message_count=len(messages),
                date=date
            )
            
            # Group messages by category
            categories_dict = self._group_by_category(messages)
            
            # Create category digests
            category_digests = []
            for category, msgs in categories_dict.items():
                category_digests.append(
                    CategoryDigest(
                        category=category,
                        emoji=self._extract_emoji(category),
                        message_count=len(msgs),
                        messages=msgs
                    )
                )
            
            # Create user digest
            digest = UserDigest(
                user_id=tenant_context.user_id,
                tenant_id=tenant_context.tenant_id,
                date=date,
                total_messages=len(messages),
                categories=category_digests
            )
            
            self.logger.info(
                "Digest generated",
                user_id=tenant_context.user_id,
                total_messages=digest.total_messages,
                category_count=len(digest.categories)
            )
            
            return digest
            
        except Exception as e:
            self.logger.error(
                "Error generating digest",
                error=str(e),
                user_id=tenant_context.user_id
            )
            raise
        finally:
            self.logger.clear_context()
    
    def _validate_user_isolation(
        self,
        tenant_context: TenantContext,
        messages: List[NormalizedMessage]
    ):
        """
        Validate that all messages belong to the specified user.
        
        Raises:
            ValueError: If any message belongs to a different user
        """
        for msg in messages:
            if msg.user_id != tenant_context.user_id:
                raise ValueError(
                    f"Message {msg.message_id} belongs to user {msg.user_id}, "
                    f"not {tenant_context.user_id}. Cross-user data access not allowed."
                )
            if msg.tenant_id != tenant_context.tenant_id:
                raise ValueError(
                    f"Message {msg.message_id} belongs to tenant {msg.tenant_id}, "
                    f"not {tenant_context.tenant_id}. Cross-tenant data access not allowed."
                )
        
        self.logger.debug(
            "User isolation validated",
            user_id=tenant_context.user_id,
            tenant_id=tenant_context.tenant_id,
            message_count=len(messages)
        )
    
    def _group_by_category(
        self,
        messages: List[NormalizedMessage]
    ) -> Dict[str, List[DigestMessage]]:
        """
        Group messages by category.
        
        Args:
            messages: List of normalized messages
        
        Returns:
            Dictionary mapping category to list of digest messages
        """
        categories = defaultdict(list)
        
        for msg in messages:
            # Extract category from message metadata
            # Assuming classification results are stored in message
            category = getattr(msg, 'classification_category', None) or "❓ Outros"
            
            # Create simplified digest message
            digest_msg = DigestMessage(
                message_id=msg.message_id,
                sender_name=msg.sender_name or "Contato",
                sender_phone=msg.sender_phone,
                summary=getattr(msg, 'classification_summary', None) or self._create_summary(msg),
                category=category,
                timestamp=msg.timestamp,
                is_group=msg.metadata.is_group,
                group_name=msg.metadata.group_id if msg.metadata.is_group else None
            )
            
            categories[category].append(digest_msg)
        
        # Sort messages within each category by timestamp (most recent first)
        for category in categories:
            categories[category].sort(key=lambda m: m.timestamp, reverse=True)
        
        return dict(categories)
    
    def _create_summary(self, msg: NormalizedMessage) -> str:
        """
        Create a simple summary if classification summary is not available.
        
        Args:
            msg: Normalized message
        
        Returns:
            Short summary text
        """
        text = msg.content.text or msg.content.caption or "Mensagem sem texto"
        
        # Truncate to 80 characters
        if len(text) > 80:
            return text[:77] + "..."
        return text
    
    def _extract_emoji(self, category: str) -> str:
        """
        Extract emoji from category string.
        
        Args:
            category: Category string (e.g., "💼 Trabalho e Negócios")
        
        Returns:
            Emoji character or empty string
        """
        # Emojis are usually at the start of the category string
        if category and len(category) > 0:
            # Check if first character is emoji (typically 2-4 bytes in UTF-8)
            first_char = category[0]
            if ord(first_char) > 127:  # Non-ASCII, likely emoji
                return first_char
        return ""


# Singleton instance
_digest_agent: Optional[DigestAgent] = None


def get_digest_agent() -> DigestAgent:
    """Get or create global digest agent instance."""
    global _digest_agent
    
    if _digest_agent is None:
        _digest_agent = DigestAgent()
    
    return _digest_agent
