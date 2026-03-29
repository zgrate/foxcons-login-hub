from django.test import TestCase
from instances.models import FoxconsInstance
from foxcons.services import authenticate_with_password, authenticate_with_refresh, normalize_identity
from foxcons.types import AuthProfile, EventProfile
from foxcons.client import (
    FoxconsClient, InvalidCredentialsError, RefreshTokenError, 
    NetworkError, InvalidResponseError
)
from unittest.mock import patch, MagicMock
import json


class FoxconsClientTestCase(TestCase):
    """Test Foxcons API client."""
    
    def setUp(self):
        self.client = FoxconsClient(timeout=5)
        self.base_url = "https://foxcons.example.com"
    
    @patch('foxcons.client.requests.post')
    def test_login_success(self, mock_post):
        """Test successful login returns tokens."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'token': 'access_token_123',
            'refreshToken': 'refresh_token_456'
        }
        mock_post.return_value = mock_response
        
        result = self.client.login(self.base_url, 'user@example.com', 'password123')
        
        assert result.token == 'access_token_123'
        assert result.refresh_token == 'refresh_token_456'
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert 'user@example.com' in str(call_args)
    
    @patch('foxcons.client.requests.post')
    def test_login_invalid_credentials(self, mock_post):
        """Test login with invalid credentials raises InvalidCredentialsError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        with self.assertRaises(InvalidCredentialsError):
            self.client.login(self.base_url, 'user@example.com', 'wrongpass')
    
    @patch('foxcons.client.requests.post')
    def test_refresh_token_success(self, mock_post):
        """Test successful token refresh."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'token': 'new_access_token',
            'refreshToken': 'new_refresh_token'
        }
        mock_post.return_value = mock_response
        
        result = self.client.refresh(self.base_url, 'old_refresh_token')
        
        assert result.token == 'new_access_token'
        assert result.refresh_token == 'new_refresh_token'
    
    @patch('foxcons.client.requests.post')
    def test_refresh_token_invalid(self, mock_post):
        """Test refresh with invalid token raises RefreshTokenError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        with self.assertRaises(RefreshTokenError):
            self.client.refresh(self.base_url, 'invalid_refresh_token')
    
    @patch('foxcons.client.requests.get')
    def test_get_auth_profile_success(self, mock_get):
        """Test retrieving auth profile."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'sessionId': 10434,
            'id': -378171,
            'accountType': 'admin',
            'flags': ['rodo', 'confirmed', 'email-active'],
            'displayName': 'TestUser',
            'language': 'EN',
            'isUwU': False
        }
        mock_get.return_value = mock_response
        
        result = self.client.get_auth_profile(self.base_url, 'token123')
        
        assert result.id == -378171
        assert result.account_type == 'admin'
        assert 'confirmed' in result.flags
        assert result.display_name == 'TestUser'
    
    @patch('foxcons.client.requests.get')
    def test_get_event_profile_success(self, mock_get):
        """Test retrieving event profile."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': -378171,
            'power': 'orga-team',
            'displayName': 'EVENT_NICK',
            'bourgeoisStatus': 'ACCREDITATION:SPONSOR',
            'eventName': 'TestEvent-2025',
            'firstName': 'John',
            'lastName': 'Doe',
            'room': 170,
            'flags': [],
            'frameType': {'virtual': ['dj', 'media']},
            'contact': {},
            'additionalPermissions': ['can_manage_booth'],
            'isHidden': False,
            'updatedAt': '2026-01-03T21:54:47.060Z'
        }
        mock_get.return_value = mock_response
        
        result = self.client.get_event_profile(self.base_url, 'token123')
        
        assert result.id == -378171
        assert result.power == 'orga-team'
        assert result.event_name == 'TestEvent-2025'
        assert result.first_name == 'John'
        assert result.additional_permissions == ['can_manage_booth']


class NormalizeIdentityTestCase(TestCase):
    """Test identity normalization."""
    
    def setUp(self):
        self.instance = FoxconsInstance.objects.create(
            name='Test Event',
            slug='test-event',
            base_url='https://test.example.com',
            is_active=True
        )
    
    def test_normalize_with_confirmed_flag(self):
        """Test email_verified is true when 'confirmed' flag present."""
        auth_profile = AuthProfile(
            session_id=100,
            id=1,
            account_type='user',
            flags=['confirmed', 'email-active'],
            display_name='TestUser',
            language='EN',
            is_uw_u=False
        )
        event_profile = EventProfile(
            id=1,
            power='attendee',
            display_name='Event Name',
            avatar_file=None,
            bourgeois_status='NONE',
            room=None,
            flags=[],
            frame_type={},
            contact={},
            updated_at='2026-01-01T00:00:00Z',
            is_hidden=False,
            first_name='Test',
            last_name='User',
            event_name='TestEvent',
            additional_permissions=[]
        )
        
        result = normalize_identity(self.instance, 'test@example.com', auth_profile, event_profile)
        
        assert result.email_verified is True
    
    def test_normalize_without_confirmed_flag(self):
        """Test email_verified is false when 'confirmed' flag not present."""
        auth_profile = AuthProfile(
            session_id=100,
            id=1,
            account_type='user',
            flags=['email-active'],  # No 'confirmed'
            display_name='TestUser',
            language='EN',
            is_uw_u=False
        )
        event_profile = EventProfile(
            id=1,
            power='attendee',
            display_name='Event Name',
            avatar_file=None,
            bourgeois_status='NONE',
            room=None,
            flags=[],
            frame_type={},
            contact={},
            updated_at='2026-01-01T00:00:00Z',
            is_hidden=False,
            first_name='Test',
            last_name='User',
            event_name='TestEvent',
            additional_permissions=[]
        )
        
        result = normalize_identity(self.instance, 'test@example.com', auth_profile, event_profile)
        
        assert result.email_verified is False
    
    def test_normalize_deduplicates_flags(self):
        """Test that duplicate flags are deduplicated."""
        auth_profile = AuthProfile(
            session_id=100,
            id=1,
            account_type='user',
            flags=['confirmed', 'email-active', 'confirmed', 'rodo'],  # 'confirmed' appears twice
            display_name='TestUser',
            language='EN',
            is_uw_u=False
        )
        event_profile = EventProfile(
            id=1,
            power='attendee',
            display_name='Event Name',
            avatar_file=None,
            bourgeois_status='NONE',
            room=None,
            flags=[],
            frame_type={},
            contact={},
            updated_at='2026-01-01T00:00:00Z',
            is_hidden=False,
            first_name='Test',
            last_name='User',
            event_name='TestEvent',
            additional_permissions=[]
        )
        
        result = normalize_identity(self.instance, 'test@example.com', auth_profile, event_profile)
        
        # Should have 3 unique flags
        assert len(result.foxcons_flags) == 3
        assert result.foxcons_flags.count('confirmed') == 1
        assert result.flags == result.foxcons_flags

    def test_normalize_groups_include_role_data(self):
        """Test groups include event-aware instance/event/account/power/perm values."""
        auth_profile = AuthProfile(
            session_id=100,
            id=1,
            account_type='admin',
            flags=['confirmed'],
            display_name='TestUser',
            language='EN',
            is_uw_u=False
        )
        event_profile = EventProfile(
            id=1,
            power='orga-team',
            display_name='Event Name',
            avatar_file=None,
            bourgeois_status='NONE',
            room=None,
            flags=[],
            frame_type={},
            contact={},
            updated_at='2026-01-01T00:00:00Z',
            is_hidden=False,
            first_name='Test',
            last_name='User',
            event_name='TestEvent',
            additional_permissions=['can_manage_booth', 'can_edit_schedule']
        )

        result = normalize_identity(self.instance, 'test@example.com', auth_profile, event_profile)

        assert 'instance:test-event:TestEvent:test-event' in result.groups
        assert 'event:test-event:TestEvent:member' in result.groups
        assert 'account:test-event:TestEvent:admin' in result.groups
        assert 'power:test-event:TestEvent:orga-team' in result.groups
        assert 'perm:test-event:TestEvent:can_manage_booth' in result.groups
        assert 'perm:test-event:TestEvent:can_edit_schedule' in result.groups
    
    def test_subject_stability(self):
        """Test that subject is stable for same instance and email."""
        auth_profile = AuthProfile(
            session_id=100,
            id=1,
            account_type='user',
            flags=['confirmed'],
            display_name='TestUser',
            language='EN',
            is_uw_u=False
        )
        event_profile = EventProfile(
            id=1,
            power='attendee',
            display_name='Event Name',
            avatar_file=None,
            bourgeois_status='NONE',
            room=None,
            flags=[],
            frame_type={},
            contact={},
            updated_at='2026-01-01T00:00:00Z',
            is_hidden=False,
            first_name='Test',
            last_name='User',
            event_name='TestEvent',
            additional_permissions=[]
        )
        
        result1 = normalize_identity(self.instance, 'test@example.com', auth_profile, event_profile)
        result2 = normalize_identity(self.instance, 'test@example.com', auth_profile, event_profile)
        
        assert result1.sub == result2.sub
        assert result1.sub == 'foxcons:test-event:test@example.com'
    
    def test_normalize_locale(self):
        """Test locale is set from auth profile language."""
        auth_profile = AuthProfile(
            session_id=100,
            id=1,
            account_type='user',
            flags=[],
            display_name='TestUser',
            language='PL',
            is_uw_u=False
        )
        event_profile = EventProfile(
            id=1,
            power='attendee',
            display_name='Event Name',
            avatar_file=None,
            bourgeois_status='NONE',
            room=None,
            flags=[],
            frame_type={},
            contact={},
            updated_at='2026-01-01T00:00:00Z',
            is_hidden=False,
            first_name='Test',
            last_name='User',
            event_name='TestEvent',
            additional_permissions=[]
        )
        
        result = normalize_identity(self.instance, 'test@example.com', auth_profile, event_profile)
        
        assert result.locale == 'PL'


class AuthenticationFlowTestCase(TestCase):
    """Test authentication flows."""
    
    def setUp(self):
        self.instance = FoxconsInstance.objects.create(
            name='Test Event',
            slug='test-event',
            base_url='https://test.example.com',
            is_active=True
        )
    
    @patch('foxcons.client.FoxconsClient.login')
    @patch('foxcons.client.FoxconsClient.get_auth_profile')
    @patch('foxcons.client.FoxconsClient.get_event_profile')
    def test_authenticate_with_password_success(self, mock_event, mock_auth, mock_login):
        """Test successful password authentication."""
        mock_login.return_value = MagicMock(token='token123', refresh_token='refresh123')
        mock_auth.return_value = AuthProfile(
            session_id=100, id=1, account_type='user', flags=['confirmed'],
            display_name='TestUser', language='EN', is_uw_u=False
        )
        mock_event.return_value = EventProfile(
            id=1, power='attendee', display_name='Event', avatar_file=None,
            bourgeois_status='NONE', room=None, flags=[], frame_type={},
            contact={}, updated_at='2026-01-01T00:00:00Z', is_hidden=False,
            first_name='Test', last_name='User', event_name='TestEvent',
            additional_permissions=[]
        )
        
        identity, token, refresh = authenticate_with_password(self.instance, 'test@example.com', 'password')
        
        assert token == 'token123'
        assert refresh == 'refresh123'
        assert identity.email == 'test@example.com'
    
    @patch('foxcons.client.FoxconsClient.login')
    def test_authenticate_with_password_invalid_credentials(self, mock_login):
        """Test password auth with invalid credentials."""
        mock_login.side_effect = InvalidCredentialsError("Invalid credentials")
        
        with self.assertRaises(InvalidCredentialsError):
            authenticate_with_password(self.instance, 'test@example.com', 'wrongpass')
    
    @patch('foxcons.client.FoxconsClient.refresh')
    @patch('foxcons.client.FoxconsClient.get_auth_profile')
    @patch('foxcons.client.FoxconsClient.get_event_profile')
    def test_authenticate_with_refresh_success(self, mock_event, mock_auth, mock_refresh):
        """Test successful refresh token authentication."""
        mock_refresh.return_value = MagicMock(token='new_token', refresh_token='new_refresh')
        mock_auth.return_value = AuthProfile(
            session_id=100, id=1, account_type='user', flags=['confirmed'],
            display_name='TestUser', language='EN', is_uw_u=False
        )
        mock_event.return_value = EventProfile(
            id=1, power='attendee', display_name='Event', avatar_file=None,
            bourgeois_status='NONE', room=None, flags=[], frame_type={},
            contact={}, updated_at='2026-01-01T00:00:00Z', is_hidden=False,
            first_name='Test', last_name='User', event_name='TestEvent',
            additional_permissions=[]
        )
        
        identity, token, refresh = authenticate_with_refresh(self.instance, 'test@example.com', 'old_refresh')
        
        assert token == 'new_token'
        assert refresh == 'new_refresh'
    
    @patch('foxcons.client.FoxconsClient.refresh')
    def test_authenticate_with_refresh_invalid_token(self, mock_refresh):
        """Test refresh with invalid token."""
        mock_refresh.side_effect = RefreshTokenError("Invalid refresh token")
        
        with self.assertRaises(RefreshTokenError):
            authenticate_with_refresh(self.instance, 'test@example.com', 'invalid_refresh')
    
    @patch('foxcons.client.FoxconsClient.login')
    @patch('foxcons.client.FoxconsClient.get_auth_profile')
    @patch('foxcons.client.FoxconsClient.get_event_profile')
    def test_authenticate_id_mismatch_rejected(self, mock_event, mock_auth, mock_login):
        """Test that ID mismatch between auth and event profiles is rejected."""
        mock_login.return_value = MagicMock(token='token123', refresh_token='refresh123')
        mock_auth.return_value = AuthProfile(
            session_id=100, id=1, account_type='user', flags=['confirmed'],
            display_name='TestUser', language='EN', is_uw_u=False
        )
        mock_event.return_value = EventProfile(
            id=999,  # Different ID
            power='attendee', display_name='Event', avatar_file=None,
            bourgeois_status='NONE', room=None, flags=[], frame_type={},
            contact={}, updated_at='2026-01-01T00:00:00Z', is_hidden=False,
            first_name='Test', last_name='User', event_name='TestEvent',
            additional_permissions=[]
        )
        
        with self.assertRaises(ValueError):
            authenticate_with_password(self.instance, 'test@example.com', 'password')

