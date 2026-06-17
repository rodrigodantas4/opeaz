import hashlib
import time
from urllib.parse import urlencode

from django.conf import settings
from rest_framework import serializers

from core.models import CommercialCondition, Document, Flyer

from .models import NodeType, ShareScope, TreeNode
from .validators import ENTITY_TYPE_MAP


class SharedBySerializer(serializers.Serializer):
    entity_type = serializers.CharField()
    id = serializers.IntegerField()
    name = serializers.CharField()


class TreeNodeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    parent_id = serializers.IntegerField(allow_null=True)
    node_type = serializers.CharField()
    is_owned = serializers.BooleanField()
    is_shared = serializers.BooleanField()
    shared_by = SharedBySerializer(allow_null=True)


def serialize_tree_node(node, *, is_owned, is_shared, shared_by, parent_id=None):
    return {
        'id': node.pk,
        'name': node.name,
        'parent_id': parent_id if parent_id is not None else node.parent_id,
        'node_type': node.node_type,
        'is_owned': is_owned,
        'is_shared': is_shared,
        'shared_by': shared_by,
    }


class AggregatedTreeSerializer(serializers.Serializer):
    def to_representation(self, items):
        return [
            serialize_tree_node(
                item['node'],
                is_owned=item['is_owned'],
                is_shared=item['is_shared'],
                shared_by=item['shared_by'],
                parent_id=item['api_parent_id'],
            )
            for item in items
        ]


class ShareTargetSerializer(serializers.Serializer):
    entity_type = serializers.ChoiceField(choices=list(ENTITY_TYPE_MAP.keys()))
    entity_id = serializers.IntegerField()


class CreateShareSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=ShareScope.values, default=ShareScope.EXPLICIT)
    target = ShareTargetSerializer(required=False)
    groupement_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        scope = attrs.get('scope', ShareScope.EXPLICIT)
        if scope == ShareScope.EXPLICIT and 'target' not in attrs:
            raise serializers.ValidationError({'target': 'Required for explicit scope'})
        if scope == ShareScope.GROUPEMENT_ALL and 'groupement_id' not in attrs:
            raise serializers.ValidationError({'groupement_id': 'Required for groupement_all scope'})
        return attrs


class MoveNodeSerializer(serializers.Serializer):
    parent_id = serializers.IntegerField(allow_null=True)


def build_signed_url(file_field):
    if not file_field:
        return None
    ttl = getattr(settings, 'DOCUMENT_TREE_SIGNED_URL_TTL', 3600)
    expires = int(time.time()) + ttl
    path = file_field.name
    signature = hashlib.sha256(f'{path}:{expires}:{settings.SECRET_KEY}'.encode()).hexdigest()[:16]
    query = urlencode({'expires': expires, 'sig': signature})
    base = file_field.url if hasattr(file_field, 'url') else f'/media/{path}'
    return f'{base}?{query}'


CONTENT_SERIALIZERS = {
    'document': lambda obj: {
        'content_type': 'document',
        'id': obj.pk,
        'name': obj.name,
        'file_url': build_signed_url(obj.file),
        'created_at': obj.created_at,
        'laboratory_id': obj.laboratory_id,
    },
    'flyer': lambda obj: {
        'content_type': 'flyer',
        'id': obj.pk,
        'title': obj.title,
        'image_url': build_signed_url(obj.image),
        'start_at': obj.start_at,
        'end_at': obj.end_at,
        'laboratory_id': obj.laboratory_id,
    },
    'commercialcondition': lambda obj: {
        'content_type': 'commercialcondition',
        'id': obj.pk,
        'name': obj.name,
        'text': obj.text,
        'year': obj.year,
        'laboratory_id': obj.laboratory_id,
    },
}


def serialize_leaf_content(node: TreeNode):
    if node.node_type != NodeType.LEAF:
        raise serializers.ValidationError('Node is not a leaf')
    model = node.content_content_type.model
    serializer_fn = CONTENT_SERIALIZERS.get(model)
    if not serializer_fn:
        raise serializers.ValidationError(f'Unsupported content type: {model}')
    obj = node.content_content_type.get_object_for_this_type(pk=node.content_object_id)
    return serializer_fn(obj)
