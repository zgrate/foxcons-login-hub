from .auth import SessionOnlyUser


class BridgeAuthMiddleware:
    """
    Middleware for bridge OIDC authentication.
    
    Sets request.user to a session-only user when sessions contain normalized claims.
    This satisfies @login_required decorators in views without persisting users to the DB.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # If we have normalized claims in session, set up the session-only user
        if 'normalized_claims' in request.session:
            email = request.session.get('selected_email')
            if email:
                request.user = SessionOnlyUser(username=email)
        return self.get_response(request)

