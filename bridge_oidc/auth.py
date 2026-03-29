"""
Session-only authentication backend for bridge OIDC.
Authenticates users via session data without persisting User objects.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import AnonymousUser
import hashlib


class SessionOnlyUser:
    """
    In-memory user object for session-based authentication.
    
    This user exists only in the request session and is never persisted to the database.
    It provides the minimal interface needed by Django's auth system.
    """
    is_authenticated = True
    is_active = True
    is_staff = False
    is_superuser = False
    
    def __init__(self, username):
        self.username = username
        # Generate a stable but non-persistent ID based on username
        # This allows Django's session system to work with this user
        self.id = int(hashlib.md5(username.encode()).hexdigest()[:8], 16) % (2**31)
        self.pk = self.id
        
    def get_username(self):
        return self.username
    
    def __str__(self):
        return self.username


class BridgeSessionBackend(ModelBackend):
    """
    Custom authentication backend for OIDC bridge.
    
    Authenticates users based on session data without creating persistent User records.
    Used only during the OIDC flow after Foxcons authentication succeeds.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate using session-based user if available.
        Returns None to allow other backends to try.
        """
        # Only authenticate if we have session-based normalized claims
        if request and hasattr(request, 'session'):
            if 'normalized_claims' in request.session:
                username = request.session.get('selected_email')
                if username:
                    return SessionOnlyUser(username=username)
        return None
    
    def get_user(self, user_id):
        """Cannot retrieve session users by ID."""
        return None

