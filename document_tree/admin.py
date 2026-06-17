from django.contrib import admin

from .models import NodeShare, TreeNode

admin.site.register(TreeNode)
admin.site.register(NodeShare)
