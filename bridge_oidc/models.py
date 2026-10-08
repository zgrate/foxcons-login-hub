from django.db import models
from django.utils import timezone
from datetime import timedelta

class TemporaryAuthState(models.Model):
    """Store normalized claims indexed by authorization code"""
    auth_code = models.CharField(max_length=255, unique=True, db_index=True)
    claims = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def is_expired(self):
        return timezone.now() - self.created_at > timedelta(minutes=10)
    
    def __str__(self):
        return f"AuthState for code {self.auth_code}"


class FoxconsTokenClaims(models.Model):
    """
    Persistent store of Foxcons-derived identity claims for issued access tokens.

    Keyed by the access token string so BridgeOAuth2Validator.get_additional_claims
    can look up the full claim set during userinfo and refresh flows — after the
    one-time authorization code (and its TemporaryAuthState) is gone.

    Rows are created by BridgeTokenView immediately after token issuance and
    cleared by the oauth2_provider token cleanup (cascade on AccessToken delete).
    """
    access_token_key = models.CharField(max_length=255, unique=True, db_index=True)
    claims = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        from django.conf import settings
        ttl_seconds = settings.BRIDGE_TOKEN_CLAIMS_TTL_SECONDS
        return timezone.now() - self.created_at > timedelta(seconds=ttl_seconds)

    def __str__(self):
        return f"Claims for token {self.access_token_key[:12]}…"


class EmailLoginCode(models.Model):
    """
    One-time verification code for the email-only fallback login.

    Used when a FoxconsInstance has purged its event data and the normal
    password-based login can no longer succeed. The code is hashed at rest
    since, unlike the external Foxcons password, it is a credential this
    app itself issues and must verify.
    """
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed = models.BooleanField(default=False)

    def is_valid(self):
        return not self.consumed and timezone.now() < self.expires_at

    def __str__(self):
        return f"EmailLoginCode for {self.email}"
