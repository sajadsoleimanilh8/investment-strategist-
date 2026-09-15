"""Third-party sign-in.

`registry.available()` is the only thing outside this package that needs to
know which providers exist; everything else takes an `OAuthProvider`.
"""
from app.oauth.base import Identity, IdentityError, OAuthProvider  # noqa: F401
from app.oauth.registry import available, get  # noqa: F401
