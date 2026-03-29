# Foxcons OIDC Bridge

This Django application serves as an OpenID Connect (OIDC) provider for authentik, bridging authentication against Foxcons HTTP APIs.

## Features

- OIDC Provider using django-oauth-toolkit
- Session-based authentication without persistent user storage
- Admin interface for managing Foxcons event instances
- Support for refresh tokens for UX optimization
- Custom claims exposure for authentik policies

## Setup

1. **Clone or setup the project**

2. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

3. **Run migrations**
   ```
   python manage.py migrate
   ```

4. **Create superuser**
   ```
   python manage.py createsuperuser
   ```

5. **Configure Foxcons instances**
   - Access Django admin at `/admin/`
   - Add `FoxconsInstance` entries for each event

6. **Configure OAuth2 Application**
   - In admin, create an OAuth2 application
   - Client type: Confidential
   - Grant type: Authorization code
   - Redirect URIs: Set to authentik's callback URL
   - Enable OIDC

7. **Run the server**
   ```
   python manage.py runserver
   ```

## Endpoints

- `/o/.well-known/openid-configuration` - OIDC discovery
- `/o/authorize/` - Authorization endpoint
- `/o/token/` - Token endpoint
- `/o/userinfo/` - Userinfo endpoint
- `/bridge/login/` - Bridge login page
- `/bridge/logout/` - Logout

## Security Notes

- Uses server-side sessions for temporary state
- Foxcons tokens stored in session only
- No persistent storage of Foxcons user data
- CSRF protection on login form
- Timeouts on all Foxcons API calls

## Development

- Latest Django with SQLite
- Plain Django templates and views
- Typed dataclasses for API responses
- Isolated Foxcons integration

## Production Docker Compose

1. Prepare environment file:
   ```
   cp .env.example .env
   ```
2. Edit `.env` and set at least:
   - `SECRET_KEY`
   - `ALLOWED_HOSTS`
   - `CSRF_TRUSTED_ORIGINS`
   - `OIDC_RSA_PRIVATE_KEY` (single line with `\n` separators)
3. Build and start:
   ```
   docker compose -f docker-compose.prod.yml up -d --build
   ```

What this stack includes:
- `web`: Django + Gunicorn, runs migrations and `collectstatic` on startup
- `nginx`: Reverse proxy and static/media file serving over HTTP
- Named volumes for persistent SQLite, media, and static files

Useful commands:
```
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f nginx
docker compose -f docker-compose.prod.yml down
```