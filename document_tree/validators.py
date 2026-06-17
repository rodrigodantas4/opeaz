from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from core.models import CommercialCondition, Document, Flyer, Groupement, Laboratory, Pharmacy

from .models import ALLOWED_OWNER_MODELS, NodeType, ShareScope, TreeNode

ALLOWED_CONTENT_MODELS = (Document, Flyer, CommercialCondition)

ENTITY_TYPE_MAP = {
    'laboratory': Laboratory,
    'groupement': Groupement,
    'pharmacy': Pharmacy,
}


def get_entity(entity_type: str, entity_id: int):
    model = ENTITY_TYPE_MAP.get(entity_type)
    if model is None:
        raise ValidationError({'entity_type': f'Unknown entity type: {entity_type}'})
    try:
        return model.objects.get(pk=entity_id)
    except model.DoesNotExist as exc:
        raise ValidationError({'entity_id': 'Entity not found'}) from exc


def get_content_type_for_model(model):
    return ContentType.objects.get_for_model(model)


def validate_owner_type(content_type):
    allowed = {get_content_type_for_model(m).id for m in ALLOWED_OWNER_MODELS}
    if content_type.id not in allowed:
        raise ValidationError('Invalid owner content type')


def validate_content_type(content_type):
    allowed = {get_content_type_for_model(m).id for m in ALLOWED_CONTENT_MODELS}
    if content_type.id not in allowed:
        raise ValidationError('Invalid leaf content type')


def validate_tree_node(node: TreeNode):
    validate_owner_type(node.owner_content_type)
    if node.node_type == NodeType.FOLDER:
        if node.content_content_type_id or node.content_object_id:
            raise ValidationError('Folder nodes must not have content')
    elif node.node_type == NodeType.LEAF:
        if not node.content_content_type_id or not node.content_object_id:
            raise ValidationError('Leaf nodes must have content')
        validate_content_type(node.content_content_type)
    else:
        raise ValidationError('Invalid node_type')


def validate_share(sharer, node: TreeNode, scope: str, target=None, groupement=None):
    sharer_ct = get_content_type_for_model(sharer.__class__)
    if node.owner_content_type_id != sharer_ct.id or node.owner_object_id != sharer.pk:
        raise ValidationError('Only the node owner can create shares')

    if scope == ShareScope.EXPLICIT:
        if target is None:
            raise ValidationError('Explicit share requires a target')
        if isinstance(sharer, Groupement) and isinstance(target, Pharmacy):
            if target.groupement_id != sharer.pk:
                raise ValidationError('Pharmacy does not belong to this groupement')
    elif scope == ShareScope.GROUPEMENT_ALL:
        if not isinstance(sharer, Groupement):
            raise ValidationError('Only a groupement can use groupement_all scope')
        if groupement is None or groupement.pk != sharer.pk:
            raise ValidationError('groupement must match the sharing groupement')
    else:
        raise ValidationError('Invalid share scope')
