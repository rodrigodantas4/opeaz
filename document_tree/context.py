from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied, ValidationError

ENTITY_ACCESS_DENIED_MESSAGE = 'Entity does not have permission'

from .models import TreeNode
from .services import TreeService
from .validators import get_entity

SESSION_ENTITY_TYPE_KEY = 'entity_type'
SESSION_ENTITY_ID_KEY = 'entity_id'


def get_session_entity_keys(request) -> tuple[str, int]:
    entity_type = request.session.get(SESSION_ENTITY_TYPE_KEY)
    entity_id = request.session.get(SESSION_ENTITY_ID_KEY)
    if not entity_type or entity_id is None:
        raise NotAuthenticated('No active entity in session')
    return entity_type, int(entity_id)


def resolve_session_entity(request):
    entity_type, entity_id = get_session_entity_keys(request)
    try:
        return get_entity(entity_type, entity_id)
    except DjangoValidationError as exc:
        if hasattr(exc, 'message_dict'):
            raise ValidationError(exc.message_dict) from exc
        raise ValidationError(str(exc)) from exc


def set_session_entity(request, entity_type: str, entity_id: int):
    try:
        get_entity(entity_type, entity_id)
    except DjangoValidationError as exc:
        if hasattr(exc, 'message_dict'):
            raise ValidationError(exc.message_dict) from exc
        raise ValidationError(str(exc)) from exc
    request.session[SESSION_ENTITY_TYPE_KEY] = entity_type
    request.session[SESSION_ENTITY_ID_KEY] = entity_id


def clear_session_entity(request):
    request.session.pop(SESSION_ENTITY_TYPE_KEY, None)
    request.session.pop(SESSION_ENTITY_ID_KEY, None)


def get_accessible_node_or_404(node_id, entity) -> TreeNode:
    try:
        node = TreeNode.objects.get(pk=node_id)
    except TreeNode.DoesNotExist as exc:
        raise NotFound('Node not found') from exc
    if not TreeService.can_entity_access_node(node, entity):
        raise PermissionDenied(ENTITY_ACCESS_DENIED_MESSAGE)
    return node
