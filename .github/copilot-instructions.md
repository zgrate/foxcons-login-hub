Build a standalone Django application named foxcons_oidc_bridge.

Purpose
- This application is an OpenID Connect Provider for authentik.
- It authenticates users against Foxcons HTTP APIs.
- Foxcons is the sole source of truth for user identity and event-scoped permissions.
- Neither Foxcons nor authentik should be modified.
- There is exactly one authentik client configured per bridge deployment.

High-level architecture
- Standalone Django app
- Server-rendered login UI
- OIDC provider using django-oauth-toolkit with OpenID Connect enabled
- SQLite database
- Django admin used to manage Foxcons event instances
- No persistent local user storage for Foxcons identities
- Optional session reuse through Foxcons refresh token stored in Django session

Core constraints
- Do not modify Foxcons.
- Do not modify authentik.
- Do not create bridge-side user records or authorization snapshots in the database.
- Do not enforce access restrictions in the bridge based on Foxcons claims.
- Only transfer current identity and permission data from Foxcons to authentik.
- Foxcons email is stable per instance and can be treated as the primary identity inside that instance.
- email_verified should be true only when Foxcons flags contain "confirmed".
- One authentik OIDC client per bridge deployment.

Technology choices
- Latest Django version
- SQLite
- django-oauth-toolkit with OIDC enabled
- Django admin
- Standard Django session framework
- Plain Django templates and views for UX
- Requests or httpx for Foxcons API calls

Foxcons API contract
1. POST {base_url}/app/auth/login
   body:
   {
     "username": "<email>",
     "password": "<password>"
   }
   response:
   {
     "token": "...",
     "refreshToken": "..."
   }

2. POST {base_url}/app/auth/refresh-token
   body:
   {
     "refreshToken": "..."
   }
   response:
   {
     "token": "...",
     "refreshToken": "..."
   }

3. GET {base_url}/app/auth/profile
   Authorization: Bearer <token>
   example response:
   {
     "sessionId": 10434,
     "id": -378171,
     "accountType": "admin",
     "flags": ["rodo", "tos", "email-active", "confirmed", "confirmed", "b-day"],
     "displayName": "Seti",
     "language": "EN",
     "isUwU": false
   }

4. GET {base_url}/app/event/profile
   Authorization: Bearer <token>
   example response:
   {
     "id": -378171,
     "power": "orga-team",
     "displayName": "TWÓJ NICK",
     "avatarFile": {
       "id": "16830246-ad16-4343-ae65-ee403efe5373",
       "type": "event"
     },
     "bourgeoisStatus": "ACCREDITATION:SPONSOR",
     "room": 170,
     "flags": [],
     "frameType": {
       "funny": [],
       "virtual": [
         "dj",
         "media",
         "medic",
         "dealer",
         "guests",
         "helper",
         "others",
         "chillzone",
         "prelegent",
         "storyteam",
         "stage-crew",
         "attractions",
         "decorations"
       ]
     },
     "contact": {},
     "updatedAt": "2026-01-03T21:54:47.060Z",
     "isHidden": null,
     "firstName": "L",
     "lastName": "L",
     "eventName": "Futrolajki-2025",
     "additionalPermissions": []
   }

Project structure
Create Django apps:
- instances
- foxcons
- bridge_oidc

Data model
Create only one custom model:

FoxconsInstance
- name: CharField
- slug: SlugField unique
- base_url: URLField unique
- is_active: BooleanField default True
- display_order: PositiveIntegerField default 0
- description: TextField blank=True

Model rules
- This model represents one Foxcons event instance identified by base_url.
- It must be fully editable in Django admin.
- Only active instances may be used in login flow.

Do not create any persistent user, membership, or snapshot models.

Session-only data
Use Django server-side session to store only temporary login state:
- selected_instance_id
- selected_instance_slug
- selected_instance_base_url
- selected_email
- foxcons_access_token
- foxcons_refresh_token
- normalized_claims
- last_auth_at

Do not store Foxcons passwords anywhere.
Do not persist user data beyond session storage.

Identity model
Treat email as stable within a Foxcons instance.
Build OIDC subject as:
- foxcons:<normalized_base_url>:<email>

Normalization rules
- email = submitted username
- preferred_username = submitted username
- name = auth/profile.displayName, fallback to event/profile.displayName
- locale = auth/profile.language if present
- foxcons_user_id = auth/profile.id
- foxcons_session_id = auth/profile.sessionId
- foxcons_account_type = auth/profile.accountType
- foxcons_power = event/profile.power
- foxcons_event_name = event/profile.eventName
- foxcons_instance = selected instance slug or normalized base_url
- foxcons_bourgeois_status = event/profile.bourgeoisStatus
- foxcons_additional_permissions = event/profile.additionalPermissions
- foxcons_first_name = event/profile.firstName
- foxcons_last_name = event/profile.lastName
- foxcons_flags = deduplicated auth/profile.flags
- email_verified = true only if deduplicated foxcons_flags contains "confirmed"

Validation rules
The bridge should validate only data integrity, not access policy:
- selected FoxconsInstance exists
- selected FoxconsInstance is active
- username/email is non-empty
- login or refresh call succeeded
- auth/profile.id equals event/profile.id
- required JSON fields are present enough to build claims

Do not deny login based on:
- accountType
- power
- flags
- additionalPermissions
- bourgeoisStatus

Those claims are passed through for authentik policies to handle.

OIDC claims to expose
Standard claims:
- sub
- email
- email_verified
- name
- preferred_username
- locale

Custom claims:
- foxcons_instance
- foxcons_event_name
- foxcons_user_id
- foxcons_session_id
- foxcons_account_type
- foxcons_power
- foxcons_flags
- foxcons_additional_permissions
- foxcons_bourgeois_status
- foxcons_first_name
- foxcons_last_name

Login flow
1. authentik redirects user to the bridge OIDC authorize endpoint.
2. If a valid bridge session exists and a refresh token is present, attempt silent refresh:
   - POST /app/auth/refresh-token
   - GET /app/auth/profile
   - GET /app/event/profile
   - validate matching IDs
   - rebuild claims
   - continue OIDC flow
3. If refresh fails, clear Foxcons tokens from session and show login form.
4. Login form contains:
   - event selector
   - email field
   - password field
5. On submit:
   - validate selected active FoxconsInstance
   - POST /app/auth/login
   - GET /app/auth/profile
   - GET /app/event/profile
   - validate matching IDs
   - normalize claims
   - store access token, refresh token, selected instance, selected email, and normalized claims in Django session
   - continue OIDC authorization code flow back to authentik

Refresh-token behavior
- Refresh token usage is a UX optimization only.
- If refresh works, reuse session without asking for credentials again.
- If refresh fails for any reason, silently clear tokens and require manual login.
- Never expose technical refresh failure details to the user.

Logout behavior
- Keep first version simple.
- Local bridge logout clears Django session, including Foxcons tokens and selected event.
- No need to implement back-channel logout or global logout in first version.
- If user returns later with no valid session, require normal login again.

UI requirements
Create a simple server-rendered login page for the bridge only.
Requirements:
- event dropdown populated from active FoxconsInstance rows ordered by display_order then name
- email field
- password field
- preselect last used event from session if available
- show clear, user-friendly error for invalid credentials
- show generic error for unavailable Foxcons instance or upstream API failure
- do not expose stack traces or internal details
- no registration, no password reset, no local account management
- no bridge-side consent screen unless OIDC library requires it; if possible auto-approve for the single configured authentik client

Admin requirements
- Register FoxconsInstance in Django admin
- Allow full CRUD in admin
- Make model easy to manage with list display, filtering by is_active, and search by name/slug/base_url

Foxcons client implementation
Create:
- foxcons/client.py
- foxcons/types.py
- foxcons/services.py

foxcons/client.py
Implement low-level HTTP methods:
- login(base_url, username, password)
- refresh(base_url, refresh_token)
- get_auth_profile(base_url, access_token)
- get_event_profile(base_url, access_token)

Requirements:
- use timeouts on all requests
- handle JSON decode errors
- handle non-2xx responses cleanly
- never log passwords
- never log raw tokens
- raise explicit typed exceptions for invalid credentials, network errors, invalid upstream responses, and refresh failure

foxcons/types.py
Define typed dataclasses or typed containers for:
- LoginResponse
- AuthProfile
- EventProfile
- NormalizedIdentity

foxcons/services.py
Implement:
- authenticate_with_password(instance, email, password) -> NormalizedIdentity + tokens
- authenticate_with_refresh(instance, email, refresh_token) -> NormalizedIdentity + tokens
- normalize_identity(instance, email, auth_profile, event_profile)

Normalization details
- Deduplicate flags while preserving order if possible.
- Prefer auth/profile.displayName over event/profile.displayName.
- Subject must remain stable for the same instance + email.
- Do not assume any Foxcons field beyond what is described above.

OIDC provider requirements
Use django-oauth-toolkit with OIDC enabled.
Expose:
- /.well-known/openid-configuration
- authorization endpoint
- token endpoint
- userinfo endpoint
- JWKS endpoint

OIDC app behavior
- Exactly one OAuth/OIDC application configured for authentik
- Authorization Code Flow
- Support PKCE
- Issue ID token and userinfo claims from session-backed normalized identity
- Limit implementation to the single configured authentik client
- Avoid multi-client abstractions unless required by the library

Bridge OIDC implementation notes
- The bridge authenticates the browser session first, then completes OIDC authorize flow
- Claims should always be derived from current session data generated from Foxcons
- If no valid normalized identity is present in session during authorize, redirect user to bridge login page and resume the OIDC flow after successful authentication

Security requirements
- CSRF-protect login form
- Use secure cookies in production
- Use HttpOnly session cookies
- Keep Foxcons tokens only in server-side session
- Never store Foxcons passwords
- Never log raw tokens
- Only allow Foxcons requests to URLs from FoxconsInstance rows
- Clear session tokens on refresh failure
- Use safe request timeouts and exception handling
- Keep secrets in Django settings via environment variables
- Ensure DEBUG-dependent behavior is safe

Settings/configuration
Use environment variables for:
- SECRET_KEY
- DEBUG
- ALLOWED_HOSTS
- CSRF_TRUSTED_ORIGINS
- OIDC signing key settings
- database path if needed
- session cookie security flags

Templates/views
Create clean Django views for:
- bridge login page
- bridge logout
- helper redirect that resumes pending OIDC authorization after successful Foxcons auth

Tests
Add tests for:
- successful manual login
- successful refresh-token login
- invalid password
- invalid refresh token
- inactive FoxconsInstance rejected
- unknown instance rejected
- mismatched auth/profile.id and event/profile.id rejected
- duplicate flags deduplicated
- email_verified true only when "confirmed" is present
- stable subject generation for same instance + email
- OIDC discovery endpoint available
- authorization code flow works with PKCE
- userinfo endpoint returns expected claims
- session is cleared correctly on logout
- refresh failure clears stored Foxcons tokens

Code quality expectations
- Keep Foxcons integration isolated from OIDC logic
- Keep claim construction in a dedicated module, e.g. bridge_oidc/claims.py
- Write explicit docstrings around trust boundaries
- Prefer typed service objects and small functions
- Avoid unnecessary abstractions
- Keep first version simple and production-minded

Out of scope for first version
- persistent local users
- persistent audit log models
- policy enforcement in bridge
- multi-client authentik support
- user self-service management
- registration
- password reset
- back-channel logout
- long-term token storage outside session
- REST API for bridge management beyond Django admin