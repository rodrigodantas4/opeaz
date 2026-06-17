from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Groupement

from .models import NodeType, ShareScope, TreeNode
from .serializers import (
    AggregatedTreeSerializer,
    CreateShareSerializer,
    MoveNodeSerializer,
    serialize_leaf_content,
    serialize_tree_node,
)
from .services import ShareService, TreeService
from .validators import get_entity


class EntityTreeView(APIView):
    def get(self, request, entity_type, entity_id):
        try:
            entity, items = TreeService.build_aggregated_view(entity_type, entity_id)
        except Exception as exc:
            if hasattr(exc, 'message_dict'):
                raise ValidationError(exc.message_dict) from exc
            raise ValidationError(str(exc)) from exc
        serializer = AggregatedTreeSerializer()
        return Response(serializer.to_representation(items))


class TreeNodeChildrenView(APIView):
    def get(self, request, node_id):
        entity_type = request.query_params.get('entity_type')
        entity_id = request.query_params.get('entity_id')
        if not entity_type or not entity_id:
            raise ValidationError({'detail': 'entity_type and entity_id query params are required'})

        try:
            entity = get_entity(entity_type, int(entity_id))
        except Exception as exc:
            raise ValidationError(str(exc)) from exc

        try:
            node = TreeNode.objects.get(pk=node_id)
        except TreeNode.DoesNotExist as exc:
            raise NotFound('Node not found') from exc

        if not TreeService.can_entity_access_node(node, entity):
            raise NotFound('Node not found')

        children = TreeService.get_children(node, entity)
        shares = TreeService.get_applicable_shares(entity)
        entity_ct_id = entity.__class__._meta.model_name

        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(entity.__class__)

        data = []
        for child in children:
            is_owned = child.owner_content_type_id == ct.id and child.owner_object_id == entity.pk
            if is_owned:
                meta = {'is_shared': False, 'shared_by': None}
            else:
                meta = TreeService._share_metadata_for_node(child, shares)
            data.append(serialize_tree_node(
                child, is_owned=is_owned, parent_id=child.parent_id, **meta,
            ))
        return Response(data)


class TreeNodeContentView(APIView):
    def get(self, request, node_id):
        entity_type = request.query_params.get('entity_type')
        entity_id = request.query_params.get('entity_id')
        if not entity_type or not entity_id:
            raise ValidationError({'detail': 'entity_type and entity_id query params are required'})

        entity = get_entity(entity_type, int(entity_id))

        try:
            node = TreeNode.objects.get(pk=node_id)
        except TreeNode.DoesNotExist as exc:
            raise NotFound('Node not found') from exc

        if not TreeService.can_entity_access_node(node, entity):
            raise NotFound('Node not found')

        if node.node_type != NodeType.LEAF:
            raise ValidationError({'detail': 'Node is not a leaf'})

        return Response(serialize_leaf_content(node))


class TreeNodeShareView(APIView):
    def post(self, request, node_id):
        sharer_type = request.data.get('sharer_type')
        sharer_id = request.data.get('sharer_id')
        if not sharer_type or not sharer_id:
            raise ValidationError({'detail': 'sharer_type and sharer_id are required'})

        sharer = get_entity(sharer_type, int(sharer_id))

        try:
            node = TreeNode.objects.get(pk=node_id)
        except TreeNode.DoesNotExist as exc:
            raise NotFound('Node not found') from exc

        serializer = CreateShareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target = None
        groupement = None
        if data['scope'] == ShareScope.EXPLICIT:
            target = get_entity(data['target']['entity_type'], data['target']['entity_id'])
        else:
            groupement = Groupement.objects.get(pk=data['groupement_id'])

        try:
            share = ShareService.create_share(
                sharer, node, data['scope'], target=target, groupement=groupement,
            )
        except Exception as exc:
            if hasattr(exc, 'message_dict'):
                raise ValidationError(exc.message_dict) from exc
            raise ValidationError(str(exc)) from exc

        return Response({
            'id': share.pk,
            'node_id': share.node_id,
            'scope': share.scope,
        }, status=status.HTTP_201_CREATED)


class TreeNodeBreadcrumbView(APIView):
    def get(self, request, node_id):
        entity_type = request.query_params.get('entity_type')
        entity_id = request.query_params.get('entity_id')
        if not entity_type or not entity_id:
            raise ValidationError({'detail': 'entity_type and entity_id query params are required'})

        entity = get_entity(entity_type, int(entity_id))

        try:
            node = TreeNode.objects.get(pk=node_id)
        except TreeNode.DoesNotExist as exc:
            raise NotFound('Node not found') from exc

        if not TreeService.can_entity_access_node(node, entity):
            raise NotFound('Node not found')

        chain = TreeService.get_breadcrumb(node)
        shares = TreeService.get_applicable_shares(entity)
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(entity.__class__)

        data = []
        for item in chain:
            is_owned = item.owner_content_type_id == ct.id and item.owner_object_id == entity.pk
            if is_owned:
                meta = {'is_shared': False, 'shared_by': None}
            else:
                meta = TreeService._share_metadata_for_node(item, shares)
            data.append(serialize_tree_node(
                item, is_owned=is_owned, parent_id=item.parent_id, **meta,
            ))
        return Response(data)


class TreeNodeMoveView(APIView):
    def patch(self, request, node_id):
        owner_type = request.data.get('owner_type')
        owner_id = request.data.get('owner_id')
        if not owner_type or not owner_id:
            raise ValidationError({'detail': 'owner_type and owner_id are required'})

        owner = get_entity(owner_type, int(owner_id))

        try:
            node = TreeNode.objects.get(pk=node_id)
        except TreeNode.DoesNotExist as exc:
            raise NotFound('Node not found') from exc

        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(owner.__class__)
        if node.owner_content_type_id != ct.id or node.owner_object_id != owner.pk:
            raise ValidationError({'detail': 'Only the node owner can move this node'})

        serializer = MoveNodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent_id = serializer.validated_data.get('parent_id')

        new_parent = None
        if parent_id is not None:
            try:
                new_parent = TreeNode.objects.get(pk=parent_id)
            except TreeNode.DoesNotExist as exc:
                raise ValidationError({'parent_id': 'Parent node not found'}) from exc

        try:
            node = TreeService.move_node(node, new_parent)
        except Exception as exc:
            if hasattr(exc, 'message_dict'):
                raise ValidationError(exc.message_dict) from exc
            raise ValidationError(str(exc)) from exc

        return Response(serialize_tree_node(
            node, is_owned=True, is_shared=False, shared_by=None, parent_id=node.parent_id,
        ))
