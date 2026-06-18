# TODO(test-validation): entire module is for PoC / manual API testing — remove before production.

from django.contrib.contenttypes.models import ContentType
from django.urls import path
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from document_tree.authentication import EntitySessionAuthentication
from document_tree.context import clear_session_entity, get_accessible_node_or_404
from document_tree.mixins import EntityContextMixin
from document_tree.serializers import serialize_tree_node
from document_tree.services import TreeService

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

    authentication_classes = []

    queryset = Laboratory.objects.order_by('name')
    serializer_class = LaboratorySerializer
    pagination_class = ValidationEntityPagination


class GroupementListView(generics.ListAPIView):
    """TODO(test-validation): list groupements (max 50 per page)."""

    authentication_classes = []

    queryset = Groupement.objects.order_by('name')
    serializer_class = GroupementSerializer
    pagination_class = ValidationEntityPagination


class PharmacyListView(generics.ListAPIView):
    """TODO(test-validation): list pharmacies (max 50 per page)."""

    authentication_classes = []

    queryset = Pharmacy.objects.select_related('groupement').order_by('name')
    serializer_class = PharmacySerializer
    pagination_class = ValidationEntityPagination


class SeedAssessmentDataView(APIView):
    """TODO(test-validation): POST to load CPC / Nuxe / Bioderma demo data (optional ?reset=false)."""

    authentication_classes = []

    def post(self, request):
        reset = request.query_params.get('reset', 'true').lower() != 'false'
        if reset:
            clear_session_entity(request)
        payload = seed_assessment_data(reset=reset)
        return Response(payload, status=status.HTTP_201_CREATED)


class TestTreeNodeSubtreeView(EntityContextMixin, APIView):
    """TODO(test-validation): recursively list all descendants of a node (nested tree view)."""

    authentication_classes = [EntitySessionAuthentication]

    def get(self, request, node_id):
        entity = self.get_request_entity()
        node = get_accessible_node_or_404(node_id, entity)

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
