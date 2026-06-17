from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q

from core.models import Groupement, Laboratory, Pharmacy


class NodeType(models.TextChoices):
    FOLDER = 'folder', 'Folder'
    LEAF = 'leaf', 'Leaf'


class ShareScope(models.TextChoices):
    EXPLICIT = 'explicit', 'Explicit'
    GROUPEMENT_ALL = 'groupement_all', 'All pharmacies in groupement'


ALLOWED_OWNER_MODELS = (Laboratory, Groupement, Pharmacy)
ALLOWED_CONTENT_MODELS = ()  # populated after imports to avoid circular refs


class TreeNodeQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)


class TreeNodeManager(models.Manager.from_queryset(TreeNodeQuerySet)):
    def get_queryset(self):
        return super().get_queryset().alive()


class AllTreeNodeManager(models.Manager.from_queryset(TreeNodeQuerySet)):
    pass


class TreeNode(models.Model):
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.CASCADE, related_name='children',
    )
    name = models.CharField(max_length=255)
    node_type = models.CharField(max_length=10, choices=NodeType.choices)
    owner_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name='tree_nodes_owned',
    )
    owner_object_id = models.PositiveIntegerField()
    content_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tree_nodes_content',
    )
    content_object_id = models.PositiveIntegerField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TreeNodeManager()
    all_objects = AllTreeNodeManager()

    class Meta:
        indexes = [
            models.Index(fields=['parent']),
            models.Index(fields=['owner_content_type', 'owner_object_id']),
        ]

    def __str__(self):
        return self.name


class NodeShare(models.Model):
    node = models.ForeignKey(TreeNode, on_delete=models.CASCADE, related_name='shares')
    scope = models.CharField(
        max_length=20, choices=ShareScope.choices, default=ShareScope.EXPLICIT,
    )
    shared_by_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name='shares_created',
    )
    shared_by_object_id = models.PositiveIntegerField()
    target_content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.CASCADE,
        related_name='shares_targeted',
    )
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    groupement = models.ForeignKey(
        Groupement, null=True, blank=True, on_delete=models.CASCADE,
        related_name='node_shares',
    )
    permission = models.CharField(max_length=20, default='read_only')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['node']),
            models.Index(fields=['target_content_type', 'target_object_id']),
            models.Index(fields=['shared_by_content_type', 'shared_by_object_id']),
            models.Index(fields=['groupement']),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(scope='explicit', target_content_type__isnull=False, target_object_id__isnull=False, groupement__isnull=True)
                    | Q(scope='groupement_all', groupement__isnull=False, target_content_type__isnull=True, target_object_id__isnull=True)
                ),
                name='nodeshare_scope_consistency',
            ),
        ]


def get_owner_content_types():
    return ContentType.objects.get_for_models(*ALLOWED_OWNER_MODELS).values()


def get_content_content_types():
    from core.models import CommercialCondition, Document, Flyer
    return ContentType.objects.get_for_models(
        Document, Flyer, CommercialCondition,
    ).values()
