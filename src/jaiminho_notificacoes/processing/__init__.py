"""Message processing and orchestration module.

Components:
- urgency_engine: Deterministic rule-based urgency detection
- agents: LLM-powered decision agents
- learning_agent: User feedback processing and statistics
- learning_integration: Bridge between learning and urgency
- feedback_handler: SendPulse webhook feedback processing
- digest_generator: Daily digest generation
- orchestrator: LangGraph-based message processing workflow
"""

# Lazy imports to avoid boto3 region errors during testing
def __getattr__(name):
    if name == "LearningAgent":
        from .learning_agent import LearningAgent
        return LearningAgent
    elif name == "FeedbackType":
        from .learning_agent import FeedbackType
        return FeedbackType
    elif name == "UserFeedback":
        from .learning_agent import UserFeedback
        return UserFeedback
    elif name == "HistoricalDataProvider":
        from .learning_integration import HistoricalDataProvider
        return HistoricalDataProvider
    elif name == "FeedbackHandler":
        from .feedback_handler import FeedbackHandler
        return FeedbackHandler
    elif name == "UserFeedbackProcessor":
        from .feedback_handler import UserFeedbackProcessor
        return UserFeedbackProcessor
    elif name == "SendPulseWebhookValidator":
        from .feedback_handler import SendPulseWebhookValidator
        return SendPulseWebhookValidator
    elif name == "FeedbackMessageResolver":
        from .feedback_handler import FeedbackMessageResolver
        return FeedbackMessageResolver
    elif name == "get_feedback_handler":
        from .feedback_handler import get_feedback_handler
        return get_feedback_handler
    raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    "LearningAgent",
    "FeedbackType",
    "UserFeedback",
    "HistoricalDataProvider",
    "FeedbackHandler",
    "UserFeedbackProcessor",
    "SendPulseWebhookValidator",
    "FeedbackMessageResolver",
    "get_feedback_handler",
]
