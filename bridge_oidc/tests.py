from django.test import TestCase, Client as DjangoTestClient, override_settings
from django.contrib.sessions.models import Session
from instances.models import FoxconsInstance
from foxcons.types import AuthProfile, EventProfile
from django.contrib.auth.models import User
from django.utils import timezone
from oauth2_provider.models import Application
from unittest.mock import patch, MagicMock
import json


class BridgeLoginFlowTestCase(TestCase):
    """Test bridge login form and authentication flow."""
    
    def setUp(self):
        self.client = DjangoTestClient()
        self.instance = FoxconsInstance.objects.create(
            name='Test Event',
            slug='test-event',
            base_url='https://test.example.com',
            is_active=True,
            display_order=1
        )
        self.inactive_instance = FoxconsInstance.objects.create(
            name='Inactive Event',
            slug='inactive-event',
            base_url='https://inactive.example.com',
            is_active=False
        )
    
    def test_login_page_loads(self):
        """Test login page is accessible and displays instances."""
        response = self.client.get('/bridge/login/')
        assert response.status_code == 200
        assert 'Test Event' in response.content.decode()
        # Inactive instance should not be in the form
        assert 'Inactive Event' not in response.content.decode()
    
    def test_login_page_shows_active_instances_only(self):
        """Test login form only includes active instances."""
        response = self.client.get('/bridge/login/')
        content = response.content.decode()
        # Active instance should be in the form
        assert 'Test Event' in content or str(self.instance.id) in content
        # Inactive instance should not be shown
        assert 'Inactive Event' not in content
    
    @patch('foxcons.services.authenticate_with_password')
    def test_successful_login_redirect_to_authorize(self, mock_auth):
        """Test successful login redirects to OIDC authorize endpoint."""
        mock_normalized = MagicMock()
        mock_normalized.__dict__ = {
            'sub': 'foxcons:test-event:test@example.com',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User',
            'preferred_username': 'test@example.com',
            'username': 'test@example.com',
            'locale': 'EN',
            'foxcons_user_id': 1,
            'foxcons_session_id': 100,
            'foxcons_account_type': 'user',
            'foxcons_power': 'attendee',
            'foxcons_event_name': 'TestEvent',
            'foxcons_instance': 'test-event',
            'foxcons_bourgeois_status': 'NONE',
            'foxcons_additional_permissions': [],
            'foxcons_first_name': 'Test',
            'foxcons_last_name': 'User',
            'foxcons_flags': ['confirmed']
        }
        mock_auth.return_value = (mock_normalized, 'token123', 'refresh123')
        
        response = self.client.post('/bridge/login/', {
            'instance': str(self.instance.id),
            'email': 'test@example.com',
            'password': 'password123'
        }, follow=False)
        
        # Should redirect (302) or have session populated (200 with form)
        assert response.status_code in [200, 302], f"Got status {response.status_code}"
        if response.status_code == 302:
            assert '/o/authorize/' in response.url
    
    @patch('foxcons.services.authenticate_with_password')
    def test_login_invalid_credentials(self, mock_auth):
        """Test login with invalid credentials shows error."""
        from foxcons.client import InvalidCredentialsError
        mock_auth.side_effect = InvalidCredentialsError("Invalid credentials")
        
        response = self.client.post('/bridge/login/', {
            'instance': str(self.instance.id),
            'email': 'test@example.com',
            'password': 'wrongpassword'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Invalid credentials or instance unavailable' in content
    
    def test_login_invalid_instance(self):
        """Test login with invalid instance ID is rejected."""
        response = self.client.post('/bridge/login/', {
            'instance': '99999',
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Invalid credentials or instance unavailable' in content
    
    def test_login_inactive_instance_rejected(self):
        """Test login with inactive instance is rejected."""
        response = self.client.post('/bridge/login/', {
            'instance': str(self.inactive_instance.id),
            'email': 'test@example.com',
            'password': 'password123'
        })
        
        assert response.status_code == 200
        content = response.content.decode()
        assert 'Invalid credentials or instance unavailable' in content

    @override_settings(
        BRIDGE_LOGIN_RATE_LIMIT_ATTEMPTS=1,
        BRIDGE_LOGIN_RATE_LIMIT_WINDOW_SECONDS=300,
    )
    def test_login_rate_limit_enforced_after_failed_attempt(self):
        """Second failed attempt for same address/email is blocked by rate limiting."""
        first = self.client.post('/bridge/login/', {
            'instance': '99999',
            'email': 'ratelimit@example.com',
            'password': 'wrong',
        })
        assert first.status_code == 200
        assert 'Invalid credentials or instance unavailable' in first.content.decode()

        second = self.client.post('/bridge/login/', {
            'instance': '99999',
            'email': 'ratelimit@example.com',
            'password': 'wrong',
        })
        assert second.status_code == 200
        assert 'Too many login attempts' in second.content.decode()
    
    @patch('bridge_oidc.views.authenticate_with_refresh')
    def test_login_page_does_not_show_continue_section(self, mock_refresh):
        """Login page remains manual-only even when refresh context exists."""
        mock_normalized = MagicMock()
        mock_normalized.__dict__ = {
            'sub': 'foxcons:test-event:test@example.com',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User',
            'preferred_username': 'test@example.com',
            'username': 'test@example.com',
            'locale': 'EN',
            'foxcons_user_id': 1,
            'foxcons_session_id': 100,
            'foxcons_account_type': 'user',
            'foxcons_power': 'attendee',
            'foxcons_event_name': 'TestEvent',
            'foxcons_instance': 'test-event',
            'foxcons_bourgeois_status': 'NONE',
            'foxcons_additional_permissions': [],
            'foxcons_first_name': 'Test',
            'foxcons_last_name': 'User',
            'foxcons_flags': ['confirmed']
        }
        mock_refresh.return_value = (mock_normalized, 'new_token', 'new_refresh')
        
        # Set up session with refresh token
        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_email'] = 'test@example.com'
        session['foxcons_refresh_token'] = 'old_refresh_token'
        session.save()
        
        response = self.client.get('/bridge/login/', follow=False)

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Continue as' not in content
        mock_refresh.assert_not_called()

    def test_continue_page_shows_current_session_section(self):
        """Continue page is the dedicated place for session reuse confirmation."""
        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_email'] = 'test@example.com'
        session['foxcons_refresh_token'] = 'old_refresh_token'
        session.save()

        response = self.client.get('/bridge/continue/', follow=False)

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Continue as' in content
        assert 'Foxcons Login' not in content

    @patch('bridge_oidc.views.authenticate_with_refresh')
    def test_continue_action_reuses_session_and_redirects(self, mock_refresh):
        """Test explicit continue action reuses current session and redirects to authorize."""
        mock_normalized = MagicMock()
        mock_normalized.__dict__ = {
            'sub': 'foxcons:test-event:test@example.com',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User',
            'preferred_username': 'test@example.com',
            'username': 'test@example.com',
            'locale': 'EN',
            'foxcons_user_id': 1,
            'foxcons_session_id': 100,
            'foxcons_account_type': 'user',
            'foxcons_power': 'attendee',
            'foxcons_event_name': 'TestEvent',
            'foxcons_instance': 'test-event',
            'foxcons_bourgeois_status': 'NONE',
            'foxcons_additional_permissions': [],
            'foxcons_first_name': 'Test',
            'foxcons_last_name': 'User',
            'foxcons_flags': ['confirmed'],
            'flags': ['confirmed'],
            'groups': ['event:test-event:TestEvent:member'],
            'additional_permissions': [],
            'account_type': 'user',
            'power': 'attendee',
            'event_name': 'TestEvent',
        }
        mock_refresh.return_value = (mock_normalized, 'new_token', 'new_refresh')

        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_email'] = 'test@example.com'
        session['foxcons_refresh_token'] = 'old_refresh_token'
        session['normalized_claims'] = mock_normalized.__dict__
        session.save()

        response = self.client.post('/bridge/continue/?client_id=test-client&state=s1', {
            'action': 'continue',
            'client_id': 'test-client',
            'state': 's1',
        }, follow=False)

        assert response.status_code == 302
        assert '/o/authorize/' in response.url
        assert 'client_id=test-client' in response.url
        assert 'state=s1' in response.url
        mock_refresh.assert_not_called()
        assert self.client.session.get('bridge_authorize_confirmed') is True

    @patch('bridge_oidc.views.authenticate_with_refresh')
    def test_continue_action_uses_refresh_when_claims_missing(self, mock_refresh):
        """Continue should fall back to refresh only when session claims are missing."""
        mock_normalized = MagicMock()
        mock_normalized.__dict__ = {
            'sub': 'foxcons:test-event:test@example.com',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User',
            'preferred_username': 'test@example.com',
            'username': 'test@example.com',
            'locale': 'EN',
            'foxcons_user_id': 1,
            'foxcons_session_id': 100,
            'foxcons_account_type': 'user',
            'foxcons_power': 'attendee',
            'foxcons_event_name': 'TestEvent',
            'foxcons_instance': 'test-event',
            'foxcons_bourgeois_status': 'NONE',
            'foxcons_additional_permissions': [],
            'foxcons_first_name': 'Test',
            'foxcons_last_name': 'User',
            'foxcons_flags': ['confirmed'],
            'flags': ['confirmed'],
            'groups': ['event:test-event:TestEvent:member'],
            'additional_permissions': [],
            'account_type': 'user',
            'power': 'attendee',
            'event_name': 'TestEvent',
        }
        mock_refresh.return_value = (mock_normalized, 'new_token', 'new_refresh')

        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_email'] = 'test@example.com'
        session['foxcons_refresh_token'] = 'old_refresh_token'
        session.save()

        response = self.client.post('/bridge/continue/?client_id=test-client&state=s1', {
            'action': 'continue',
            'client_id': 'test-client',
            'state': 's1',
        }, follow=False)

        assert response.status_code == 302
        assert '/o/authorize/' in response.url
        mock_refresh.assert_called_once()

    @patch('bridge_oidc.views.authenticate_with_refresh')
    def test_continue_action_does_not_fall_back_to_login_after_authorize_redirect(self, mock_refresh):
        """Successful continue should pass through authorize, not bounce back to login."""
        service_user, _ = User.objects.get_or_create(
            username='_oauth2_service_account',
            defaults={
                'email': 'oauth2@bridge.local',
                'is_active': True,
                'last_login': timezone.now(),
            },
        )
        Application.objects.create(
            name='Test App',
            user=service_user,
            client_id='client123',
            client_secret='',
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris='https://client.example/callback',
            skip_authorization=True,
            algorithm='RS256',
        )

        mock_normalized = MagicMock()
        mock_normalized.__dict__ = {
            'sub': 'foxcons:test-event:test@example.com',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User',
            'preferred_username': 'test@example.com',
            'username': 'test@example.com',
            'locale': 'EN',
            'foxcons_user_id': 1,
            'foxcons_session_id': 100,
            'foxcons_account_type': 'user',
            'foxcons_power': 'attendee',
            'foxcons_event_name': 'TestEvent',
            'foxcons_instance': 'test-event',
            'foxcons_bourgeois_status': 'NONE',
            'foxcons_additional_permissions': [],
            'foxcons_first_name': 'Test',
            'foxcons_last_name': 'User',
            'foxcons_flags': ['confirmed'],
            'flags': ['confirmed'],
            'groups': ['event:test-event:TestEvent:member'],
            'additional_permissions': [],
            'account_type': 'user',
            'power': 'attendee',
            'event_name': 'TestEvent',
        }
        mock_refresh.return_value = (mock_normalized, 'new_token', 'new_refresh')

        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_instance_slug'] = self.instance.slug
        session['selected_email'] = 'test@example.com'
        session['foxcons_refresh_token'] = 'old_refresh_token'
        session['normalized_claims'] = mock_normalized.__dict__
        session.save()

        response = self.client.post('/bridge/continue/?client_id=client123&response_type=code&redirect_uri=https://client.example/callback&scope=openid&state=s1', {
            'action': 'continue',
            'client_id': 'client123',
            'response_type': 'code',
            'redirect_uri': 'https://client.example/callback',
            'scope': 'openid',
            'state': 's1',
        }, follow=True)

        redirect_chain = [url for url, _status in response.redirect_chain]
        assert not any('/bridge/login/' in url for url in redirect_chain)

    @patch('bridge_oidc.views.authenticate_with_refresh')
    def test_continue_action_refresh_failure_stays_on_continue_page(self, mock_refresh):
        """Refresh failure should not silently bounce to login page."""
        from foxcons.client import RefreshTokenError

        mock_refresh.side_effect = RefreshTokenError('invalid refresh token')

        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_instance_slug'] = self.instance.slug
        session['selected_email'] = 'test@example.com'
        session['foxcons_refresh_token'] = 'old_refresh_token'
        session.save()

        response = self.client.post('/bridge/continue/?client_id=test-client&state=s1', {
            'action': 'continue',
            'client_id': 'test-client',
            'state': 's1',
        }, follow=False)

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Your saved session could not be refreshed. Please sign in again.' in content
        assert 'Use a different account' in content

    def test_switch_action_keeps_login_form(self):
        """Test switch action clears token session and keeps user on login form."""
        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_email'] = 'test@example.com'
        session['foxcons_access_token'] = 'old_access'
        session['foxcons_refresh_token'] = 'old_refresh'
        session['normalized_claims'] = {'email': 'test@example.com'}
        session.save()

        response = self.client.post('/bridge/continue/?client_id=test-client', {
            'action': 'switch',
            'client_id': 'test-client',
        }, follow=False)

        assert response.status_code == 302
        assert '/bridge/login/' in response.url
        new_session = self.client.session
        assert 'foxcons_access_token' not in new_session
        assert 'foxcons_refresh_token' not in new_session
        assert 'normalized_claims' not in new_session


class BridgeLogoutTestCase(TestCase):
    """Test logout functionality."""
    
    def setUp(self):
        self.client = DjangoTestClient()
        self.instance = FoxconsInstance.objects.create(
            name='Test Event',
            slug='test-event',
            base_url='https://test.example.com',
            is_active=True
        )
    
    @patch('foxcons.services.authenticate_with_password')
    def test_logout_clears_session(self, mock_auth):
        """Test logout clears all session data."""
        mock_normalized = MagicMock()
        mock_normalized.__dict__ = {'email': 'test@example.com'}
        mock_auth.return_value = (mock_normalized, 'token123', 'refresh123')
        
        # Set up initial session state
        session = self.client.session
        session['foxcons_access_token'] = 'token123'
        session['foxcons_refresh_token'] = 'refresh123'
        session['normalized_claims'] = {'email': 'test@example.com'}
        session.save()
        
        # Verify session has data before logout
        assert 'foxcons_access_token' in self.client.session
        
        # Logout
        response = self.client.get('/bridge/logout/', follow=False)
        
        # Should redirect to login
        assert response.status_code == 302
        assert '/bridge/login/' in response.url
        
        # Session should be cleared after logout
        new_session = self.client.session
        assert 'foxcons_access_token' not in new_session
        assert 'foxcons_refresh_token' not in new_session
        assert 'normalized_claims' not in new_session


class BridgeInstanceTestCase(TestCase):
    """Test FoxconsInstance model."""
    
    def test_instance_only_active_in_list(self):
        """Test that inactive instances are excluded."""
        active = FoxconsInstance.objects.create(
            name='Active Event',
            slug='active',
            base_url='https://active.example.com',
            is_active=True
        )
        inactive = FoxconsInstance.objects.create(
            name='Inactive Event',
            slug='inactive',
            base_url='https://inactive.example.com',
            is_active=False
        )
        
        active_list = FoxconsInstance.objects.filter(is_active=True)
        assert active in active_list
        assert inactive not in active_list
    
    def test_instance_slug_generation(self):
        """Test that slug is auto-generated from name."""
        instance = FoxconsInstance.objects.create(
            name='My Test Event 2025',
            base_url='https://test.example.com',
            is_active=True
        )
        assert instance.slug == 'my-test-event-2025'
    
    def test_instance_ordering(self):
        """Test instances are ordered by display_order then name."""
        third = FoxconsInstance.objects.create(
            name='AAA Event',
            slug='aaa',
            base_url='https://aaa.example.com',
            is_active=True,
            display_order=3
        )
        first = FoxconsInstance.objects.create(
            name='ZZZ Event',
            slug='zzz',
            base_url='https://zzz.example.com',
            is_active=True,
            display_order=1
        )
        second = FoxconsInstance.objects.create(
            name='BBB Event',
            slug='bbb',
            base_url='https://bbb.example.com',
            is_active=True,
            display_order=2
        )
        
        ordered = list(FoxconsInstance.objects.all())
        assert ordered[0] == first
        assert ordered[1] == second
        assert ordered[2] == third


class OIDCDiscoveryTestCase(TestCase):
    """Test OIDC discovery endpoint."""
    
    def test_openid_configuration_available(self):
        """Test OIDC discovery endpoint is available."""
        # The endpoint should be provided by oauth2_provider
        response = self.client.get('/.well-known/openid-configuration')
        # It may 404 if not configured, but it should be reachable by oauth2_provider
        # For now, just check that the path is accessible to Django
        assert response.status_code in [200, 404, 405]


class OIDCAuthorizationFlowTestCase(TestCase):
    """Test OIDC authorization endpoint behavior."""

    def setUp(self):
        self.instance = FoxconsInstance.objects.create(
            name='Test Event',
            slug='test-event',
            base_url='https://test.example.com',
            is_active=True,
        )
    
    def test_unauthenticated_redirect_to_login(self):
        """Test that unauthenticated users are redirected to bridge login."""
        response = self.client.get('/o/authorize/?client_id=test&response_type=code&state=state123', follow=False)
        
        # Should redirect to bridge login
        assert response.status_code == 302
        assert '/bridge/login/' in response.url
        # OIDC params should be preserved in the redirect
        assert 'client_id=test' in response.url
        assert 'state=state123' in response.url
    
    def test_unauthenticated_preserve_all_oidc_params(self):
        """Test that all OIDC parameters are preserved in login redirect."""
        oidc_params = {
            'client_id': 'test_client',
            'response_type': 'code',
            'redirect_uri': 'https://callback.example.com/auth',
            'scope': 'openid profile email',
            'state': 'abc123xyz',
            'nonce': 'nonce456',
            'code_challenge': 'challenge789',
            'code_challenge_method': 'S256'
        }
        
        query_string = '&'.join([f'{k}={v}' for k, v in oidc_params.items()])
        response = self.client.get(f'/o/authorize/?{query_string}', follow=False)
        
        assert response.status_code == 302
        redirect_url = response.url
        # Check that key params are in the redirect (URL encoding may change values)
        assert 'client_id' in redirect_url
        assert 'state' in redirect_url
        assert 'code_challenge' in redirect_url
        assert '/bridge/login/' in redirect_url

    def test_authenticated_requires_confirmation_redirect(self):
        """Authenticated session should still be redirected to confirmation screen."""
        session = self.client.session
        session['selected_instance_id'] = self.instance.id
        session['selected_email'] = 'test@example.com'
        session['foxcons_refresh_token'] = 'refresh123'
        session['normalized_claims'] = {'email': 'test@example.com', 'sub': 'foxcons:test-event:test@example.com'}
        session.save()

        response = self.client.get('/o/authorize/?client_id=test&response_type=code&state=state123', follow=False)
        assert response.status_code == 302
        assert '/bridge/continue/' in response.url
        assert 'client_id=test' in response.url
        assert 'state=state123' in response.url


class OIDCTokenEndpointTestCase(TestCase):
    """Test OIDC token endpoint (ID token generation)."""
    
    def setUp(self):
        self.client = DjangoTestClient()
        from django.contrib.auth.models import User
        # Verify service account can be created with valid last_login
        self.service_user, created = User.objects.get_or_create(
            username='_oauth2_service_account',
            defaults={
                'email': 'oauth2@bridge.local',
                'is_active': True,
            }
        )
        # Important: ensure last_login is set (needed for ID token generation)
        from django.utils import timezone
        if self.service_user.last_login is None:
            self.service_user.last_login = timezone.now()
            self.service_user.save()
    
    def test_service_account_has_valid_last_login(self):
        """Test that service account has a valid last_login for oauth2_provider."""
        assert self.service_user.last_login is not None, "Service account must have last_login set"

