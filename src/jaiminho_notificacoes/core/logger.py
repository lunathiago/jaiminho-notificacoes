"""Structured logging with tenant context."""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from functools import wraps


class TenantContextLogger:
    """Logger with tenant context and security audit capabilities."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # JSON formatter for structured logging
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(self._get_json_formatter())
        self.logger.addHandler(handler)
        
        self._tenant_context: Dict[str, Any] = {}
    
    def _get_json_formatter(self) -> logging.Formatter:
        """Get JSON formatter for CloudWatch."""
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': record.levelname,
                    'logger': record.name,
                    'message': record.getMessage(),
                }
                
                # Add extra fields
                if hasattr(record, 'tenant_id'):
                    log_data['tenant_id'] = record.tenant_id
                if hasattr(record, 'user_id'):
                    log_data['user_id'] = record.user_id
                if hasattr(record, 'instance_id'):
                    log_data['instance_id'] = record.instance_id
                if hasattr(record, 'security_event'):
                    log_data['security_event'] = record.security_event
                if hasattr(record, 'details'):
                    log_data['details'] = record.details
                
                return json.dumps(log_data)
        
        return JsonFormatter()
    
    def set_context(self, **kwargs):
        """Set tenant context for subsequent logs."""
        self._tenant_context.update(kwargs)
    
    def clear_context(self):
        """Clear tenant context."""
        self._tenant_context.clear()
    
    def _add_context(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add tenant context to log extra fields."""
        log_extra = self._tenant_context.copy()
        if extra:
            log_extra.update(extra)
        return log_extra
    
    def info(self, message: str, **kwargs):
        """Log info message with context."""
        self.logger.info(message, extra=self._add_context(kwargs))
    
    def warning(self, message: str, **kwargs):
        """Log warning message with context."""
        self.logger.warning(message, extra=self._add_context(kwargs))
    
    def error(self, message: str, **kwargs):
        """Log error message with context."""
        self.logger.error(message, extra=self._add_context(kwargs))
    
    def critical(self, message: str, **kwargs):
        """Log critical message with context."""
        self.logger.critical(message, extra=self._add_context(kwargs))
    
    def debug(self, message: str, **kwargs):
        """Log debug message with context."""
        self.logger.debug(message, extra=self._add_context(kwargs))
    
    def security_event(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Log security event with structured data."""
        log_data = {
            'security_event': event_type,
            'severity': severity,
            'details': details or {}
        }
        log_data.update(kwargs)
        
        if severity in ('high', 'critical'):
            self.logger.critical(message, extra=self._add_context(log_data))
        elif severity == 'medium':
            self.logger.error(message, extra=self._add_context(log_data))
        else:
            self.logger.warning(message, extra=self._add_context(log_data))
    
    def security_validation_failed(
        self,
        reason: str,
        instance_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log security validation failure."""
        self.security_event(
            event_type='validation_failed',
            severity='high',
            message=f'Security validation failed: {reason}',
            instance_id=instance_id,
            tenant_id=tenant_id,
            details=details or {}
        )
    
    def cross_tenant_attempt(
        self,
        attempted_tenant: str,
        actual_tenant: str,
        instance_id: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log cross-tenant access attempt."""
        self.security_event(
            event_type='cross_tenant_attempt',
            severity='critical',
            message='Cross-tenant access attempt detected',
            instance_id=instance_id,
            details={
                'attempted_tenant': attempted_tenant,
                'actual_tenant': actual_tenant,
                **(details or {})
            }
        )
    
    def invalid_instance(
        self,
        instance_id: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log invalid instance access."""
        self.security_event(
            event_type='invalid_instance',
            severity='high',
            message=f'Invalid instance access: {reason}',
            instance_id=instance_id,
            details=details or {}
        )
    
    def message_processed(
        self,
        message_id: str,
        tenant_id: str,
        user_id: str,
        message_type: str
    ):
        """Log successful message processing."""
        self.info(
            f'Message processed successfully: {message_id}',
            message_id=message_id,
            tenant_id=tenant_id,
            user_id=user_id,
            message_type=message_type
        )


def log_execution(func):
    """Decorator to log function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger = TenantContextLogger(func.__module__)
        logger.info(f'Executing {func.__name__}')
        try:
            result = func(*args, **kwargs)
            logger.info(f'{func.__name__} completed successfully')
            return result
        except Exception as e:
            logger.error(
                f'{func.__name__} failed: {str(e)}',
                details={'error_type': type(e).__name__}
            )
            raise
    return wrapper


# Global logger instance
def get_logger(name: str) -> TenantContextLogger:
    """Get or create logger with name."""
    return TenantContextLogger(name)

