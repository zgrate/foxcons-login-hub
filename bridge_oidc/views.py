from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib.auth import login as auth_login
from django.utils.translation import gettext_lazy as _
from instances.models import FoxconsInstance
from foxcons.services import authenticate_with_password, authenticate_with_refresh
from foxcons.client import FoxconsClientError
from oauth2_provider.exceptions import OAuthToolkitError
from oauth2_provider.views.oidc import UserInfoView
from oauth2_provider.views.base import AuthorizationView as BaseAuthorizationView
from oauth2_provider.views import TokenView
from .models import TemporaryAuthState
from .auth import SessionOnlyUser
import json


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = (color or '').strip().lstrip('#')
    if len(value) != 6:
        return 252, 165, 165
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return 252, 165, 165


def _darken_rgb(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )


def _rgb_to_css(rgb: tuple[int, int, int]) -> str:
    return f"{rgb[0]}, {rgb[1]}, {rgb[2]}"


def _theme_context_for_instance(instance: FoxconsInstance | None) -> dict:
    primary = '#fca5a5'
    secondary = '#ef4444'
    text = '#2b0a0a'
    if instance:
        primary = instance.theme_primary or primary
        secondary = instance.theme_secondary or secondary
        text = instance.theme_text or text

    primary_rgb = _hex_to_rgb(primary)
    secondary_rgb = _hex_to_rgb(secondary)
    dark_rgb = _darken_rgb(secondary_rgb, 0.52)
    navy_rgb = _darken_rgb(secondary_rgb, 0.34)

    return {
        'theme_sky': primary,
        'theme_sky_deep': secondary,
        'theme_blue': f"#{dark_rgb[0]:02x}{dark_rgb[1]:02x}{dark_rgb[2]:02x}",
        'theme_navy': f"#{navy_rgb[0]:02x}{navy_rgb[1]:02x}{navy_rgb[2]:02x}",
        'theme_accent': secondary,
        'theme_text': text,
        'theme_sky_rgb': _rgb_to_css(primary_rgb),
        'theme_accent_rgb': _rgb_to_css(secondary_rgb),
    }


def _login_rate_limit_key(request, email: str) -> str:
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ip = forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR', 'unknown')
    normalized_email = (email or '').strip().lower()
    return f"bridge-login:{ip}:{normalized_email}"


def _is_login_rate_limited(request, email: str) -> bool:
    max_attempts = max(0, int(getattr(settings, 'BRIDGE_LOGIN_RATE_LIMIT_ATTEMPTS', 10)))
    if max_attempts == 0:
        return False
    key = _login_rate_limit_key(request, email)
    attempts = int(cache.get(key, 0) or 0)
    return attempts >= max_attempts


def _record_login_attempt(request, email: str, success: bool) -> None:
    key = _login_rate_limit_key(request, email)
    if success:
        cache.delete(key)
        return

    window_seconds = max(1, int(getattr(settings, 'BRIDGE_LOGIN_RATE_LIMIT_WINDOW_SECONDS', 300)))
    added = cache.add(key, 1, timeout=window_seconds)
    if not added:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window_seconds)

def login_view(request):
    from urllib.parse import urlencode
    
    # Extract and preserve OIDC authorization parameters from request.
    # On POST, keep values from hidden fields so the flow can resume.
    oidc_params = {}
    for param in ['client_id', 'redirect_uri', 'scope', 'response_type', 'state', 'nonce', 'code_challenge', 'code_challenge_method']:
        value = request.GET.get(param) or request.POST.get(param)
        if value:
            oidc_params[param] = value

    error = None
    if request.method == 'POST':
        instance_id = request.POST.get('instance')
        email = request.POST.get('email')
        password = request.POST.get('password')
        if _is_login_rate_limited(request, email):
            error = _('Too many login attempts. Please wait a few minutes and try again.')
        else:
            try:
                instance = FoxconsInstance.objects.get(id=instance_id, is_active=True)
                normalized, token, refresh = authenticate_with_password(instance, email, password)
                request.session['selected_instance_id'] = instance.id
                request.session['selected_instance_slug'] = instance.slug
                request.session['selected_instance_base_url'] = instance.base_url
                request.session['selected_email'] = email
                request.session['foxcons_access_token'] = token
                request.session['foxcons_refresh_token'] = refresh
                request.session['normalized_claims'] = normalized.__dict__
                request.session['last_auth_at'] = str(timezone.now())
                request.session['bridge_authorize_confirmed'] = True
                request.session.save()
                _record_login_attempt(request, email, success=True)

                # Build redirect URL preserving OIDC params
                if oidc_params:
                    redirect_url = f"/o/authorize/?{urlencode(oidc_params)}"
                else:
                    redirect_url = "/o/authorize/"
                return redirect(redirect_url)
            except (FoxconsInstance.DoesNotExist, FoxconsClientError, ValueError):
                _record_login_attempt(request, email, success=False)
                error = _('Invalid credentials or instance unavailable')

    instances = FoxconsInstance.objects.filter(is_active=True).order_by('display_order', 'name')
    selected_instance_id = request.session.get('selected_instance_id')
    email = request.session.get('selected_email', '')
    selected_instance = instances.filter(id=selected_instance_id).first() if selected_instance_id else None
    selected_instance_name = selected_instance.name if selected_instance else ''

    context = {
        'instances': instances,
        'selected_instance_id': selected_instance_id,
        'selected_instance_name': selected_instance_name,
        'email': email,
        'error': error,
        'oidc_params': oidc_params,
    }
    context.update(_theme_context_for_instance(selected_instance))
    return render(request, 'bridge_oidc/login.html', context)


def continue_view(request):
    from urllib.parse import urlencode

    oidc_params = {}
    for param in ['client_id', 'redirect_uri', 'scope', 'response_type', 'state', 'nonce', 'code_challenge', 'code_challenge_method']:
        value = request.GET.get(param) or request.POST.get(param)
        if value:
            oidc_params[param] = value

    has_saved_session = (
        'foxcons_refresh_token' in request.session
        and 'selected_instance_id' in request.session
        and 'selected_email' in request.session
    )
    selected_email = request.session.get('selected_email', '')
    current_instance = FoxconsInstance.objects.filter(id=request.session.get('selected_instance_id')).first()
    if not has_saved_session:
        if oidc_params:
            return redirect(f"{reverse('bridge_oidc:login')}?{urlencode(oidc_params)}")
        return redirect(reverse('bridge_oidc:login'))

    error = None
    action = request.POST.get('action') if request.method == 'POST' else None
    allow_login_redirect = False

    if request.method == 'POST' and action == 'continue':
        if 'normalized_claims' in request.session:
            request.session['bridge_authorize_confirmed'] = True
            request.session['last_auth_at'] = request.session.get('last_auth_at', str(timezone.now()))
            request.session.save()

            if oidc_params:
                return redirect(f"/o/authorize/?{urlencode(oidc_params)}")
            return redirect('/o/authorize/')

        try:
            instance = FoxconsInstance.objects.get(id=request.session['selected_instance_id'], is_active=True)
            normalized, token, refresh = authenticate_with_refresh(
                instance,
                request.session['selected_email'],
                request.session['foxcons_refresh_token'],
            )
            request.session['foxcons_access_token'] = token
            request.session['foxcons_refresh_token'] = refresh
            request.session['normalized_claims'] = normalized.__dict__
            request.session['last_auth_at'] = str(timezone.now())
            request.session['bridge_authorize_confirmed'] = True
            request.session.save()

            if oidc_params:
                return redirect(f"/o/authorize/?{urlencode(oidc_params)}")
            return redirect('/o/authorize/')
        except (FoxconsInstance.DoesNotExist, FoxconsClientError, ValueError):
            for key in ['foxcons_access_token', 'foxcons_refresh_token', 'normalized_claims', 'last_auth_at']:
                request.session.pop(key, None)
            request.session.pop('bridge_authorize_confirmed', None)
            error = _('Your saved session could not be refreshed. Please sign in again.')
            has_saved_session = False
            allow_login_redirect = True

    elif request.method == 'POST' and action == 'switch':
        for key in ['foxcons_access_token', 'foxcons_refresh_token', 'normalized_claims', 'last_auth_at']:
            request.session.pop(key, None)
        request.session.pop('bridge_authorize_confirmed', None)
        if oidc_params:
            return redirect(f"{reverse('bridge_oidc:login')}?{urlencode(oidc_params)}")
        return redirect(reverse('bridge_oidc:login'))

    if not has_saved_session and not allow_login_redirect:
        if oidc_params:
            return redirect(f"{reverse('bridge_oidc:login')}?{urlencode(oidc_params)}")
        return redirect(reverse('bridge_oidc:login'))

    claims = request.session.get('normalized_claims', {})
    display_name = claims.get('name') or selected_email
    initial = (display_name[0] if display_name else '?').upper()
    avatar_url = claims.get('foxcons_avatar_url') or ''
    event_name = claims.get('foxcons_event_name') or (current_instance.name if current_instance else '')
    power = claims.get('foxcons_power') or ''

    context = {
        'email': selected_email,
        'display_name': display_name,
        'initial': initial,
        'avatar_url': avatar_url,
        'event_name': event_name,
        'power': power,
        'current_instance_name': current_instance.name if current_instance else request.session.get('selected_instance_slug', 'Unknown event'),
        'oidc_params': oidc_params,
        'error': error,
        'can_continue': has_saved_session,
    }
    context.update(_theme_context_for_instance(current_instance))
    return render(request, 'bridge_oidc/continue.html', context)

def logout_view(request):
    request.session.flush()
    return redirect(reverse('bridge_oidc:login'))

from django.views.decorators.csrf import csrf_exempt

class BridgeAuthorizationView(BaseAuthorizationView):
    template_name = 'bridge_oidc/authorize.html'

    def _get_oauth2_service_account(self):
        """Get or create the OAuth2 service account for Grant model."""
        from django.contrib.auth.models import User
        from django.utils import timezone
        service_user, _ = User.objects.get_or_create(
            username='_oauth2_service_account',
            defaults={
                'email': 'oauth2@bridge.local',
                'is_active': True,
                'last_login': timezone.now(),
            }
        )
        if not service_user.has_usable_password():
            service_user.set_unusable_password()
        
        # Ensure last_login is set (needed for oauth2_provider ID token generation)
        if service_user.last_login is None:
            service_user.last_login = timezone.now()
        
        service_user.save()
        return service_user

    def dispatch(self, request, *args, **kwargs):
        from urllib.parse import urlencode

        # Check if user is authenticated via bridge session
        if not request.user.is_authenticated:
            # User hasn't logged in through bridge yet
            # Redirect to bridge login, preserving OIDC params
            oidc_params = {}
            for param in ['client_id', 'redirect_uri', 'scope', 'response_type', 'state', 'nonce', 'code_challenge', 'code_challenge_method']:
                value = request.GET.get(param)
                if value:
                    oidc_params[param] = value
            
            if oidc_params:
                return redirect(f"/bridge/login/?{urlencode(oidc_params)}")
            else:
                return redirect('/bridge/login/')

        # Even if authenticated, require explicit user confirmation on login page
        # before continuing OIDC authorize flow (allows switching event/account).
        if request.method == 'GET':
            confirmed = request.session.pop('bridge_authorize_confirmed', False)
            if not confirmed:
                oidc_params = {}
                for param in ['client_id', 'redirect_uri', 'scope', 'response_type', 'state', 'nonce', 'code_challenge', 'code_challenge_method']:
                    value = request.GET.get(param)
                    if value:
                        oidc_params[param] = value
                if oidc_params:
                    return redirect(f"/bridge/continue/?{urlencode(oidc_params)}")
                return redirect('/bridge/continue/')
        
        return super().dispatch(request, *args, **kwargs)

    def _maybe_capture_auth_code(self, response):
        """
        If the authorization response redirects back with a code, store the
        current session's normalized_claims in TemporaryAuthState so that
        BridgeTokenView can attach them to the issued access token.

        This must be called on the response from both get() and post() because
        when skip_authorization=True on the Application, oauth2_provider issues
        the auth code during the GET request and never calls form_valid().
        """
        import urllib.parse
        try:
            location = response.get('Location', '')
        except AttributeError:
            return
        if 'code=' not in location:
            return
        parsed = urllib.parse.urlparse(location)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get('code', [None])[0]
        if not code:
            return
        claims = self.request.session.get('normalized_claims')
        if claims:
            TemporaryAuthState.objects.filter(auth_code=code).delete()  # prevent duplicates
            TemporaryAuthState.objects.create(auth_code=code, claims=claims)

    def get_form_kwargs(self):
        # Ensure GET parameters are passed to the form as data
        kwargs = super().get_form_kwargs()
        kwargs['data'] = self.request.GET
        return kwargs

    def get(self, request, *args, **kwargs):
        # Swap request.user with service account for oauth2_provider
        original_user = request.user
        try:
            service_user = self._get_oauth2_service_account()
            request.user = service_user
            response = super().get(request, *args, **kwargs)
            # When skip_authorization=True, the auth code is issued here (never
            # reaching form_valid), so we must capture it from the response.
            self._maybe_capture_auth_code(response)
            return response
        finally:
            request.user = original_user

    def post(self, request, *args, **kwargs):
        """
        Override POST to auto-approve authorization for the single OIDC client.
        Per spec: "no bridge-side consent screen unless OIDC library requires it"

        We use a service account user for oauth2_provider's Grant model,
        while keeping the actual user identity in session normalized_claims.
        """
        original_user = request.user
        try:
            service_user = self._get_oauth2_service_account()
            request.user = service_user
            # Auto-approve by setting authorize
            request.POST = request.POST.copy()
            request.POST['authorize'] = 'Allow'
            response = super().post(request, *args, **kwargs)
            self._maybe_capture_auth_code(response)
            return response
        finally:
            request.user = original_user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add user info from normalized claims
        claims = self.request.session.get('normalized_claims', {})
        context['user_email'] = claims.get('email', 'Unknown')
        context['user_name'] = claims.get('name', claims.get('username', 'Unknown'))
        context['logout_url'] = reverse('bridge_oidc:logout')
        instance = FoxconsInstance.objects.filter(id=self.request.session.get('selected_instance_id')).first()
        context.update(_theme_context_for_instance(instance))
        return context

    def error_response(self, error, application, **kwargs):
        # Let oauth2_provider handle errors gracefully
        return super().error_response(error, application, **kwargs)

class BridgeTokenView(TokenView):
    def create_token_response(self, request):
        """
        Intercept token issuance to store Foxcons claims in FoxconsTokenClaims,
        keyed by the access token string, so the validator can return them later
        during userinfo and refresh flows.
        """
        from .models import FoxconsTokenClaims
        claims = None

        # Auth-code grant: look up claims from TemporaryAuthState
        code = request.POST.get('code')
        if code:
            auth_state = TemporaryAuthState.objects.filter(auth_code=code).first()
            if auth_state and not auth_state.is_expired():
                claims = auth_state.claims

        # Refresh token grant: copy claims from existing FoxconsTokenClaims
        if not claims:
            refresh_token_str = request.POST.get('refresh_token')
            if refresh_token_str:
                try:
                    from oauth2_provider.models import RefreshToken as OAuthRefreshToken
                    old_refresh = OAuthRefreshToken.objects.filter(token=refresh_token_str).select_related('access_token').first()
                    if old_refresh and old_refresh.access_token:
                        old_claims = FoxconsTokenClaims.objects.filter(
                            access_token_key=old_refresh.access_token.token
                        ).first()
                        if old_claims:
                            claims = old_claims.claims
                except Exception:
                    pass

        url, headers, body, status = super().create_token_response(request)

        # Store claims in FoxconsTokenClaims for the new access token
        if claims and body:
            try:
                body_data = json.loads(body)
                new_token_str = body_data.get('access_token')
                if new_token_str:
                    FoxconsTokenClaims.objects.update_or_create(
                        access_token_key=new_token_str,
                        defaults={'claims': claims},
                    )
            except Exception:
                pass

        return url, headers, body, status


class BridgeUserInfoView(UserInfoView):
    """
    Userinfo endpoint. Claims are returned by BridgeOAuth2Validator.get_additional_claims,
    which reads from FoxconsTokenClaims keyed by the bearer access token string.
    """
    pass
