from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from core.models import Groupement, Pharmacy

from .models import NodeShare, NodeType, ShareScope, TreeNode
from .request_cache import get_cached_shares
from .validators import get_content_type_for_model, validate_tree_node


class TreeService:
    MAX_DEPTH = 20

    @staticmethod
    def _owner_filter(entity):
        ct = get_content_type_for_model(entity.__class__)
        return Q(owner_content_type=ct, owner_object_id=entity.pk)

    @classmethod
    def get_children(cls, node: TreeNode, _entity, request=None):
        """Return direct children; access is enforced on the parent node before calling."""
        return TreeNode.objects.filter(parent=node).order_by('name')

    @classmethod
    def get_breadcrumb(cls, node: TreeNode):
        chain = []
        current = node
        depth = 0
        while current is not None and depth < cls.MAX_DEPTH:
            chain.append(current)
            current = current.parent
            depth += 1
        chain.reverse()
        return chain

    @classmethod
    def _is_ancestor(cls, ancestor: TreeNode, node: TreeNode) -> bool:
        current = node.parent
        depth = 0
        while current is not None and depth < cls.MAX_DEPTH:
            if current.pk == ancestor.pk:
                return True
            current = current.parent
            depth += 1
        return False

    @classmethod
    @transaction.atomic
    def create_node(cls, *, name, node_type, owner, parent=None, content_obj=None):
        owner_ct = get_content_type_for_model(owner.__class__)
        content_ct = None
        content_id = None
        if content_obj is not None:
            content_ct = get_content_type_for_model(content_obj.__class__)
            content_id = content_obj.pk
        node = TreeNode(
            name=name,
            node_type=node_type,
            parent=parent,
            owner_content_type=owner_ct,
            owner_object_id=owner.pk,
            content_content_type=content_ct,
            content_object_id=content_id,
        )
        validate_tree_node(node)
        node.save()
        return node

    @classmethod
    @transaction.atomic
    def move_node(cls, node: TreeNode, new_parent: TreeNode | None):
        if new_parent and cls._is_ancestor(node, new_parent):
            raise ValidationError('Cannot move a node into its own descendant')
        if new_parent and new_parent.owner_content_type_id != node.owner_content_type_id:
            raise ValidationError('Cannot move node to a different owner tree')
        if new_parent and new_parent.owner_object_id != node.owner_object_id:
            raise ValidationError('Cannot move node to a different owner tree')
        node.parent = new_parent
        node.save(update_fields=['parent'])
        return node

    @classmethod
    def get_applicable_shares(cls, entity, request=None) -> list[NodeShare]:
        def fetch():
            entity_ct = get_content_type_for_model(entity.__class__)
            q = Q(scope=ShareScope.EXPLICIT, target_content_type=entity_ct, target_object_id=entity.pk)

            if isinstance(entity, Pharmacy) and entity.groupement_id:
                grp_ct = get_content_type_for_model(Groupement)
                q |= Q(scope=ShareScope.EXPLICIT, target_content_type=grp_ct, target_object_id=entity.groupement_id)
                q |= Q(scope=ShareScope.GROUPEMENT_ALL, groupement_id=entity.groupement_id)

            return list(
                NodeShare.objects.filter(q)
                .select_related(
                    'node', 'shared_by_content_type', 'groupement',
                    'target_content_type',
                )
            )

        return get_cached_shares(request, entity, fetch)

    @classmethod
    def share_metadata_for_node(cls, node: TreeNode, shares: list[NodeShare]):
        for share in shares:
            if share.node_id == node.pk or cls._is_ancestor(share.node, node):
                sharer = share.shared_by_content_type.model
                sharer_obj = share.shared_by_content_type.get_object_for_this_type(pk=share.shared_by_object_id)
                return {
                    'is_shared': True,
                    'shared_by': {
                        'entity_type': sharer,
                        'id': sharer_obj.pk,
                        'name': str(sharer_obj),
                    },
                }
        return {'is_shared': False, 'shared_by': None}

    @classmethod
    def can_entity_access_node(cls, node: TreeNode, entity, request=None) -> bool:
        owner_ct = get_content_type_for_model(entity.__class__)
        if node.owner_content_type_id == owner_ct.id and node.owner_object_id == entity.pk:
            return True
        shares = cls.get_applicable_shares(entity, request=request)
        for share in shares:
            if share.node_id == node.pk or cls._is_ancestor(share.node, node):
                return True
        return False

    @classmethod
    def build_aggregated_view(cls, entity, request=None):
        owner_q = cls._owner_filter(entity)

        own_roots = TreeNode.objects.filter(owner_q, parent__isnull=True).order_by('name')
        own_root_ids = list(own_roots.values_list('pk', flat=True))
        own_children = TreeNode.objects.filter(owner_q, parent_id__in=own_root_ids).order_by('name')

        shares = cls.get_applicable_shares(entity, request=request)
        shared_root_ids = {s.node_id for s in shares}
        shared_roots = TreeNode.objects.filter(pk__in=shared_root_ids).order_by('name')
        shared_children = TreeNode.objects.filter(parent_id__in=shared_root_ids).order_by('name')

        nodes = {}
        for node in list(own_roots) + list(own_children) + list(shared_roots) + list(shared_children):
            nodes[node.pk] = node

        result = []
        entity_ct = get_content_type_for_model(entity.__class__)

        for node in sorted(nodes.values(), key=lambda n: (n.parent_id or 0, n.name.lower())):
            is_owned = (
                node.owner_content_type_id == entity_ct.id
                and node.owner_object_id == entity.pk
            )
            meta = cls.share_metadata_for_node(node, shares) if not is_owned else {
                'is_shared': False, 'shared_by': None,
            }
            if not is_owned and not meta['is_shared']:
                continue

            api_parent_id = node.parent_id
            if not is_owned and node.parent_id and node.parent_id not in shared_root_ids:
                if node.parent_id not in own_root_ids:
                    parent = node.parent
                    while parent and parent.parent_id and parent.parent_id not in shared_root_ids:
                        parent = parent.parent
                    if parent and parent.pk in shared_root_ids:
                        api_parent_id = parent.pk
                    elif node.parent_id in shared_root_ids:
                        api_parent_id = node.parent_id
            if not is_owned and node.pk in shared_root_ids:
                api_parent_id = None

            result.append({
                'node': node,
                'is_owned': is_owned,
                'api_parent_id': api_parent_id,
                **meta,
            })

        return entity, result


class ShareService:
    @staticmethod
    @transaction.atomic
    def create_share(sharer, node: TreeNode, scope: str, target=None, groupement=None):
        from .validators import validate_share

        validate_share(sharer, node, scope, target=target, groupement=groupement)
        sharer_ct = get_content_type_for_model(sharer.__class__)

        share_kwargs = {
            'node': node,
            'scope': scope,
            'shared_by_content_type': sharer_ct,
            'shared_by_object_id': sharer.pk,
        }
        if scope == ShareScope.EXPLICIT:
            target_ct = get_content_type_for_model(target.__class__)
            share_kwargs.update({
                'target_content_type': target_ct,
                'target_object_id': target.pk,
                'groupement': None,
            })
        else:
            share_kwargs.update({
                'target_content_type': None,
                'target_object_id': None,
                'groupement': groupement,
            })

        return NodeShare.objects.create(**share_kwargs)
