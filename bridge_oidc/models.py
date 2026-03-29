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

    def __str__(self):
        return f"Claims for token {self.access_token_key[:12]}…"
