from .client import FoxconsClient, FoxconsClientError
from .types import NormalizedIdentity, AuthProfile, EventProfile
from instances.models import FoxconsInstance
from typing import Tuple

def authenticate_with_password(instance: FoxconsInstance, email: str, password: str) -> Tuple[NormalizedIdentity, str, str]:
    if not email or not email.strip():
        raise ValueError("Email is required")
    client = FoxconsClient()
    try:
        login_response = client.login(instance.base_url, email, password)
        auth_profile = client.get_auth_profile(instance.base_url, login_response.token)
        event_profile = client.get_event_profile(instance.base_url, login_response.token)
        if auth_profile.id != event_profile.id:
            raise ValueError("Mismatched user IDs")
        normalized = normalize_identity(instance, email, auth_profile, event_profile)
        return normalized, login_response.token, login_response.refresh_token
    except FoxconsClientError:
        raise

def authenticate_with_refresh(instance: FoxconsInstance, email: str, refresh_token: str) -> Tuple[NormalizedIdentity, str, str]:
    client = FoxconsClient()
    try:
        login_response = client.refresh(instance.base_url, refresh_token)
        auth_profile = client.get_auth_profile(instance.base_url, login_response.token)
        event_profile = client.get_event_profile(instance.base_url, login_response.token)
        if auth_profile.id != event_profile.id:
            raise ValueError("Mismatched user IDs")
        normalized = normalize_identity(instance, email, auth_profile, event_profile)
        return normalized, login_response.token, login_response.refresh_token
    except FoxconsClientError:
        raise

def normalize_identity(instance: FoxconsInstance, email: str, auth_profile: AuthProfile, event_profile: EventProfile) -> NormalizedIdentity:
    # Deduplicate flags
    flags = list(dict.fromkeys(auth_profile.flags))  # preserve order
    email_verified = "confirmed" in flags

    name = auth_profile.display_name or event_profile.display_name
    locale = auth_profile.language if auth_profile.language else None

    sub = f"foxcons:{instance.slug}:{email}"
    additional_permissions = list(event_profile.additional_permissions or [])

    # Build event-aware groups as type:instance-slug:event-name:value for downstream mapping.
    # Keep order stable and deduplicate.
    event_scope = event_profile.event_name
    instance_scope = instance.slug
    group_candidates = [
        f"instance:{instance_scope}:{event_scope}:{instance.slug}",
        f"event:{instance_scope}:{event_scope}:member",
        f"account:{instance_scope}:{event_scope}:{auth_profile.account_type}",
        f"power:{instance_scope}:{event_scope}:{event_profile.power}",
    ] + [f"perm:{instance_scope}:{event_scope}:{perm}" for perm in additional_permissions]
    groups = list(dict.fromkeys([g for g in group_candidates if g and g.strip()]))

    # Build avatar URL from event profile avatar file id (public Foxcons files endpoint).
    avatar_file = event_profile.avatar_file
    foxcons_avatar_url = None
    if isinstance(avatar_file, dict) and avatar_file.get('id'):
        foxcons_avatar_url = (
            f"{instance.base_url}/app/event/default/files/{avatar_file['id']}?size=std-small"
        )

    return NormalizedIdentity(
        sub=sub,
        email=email,
        email_verified=email_verified,
        name=name,
        preferred_username=email,
        username=email,
        locale=locale,
        foxcons_user_id=auth_profile.id,
        foxcons_session_id=auth_profile.session_id,
        foxcons_account_type=auth_profile.account_type,
        foxcons_power=event_profile.power,
        foxcons_event_name=event_profile.event_name,
        foxcons_instance=instance.slug,
        foxcons_bourgeois_status=event_profile.bourgeois_status,
        foxcons_additional_permissions=additional_permissions,
        foxcons_first_name=event_profile.first_name,
        foxcons_last_name=event_profile.last_name,
        foxcons_flags=flags,
        foxcons_avatar_url=foxcons_avatar_url,
        flags=flags,
        groups=groups,
        additional_permissions=additional_permissions,
        account_type=auth_profile.account_type,
        power=event_profile.power,
        event_name=event_profile.event_name,
    )