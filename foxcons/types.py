from dataclasses import dataclass
from typing import List, Optional

@dataclass
class LoginResponse:
    token: str
    refresh_token: str

@dataclass
class AuthProfile:
    session_id: int
    id: int
    account_type: str
    flags: List[str]
    display_name: str
    language: str
    is_uw_u: bool

@dataclass
class EventProfile:
    id: int
    power: str
    display_name: str
    avatar_file: Optional[dict]
    bourgeois_status: str
    room: Optional[int]
    flags: List[str]
    frame_type: dict
    contact: dict
    updated_at: str
    is_hidden: Optional[bool]
    first_name: str
    last_name: str
    event_name: str
    additional_permissions: List[str]

@dataclass
class NormalizedIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str
    preferred_username: str
    username: str
    locale: Optional[str]
    foxcons_user_id: int
    foxcons_session_id: int
    foxcons_account_type: str
    foxcons_power: str
    foxcons_event_name: str
    foxcons_instance: str
    foxcons_bourgeois_status: str
    foxcons_additional_permissions: List[str]
    foxcons_first_name: str
    foxcons_last_name: str
    foxcons_flags: List[str]
    foxcons_avatar_url: Optional[str]
    # Plain aliases for consumers that expect non-prefixed claim names.
    flags: List[str]
    groups: List[str]
    additional_permissions: List[str]
    account_type: str
    power: str
    event_name: str