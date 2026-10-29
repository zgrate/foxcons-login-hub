from django.db import models
from django.utils import timezone
from datetime import timedelta
from oauth2_provider.settings import oauth2_settings

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


class ApplicationSettings(models.Model):
    """Bridge-specific per-client switches, edited inline on the OAuth Application admin."""
    application = models.OneToOneField(
        oauth2_settings.APPLICATION_MODEL, on_delete=models.CASCADE, related_name='bridge_settings'
    )
    pkce_required = models.BooleanField(
        default=True,
        help_text='Turn off only for clients that cannot send code_challenge (e.g. Moodle).',
    )

    def __str__(self):
        return f"Settings for {self.application}"


class AuditLog(models.Model):
    """One row per bridge operation (login, refresh, authorize, token, upstream call…) for debugging."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    event = models.CharField(max_length=64, db_index=True)
    success = models.BooleanField(default=True)
    email = models.CharField(max_length=255, blank=True)
    instance_slug = models.CharField(max_length=255, blank=True)
    client_id = models.CharField(max_length=255, blank=True)
    ip = models.CharField(max_length=64, blank=True)
    path = models.CharField(max_length=512, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.event} {'ok' if self.success else 'FAIL'}"
