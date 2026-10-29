import logging

logger = logging.getLogger(__name__)

MAX_TEXT = 2000
_SECRET_MARKERS = ('password', 'token', 'secret', 'code')


def client_ip(request) -> str:
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR', 'unknown')


def _clean_details(details: dict) -> dict:
    out = {}
    for key, value in (details or {}).items():
        if any(marker in key.lower() for marker in _SECRET_MARKERS):
            continue
        out[key] = value[:MAX_TEXT] if isinstance(value, str) else value
    return out


def audit(event, request=None, success=True, details=None, **fields):
    """Record an AuditLog row and mirror it to the console. Never raises."""
    from .models import AuditLog

    try:
        if request is not None:
            session = getattr(request, 'session', None) or {}
            fields.setdefault('ip', client_ip(request))
            fields.setdefault('path', request.path[:512])
            fields.setdefault('email', session.get('selected_email') or '')
            fields.setdefault('instance_slug', session.get('selected_instance_slug') or '')
        fields = {k: v for k, v in fields.items() if v is not None}
        fields['message'] = str(fields.get('message', ''))[:MAX_TEXT]
        details = _clean_details(details)
        AuditLog.objects.create(event=event, success=success, details=details, **fields)
        logger.log(
            logging.INFO if success else logging.WARNING,
            '%s success=%s %s details=%s',
            event, success, ' '.join(f'{k}={v}' for k, v in fields.items() if v != ''), details,
        )
    except Exception:
        logger.exception('Failed to write audit log for event %s', event)
