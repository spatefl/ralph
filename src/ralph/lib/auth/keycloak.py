import json
import logging
import time
from typing import Optional

import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from rest_framework import authentication, exceptions
from jwt import PyJWKClient

logger = logging.getLogger(__name__)


class KeycloakJWTAuthentication(authentication.BaseAuthentication):
    """
    DRF authentication backend that validates Keycloak-issued JWTs.
    - Verifies issuer and audience.
    - Fetches and caches JWKS keys.
    - Creates/updates Django users from token claims.
    - Optionally syncs roles to Django groups and/or enforces a required role.
    """

    _jwks_cache = {"client": None, "expires_at": 0.0}

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode()
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return None

        token = auth_header.split()[1]
        decoded = self._decode(token)
        user = self._get_or_create_user(decoded)
        self._sync_groups(decoded, user)
        self._enforce_required_role(decoded)
        return (user, None)

    def _decode(self, token: str) -> dict:
        issuer = getattr(settings, "KEYCLOAK_ISSUER", None)
        audience = getattr(settings, "KEYCLOAK_AUDIENCE", None)
        jwks_url = getattr(settings, "KEYCLOAK_JWKS_URL", None)

        if not issuer or not jwks_url:
            raise ImproperlyConfigured("Keycloak issuer and JWKS URL must be configured.")

        jwk_client = self._get_jwk_client(jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        try:
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                audience=audience,
                issuer=issuer,
                options={"require": ["exp", "iat", "iss"]},
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired")
        except jwt.InvalidAudienceError:
            raise exceptions.AuthenticationFailed("Invalid audience")
        except jwt.InvalidIssuerError:
            raise exceptions.AuthenticationFailed("Invalid issuer")
        except jwt.PyJWTError as exc:
            logger.warning("Keycloak token validation failed: %s", exc)
            raise exceptions.AuthenticationFailed("Invalid token")

    def _get_jwk_client(self, jwks_url: str) -> PyJWKClient:
        now = time.time()
        cached = self._jwks_cache
        if cached["client"] and cached["expires_at"] > now:
            return cached["client"]
        # Short-lived cache; JWKS rarely changes
        client = PyJWKClient(jwks_url)
        self._jwks_cache = {"client": client, "expires_at": now + 300}
        return client

    def _get_or_create_user(self, claims: dict):
        username = claims.get("preferred_username") or claims.get("email")
        email = claims.get("email") or ""
        if not username:
            raise exceptions.AuthenticationFailed("preferred_username or email claim required")
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_active": True},
        )
        updated = False
        if email and user.email != email:
            user.email = email
            updated = True
        if updated:
            user.save(update_fields=["email", "modified"])
        return user

    def _sync_groups(self, claims: dict, user):
        if not getattr(settings, "KEYCLOAK_SYNC_GROUPS", True):
            return
        roles = claims.get("realm_access", {}).get("roles", [])
        if not roles:
            return
        groups = []
        for role in roles:
            group, _ = Group.objects.get_or_create(name=role)
            groups.append(group)
        if groups:
            user.groups.set(groups)

    def _enforce_required_role(self, claims: dict):
        required = getattr(settings, "KEYCLOAK_REQUIRED_ROLE", None)
        if not required:
            return
        roles = claims.get("realm_access", {}).get("roles", [])
        if required not in roles:
            raise exceptions.AuthenticationFailed("Required role missing")
