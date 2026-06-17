# TODO(test-validation): entire module is for PoC / manual API testing — remove before production.

from django.contrib.contenttypes.models import ContentType
from django.urls import path
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from document_tree.models import TreeNode
from document_tree.serializers import serialize_tree_node
from document_tree.services import TreeService
from document_tree.validators import get_entity

from .models import Groupement, Laboratory, Pharmacy
from .seed import seed_assessment_data
from .serializers import GroupementSerializer, LaboratorySerializer, PharmacySerializer


def _node_metadata(node, entity, shares, entity_ct):
    is_owned = node.owner_content_type_id == entity_ct.id and node.owner_object_id == entity.pk
    if is_owned:
        return is_owned, {'is_shared': False, 'shared_by': None}
    return is_owned, TreeService._share_metadata_for_node(node, shares)


def _build_subtree(node, entity, shares, entity_ct, *, depth=0):
    if depth >= TreeService.MAX_DEPTH:
        raise ValidationError({'detail': f'Subtree exceeds max depth ({TreeService.MAX_DEPTH})'})

    is_owned, meta = _node_metadata(node, entity, shares, entity_ct)
    children = [
        _build_subtree(child, entity, shares, entity_ct, depth=depth + 1)
        for child in TreeService.get_children(node, entity)
    ]
    return {
        **serialize_tree_node(node, is_owned=is_owned, parent_id=node.parent_id, **meta),
        'children': children,
    }


class ValidationEntityPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 50


class LaboratoryListView(generics.ListAPIView):
    """TODO(test-validation): list laboratories (max 50 per page)."""

    queryset = Laboratory.objects.order_by('name')
    serializer_class = LaboratorySerializer
    pagination_class = ValidationEntityPagination


class GroupementListView(generics.ListAPIView):
    """TODO(test-validation): list groupements (max 50 per page)."""

    queryset = Groupement.objects.order_by('name')
    serializer_class = GroupementSerializer
    pagination_class = ValidationEntityPagination


class PharmacyListView(generics.ListAPIView):
    """TODO(test-validation): list pharmacies (max 50 per page)."""

    queryset = Pharmacy.objects.select_related('groupement').order_by('name')
    serializer_class = PharmacySerializer
    pagination_class = ValidationEntityPagination


class SeedAssessmentDataView(APIView):
    """TODO(test-validation): POST to load CPC / Nuxe / Bioderma demo data (optional ?reset=false)."""

    def post(self, request):
        reset = request.query_params.get('reset', 'true').lower() != 'false'
        payload = seed_assessment_data(reset=reset)
        return Response(payload, status=status.HTTP_201_CREATED)


class TestTreeNodeSubtreeView(APIView):
    """TODO(test-validation): recursively list all descendants of a node (nested tree view)."""

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

        shares = TreeService.get_applicable_shares(entity)
        entity_ct = ContentType.objects.get_for_model(entity.__class__)
        return Response(_build_subtree(node, entity, shares, entity_ct))


urlpatterns = [
    path('laboratories/', LaboratoryListView.as_view(), name='test-laboratory-list'),
    path('groupements/', GroupementListView.as_view(), name='test-groupement-list'),
    path('pharmacies/', PharmacyListView.as_view(), name='test-pharmacy-list'),
    path('seed/', SeedAssessmentDataView.as_view(), name='test-seed-assessment'),
    path(
        'tree-nodes/<int:node_id>/subtree/',
        TestTreeNodeSubtreeView.as_view(),
        name='test-tree-node-subtree',
    ),
]
