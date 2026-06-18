from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from .context import SESSION_ENTITY_ID_KEY, SESSION_ENTITY_TYPE_KEY, resolve_session_entity


class EntitySessionAuthentication(BaseAuthentication):
    """PoC: bind the active entity from Django session. Production: swap for JWT claims."""

    def authenticate(self, request):
        entity_type = request.session.get(SESSION_ENTITY_TYPE_KEY)
        entity_id = request.session.get(SESSION_ENTITY_ID_KEY)
        if not entity_type or entity_id is None:
            raise AuthenticationFailed('No active entity in session')

        try:
            entity = resolve_session_entity(request)
        except ValidationError as exc:
            raise AuthenticationFailed(str(exc.detail)) from exc

        request.entity = entity
        request.entity_type = entity_type
        request.entity_id = int(entity_id)
        return None

    def authenticate_header(self, request):
        return 'Entity'


class OptionalEntitySessionAuthentication(BaseAuthentication):
    """
    PoC: bind session entity when present; return None when absent so mutations
    can fall back to body identity fields for manual testing.
    """

    def authenticate(self, request):
        entity_type = request.session.get(SESSION_ENTITY_TYPE_KEY)
        entity_id = request.session.get(SESSION_ENTITY_ID_KEY)
        if not entity_type or entity_id is None:
            return None

        try:
            entity = resolve_session_entity(request)
        except ValidationError as exc:
            raise AuthenticationFailed(str(exc.detail)) from exc

        request.entity = entity
        request.entity_type = entity_type
        request.entity_id = int(entity_id)
        return None

    def authenticate_header(self, request):
        return 'Entity'
