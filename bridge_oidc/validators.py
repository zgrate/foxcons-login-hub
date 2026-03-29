"""
Custom OAuth2 validator for the Foxcons OIDC bridge.

Trust boundary: this module bridges oauthlib's claim-building hooks with
the Foxcons-derived identity stored in:
  - TemporaryAuthState  (keyed by auth code, used during token exchange)
  - FoxconsTokenClaims  (keyed by access token string, used for userinfo / refresh)
"""

import logging

from oauth2_provider.oauth2_validators import OAuth2Validator

logger = logging.getLogger(__name__)

# All claims our validator can return, mapped to the scope that gates them.
# Standard OIDC claims use their standard scope; foxcons_* claims are gated on
# "openid" so they are always emitted when the OIDC flow is used.
_FOXCONS_CLAIM_SCOPE = {
    # standard claims inherited from the base class (reproduced for our foxcons sub override)
    "sub": "openid",
    "email": "email",
    "email_verified": "email",
    "name": "profile",
    "preferred_username": "profile",
    "locale": "profile",
    "groups": "openid",
    "flags": "openid",
    "additional_permissions": "openid",
    "account_type": "openid",
    "power": "openid",
    "event_name": "openid",
    # foxcons_* custom claims — gate on openid so they travel in every OIDC token
    "foxcons_instance": "openid",
    "foxcons_event_name": "openid",
    "foxcons_user_id": "openid",
    "foxcons_session_id": "openid",
    "foxcons_account_type": "openid",
    "foxcons_power": "openid",
    "foxcons_flags": "openid",
    "foxcons_additional_permissions": "openid",
    "foxcons_bourgeois_status": "openid",
    "foxcons_first_name": "openid",
    "foxcons_last_name": "openid",
}


class BridgeOAuth2Validator(OAuth2Validator):
    """
    Provides Foxcons-derived identity claims to oauthlib's claim-building pipeline.

    ``get_additional_claims`` is called by ``get_claim_dict``, whose result is
    used by both ``finalize_id_token`` (ID token) and ``get_userinfo_claims``
    (userinfo endpoint).  Returning ``sub`` here overrides the default service-
    account primary key.

    Lookup priority:
      1. Auth-code token exchange – ``request.code`` is the auth code →
         look up TemporaryAuthState.
      2. Userinfo / refresh – ``request.access_token`` is the AccessToken DB
         object → look up FoxconsTokenClaims by its token string.
    """

    # Extend the parent scope map with our custom foxcons_* claims so that
    # get_oidc_claims does not filter them out.
    oidc_claim_scope = OAuth2Validator.oidc_claim_scope.copy()
    oidc_claim_scope.update(_FOXCONS_CLAIM_SCOPE)

    @staticmethod
    def _ensure_alias_claims(claims):
        """Backfill alias claims for tokens/sessions created before alias support."""
        if not isinstance(claims, dict):
            return {}

        out = {k: v for k, v in claims.items() if v is not None}
        if 'flags' not in out and 'foxcons_flags' in out:
            out['flags'] = out['foxcons_flags']
        if 'additional_permissions' not in out and 'foxcons_additional_permissions' in out:
            out['additional_permissions'] = out['foxcons_additional_permissions']
        if 'account_type' not in out and 'foxcons_account_type' in out:
            out['account_type'] = out['foxcons_account_type']
        if 'power' not in out and 'foxcons_power' in out:
            out['power'] = out['foxcons_power']
        if 'event_name' not in out and 'foxcons_event_name' in out:
            out['event_name'] = out['foxcons_event_name']
        if 'groups' not in out:
            event_scope = out.get('event_name') or out.get('foxcons_event_name')
            instance_scope = out.get('foxcons_instance')
            group_candidates = [
                f"instance:{instance_scope}:{event_scope}:{out.get('foxcons_instance')}" if (instance_scope and event_scope and out.get('foxcons_instance')) else None,
                f"event:{instance_scope}:{event_scope}:member" if (instance_scope and event_scope) else None,
                f"account:{instance_scope}:{event_scope}:{out.get('account_type') or out.get('foxcons_account_type')}" if (instance_scope and event_scope and (out.get('account_type') or out.get('foxcons_account_type'))) else None,
                f"power:{instance_scope}:{event_scope}:{out.get('power') or out.get('foxcons_power')}" if (instance_scope and event_scope and (out.get('power') or out.get('foxcons_power'))) else None,
            ]
            for perm in out.get('additional_permissions', []):
                if instance_scope and event_scope:
                    group_candidates.append(f"perm:{instance_scope}:{event_scope}:{perm}")
            out['groups'] = list(dict.fromkeys([g for g in group_candidates if g]))

        return out

    def get_additional_claims(self, request):
        from .models import TemporaryAuthState, FoxconsTokenClaims

        # ── Auth-code token exchange ──────────────────────────────────────
        # oauthlib populates request.code from the POST body before calling
        # validate_code / finalize_id_token.
        code = getattr(request, 'code', None)
        if code:
            try:
                auth_state = TemporaryAuthState.objects.filter(auth_code=code).first()
                if auth_state and not auth_state.is_expired():
                    return self._ensure_alias_claims(auth_state.claims)
            except Exception:
                logger.exception("Error reading TemporaryAuthState for code in get_additional_claims")

        # ── Userinfo / refresh ────────────────────────────────────────────
        # After validate_bearer_token, request.access_token is the AccessToken
        # DB object.  BridgeTokenView stores claims in FoxconsTokenClaims keyed
        # by its token string immediately after issuance.
        access_token = getattr(request, 'access_token', None)
        token_str = getattr(access_token, 'token', None)
        if token_str:
            try:
                token_claims = FoxconsTokenClaims.objects.filter(access_token_key=token_str).first()
                if token_claims:
                    return self._ensure_alias_claims(token_claims.claims)
            except Exception:
                logger.exception("Error reading FoxconsTokenClaims in get_additional_claims")

        return {}
