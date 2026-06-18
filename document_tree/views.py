from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Groupement

from .authentication import EntitySessionAuthentication, OptionalEntitySessionAuthentication
from .context import clear_session_entity, get_accessible_node_or_404, resolve_mutation_entity, set_session_entity
from .mixins import EntityContextMixin
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


def _validation_error_from_django(exc: DjangoValidationError) -> ValidationError:
    if hasattr(exc, 'message_dict'):
        return ValidationError(exc.message_dict)
    if hasattr(exc, 'messages'):
        return ValidationError(exc.messages)
    return ValidationError(str(exc))


class EntitySessionView(APIView):
    authentication_classes = []

    def post(self, request):
        entity_type = request.data.get('entity_type')
        entity_id = request.data.get('entity_id')
        if not entity_type or entity_id is None:
            raise ValidationError({'detail': 'entity_type and entity_id are required'})
        try:
            set_session_entity(request, entity_type, int(entity_id))
        except ValidationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ValidationError({'entity_id': 'Must be an integer'}) from exc
        return Response(
            {'entity_type': entity_type, 'entity_id': int(entity_id)},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request):
        clear_session_entity(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EntityTreeView(EntityContextMixin, APIView):
    authentication_classes = [EntitySessionAuthentication]

    def get(self, request):
        entity = self.get_request_entity()
        try:
            _, items = TreeService.build_aggregated_view(entity, request=request)
        except DjangoValidationError as exc:
            raise _validation_error_from_django(exc) from exc
        serializer = AggregatedTreeSerializer()
        return Response(serializer.to_representation(items))


class TreeNodeChildrenView(EntityContextMixin, APIView):
    authentication_classes = [EntitySessionAuthentication]

    def get(self, request, node_id):
        entity = self.get_request_entity()
        node = get_accessible_node_or_404(node_id, entity, request=request)

        children = TreeService.get_children(node, entity, request=request)
        shares = TreeService.get_applicable_shares(entity, request=request)

        ct = ContentType.objects.get_for_model(entity.__class__)

        data = []
        for child in children:
            is_owned = child.owner_content_type_id == ct.id and child.owner_object_id == entity.pk
            if is_owned:
                meta = {'is_shared': False, 'shared_by': None}
            else:
                meta = TreeService.share_metadata_for_node(child, shares)
            data.append(serialize_tree_node(
                child, is_owned=is_owned, parent_id=child.parent_id, **meta,
            ))
        return Response(data)


class TreeNodeContentView(EntityContextMixin, APIView):
    authentication_classes = [EntitySessionAuthentication]

    def get(self, request, node_id):
        entity = self.get_request_entity()
        node = get_accessible_node_or_404(node_id, entity, request=request)

        if node.node_type != NodeType.LEAF:
            raise ValidationError({'detail': 'Node is not a leaf'})

        return Response(serialize_leaf_content(node))


class TreeNodeShareView(APIView):
    """
    PoC: prefers session entity as sharer; body sharer_type/sharer_id accepted
    only when no session is bound (manual testing).
    """

    authentication_classes = [OptionalEntitySessionAuthentication]

    def post(self, request, node_id):
        sharer = resolve_mutation_entity(request, type_key='sharer_type', id_key='sharer_id')

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
        except DjangoValidationError as exc:
            raise _validation_error_from_django(exc) from exc

        return Response({
            'id': share.pk,
            'node_id': share.node_id,
            'scope': share.scope,
        }, status=status.HTTP_201_CREATED)


class TreeNodeBreadcrumbView(EntityContextMixin, APIView):
    authentication_classes = [EntitySessionAuthentication]

    def get(self, request, node_id):
        entity = self.get_request_entity()
        node = get_accessible_node_or_404(node_id, entity, request=request)

        chain = TreeService.get_breadcrumb(node)
        shares = TreeService.get_applicable_shares(entity, request=request)
        ct = ContentType.objects.get_for_model(entity.__class__)

        data = []
        for item in chain:
            is_owned = item.owner_content_type_id == ct.id and item.owner_object_id == entity.pk
            if is_owned:
                meta = {'is_shared': False, 'shared_by': None}
            else:
                meta = TreeService.share_metadata_for_node(item, shares)
            data.append(serialize_tree_node(
                item, is_owned=is_owned, parent_id=item.parent_id, **meta,
            ))
        return Response(data)


class TreeNodeMoveView(APIView):
    """
    PoC: prefers session entity as owner; body owner_type/owner_id accepted
    only when no session is bound (manual testing).
    """

    authentication_classes = [OptionalEntitySessionAuthentication]

    def patch(self, request, node_id):
        owner = resolve_mutation_entity(request, type_key='owner_type', id_key='owner_id')

        try:
            node = TreeNode.objects.get(pk=node_id)
        except TreeNode.DoesNotExist as exc:
            raise NotFound('Node not found') from exc

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
        except DjangoValidationError as exc:
            raise _validation_error_from_django(exc) from exc

        return Response(serialize_tree_node(
            node, is_owned=True, is_shared=False, shared_by=None, parent_id=node.parent_id,
        ))
