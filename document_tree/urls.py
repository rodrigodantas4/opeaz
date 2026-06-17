from django.urls import path

from .views import (
    EntityTreeView,
    TreeNodeBreadcrumbView,
    TreeNodeChildrenView,
    TreeNodeContentView,
    TreeNodeMoveView,
    TreeNodeShareView,
)

urlpatterns = [
    path(
        'entities/<str:entity_type>/<int:entity_id>/tree/',
        EntityTreeView.as_view(),
        name='entity-tree',
    ),
    path(
        'tree-nodes/<int:node_id>/children/',
        TreeNodeChildrenView.as_view(),
        name='tree-node-children',
    ),
    path(
        'tree-nodes/<int:node_id>/content/',
        TreeNodeContentView.as_view(),
        name='tree-node-content',
    ),
    path(
        'tree-nodes/<int:node_id>/shares/',
        TreeNodeShareView.as_view(),
        name='tree-node-shares',
    ),
    path(
        'tree-nodes/<int:node_id>/breadcrumb/',
        TreeNodeBreadcrumbView.as_view(),
        name='tree-node-breadcrumb',
    ),
    path(
        'tree-nodes/<int:node_id>/move/',
        TreeNodeMoveView.as_view(),
        name='tree-node-move',
    ),
]
