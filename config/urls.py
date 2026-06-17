from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('document_tree.urls')),
    # TODO(test-validation): test-only routes — remove before production.
    path('api/v1/test/', include('core.test_endpoints')),
]
