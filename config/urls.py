from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
import sys

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('document_tree.urls')),
]

_validation_api_enabled = settings.DEBUG or 'test' in sys.argv
if _validation_api_enabled:
    # TODO(test-validation): test-only routes — remove before production.
    urlpatterns += [
        path('api/v1/test/', include('core.test_endpoints')),
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
