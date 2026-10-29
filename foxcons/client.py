import time
import requests
from typing import Optional
from .types import LoginResponse, AuthProfile, EventProfile

class FoxconsClientError(Exception):
    pass

class InvalidCredentialsError(FoxconsClientError):
    pass

class NetworkError(FoxconsClientError):
    pass

class InvalidResponseError(FoxconsClientError):
    pass

class RefreshTokenError(FoxconsClientError):
    pass

def normalize_base_url(base_url: str) -> str:
    return base_url[:-1] if base_url.endswith('/') else base_url

class FoxconsClient:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        from bridge_oidc.audit import audit  # lazy: bridge_oidc imports this module

        started = time.monotonic()
        try:
            response = getattr(requests, method.lower())(url, timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            audit('upstream_error', success=False, path=url, message=f"{method} {type(e).__name__}: {e}",
                  duration_ms=int((time.monotonic() - started) * 1000))
            raise
        failed = response.status_code >= 400
        audit('upstream_call', success=not failed, path=url, status_code=response.status_code,
              duration_ms=int((time.monotonic() - started) * 1000),
              message=f"{method} {response.status_code}", details={'body': response.text} if failed else None)
        return response

    def login(self, base_url: str, username: str, password: str) -> LoginResponse:
        url = f"{normalize_base_url(base_url)}/app/auth/login"
        data = {"username": username, "password": password}
        try:
            response = self._request('POST', url, json=data)
            if response.status_code == 401:
                raise InvalidCredentialsError("Invalid credentials")
            response.raise_for_status()
            json_data = response.json()
            return LoginResponse(
                token=json_data['token'],
                refresh_token=json_data['refreshToken']
            )
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}")
        except (KeyError, ValueError) as e:
            raise InvalidResponseError(f"Invalid response: {e}")

    def refresh(self, base_url: str, refresh_token: str) -> LoginResponse:
        url = f"{normalize_base_url(base_url)}/app/auth/refresh-token"
        data = {"refreshToken": refresh_token}
        try:
            response = self._request('POST', url, json=data)
            if response.status_code == 401:
                raise RefreshTokenError("Invalid refresh token")
            response.raise_for_status()
            json_data = response.json()
            return LoginResponse(
                token=json_data['token'],
                refresh_token=json_data['refreshToken']
            )
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}")
        except (KeyError, ValueError) as e:
            raise InvalidResponseError(f"Invalid response: {e}")

    def get_auth_profile(self, base_url: str, access_token: str) -> AuthProfile:
        url = f"{normalize_base_url(base_url)}/app/auth/profile"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = self._request('GET', url, headers=headers)
            response.raise_for_status()
            json_data = response.json()
            return AuthProfile(
                session_id=json_data.get('sessionId'),
                id=json_data.get('id'),
                account_type=json_data.get('accountType'),
                flags=json_data.get('flags', []),
                display_name=json_data.get('displayName'),
                language=json_data.get('language'),
                is_uw_u=json_data.get('isUwU')
            )
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}")
        except (KeyError, ValueError) as e:
            raise InvalidResponseError(f"Invalid response: {e}")

    def get_event_profile(self, base_url: str, access_token: str) -> EventProfile:
        url = f"{normalize_base_url(base_url)}/app/event/profile"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = self._request('GET', url, headers=headers)
            response.raise_for_status()
            json_data = response.json()
            return EventProfile(
                id=json_data.get('id'),
                power=json_data.get('power'),
                display_name=json_data.get('displayName'),
                avatar_file=json_data.get('avatarFile'),
                bourgeois_status=json_data.get('bourgeoisStatus'),
                room=json_data.get('room'),
                flags=json_data.get('flags', []),
                frame_type=json_data.get('frameType'),
                contact=json_data.get('contact', {}),
                updated_at=json_data.get('updatedAt'),
                is_hidden=json_data.get('isHidden'),
                first_name=json_data.get('firstName'),
                last_name=json_data.get('lastName'),
                event_name=json_data.get('eventName'),
                additional_permissions=json_data.get('additionalPermissions', [])
            )
        except requests.RequestException as e:
            raise NetworkError(f"Network error: {e}")
        except (KeyError, ValueError) as e:
            raise InvalidResponseError(f"Invalid response: {e}")