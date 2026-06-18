import hashlib
import time
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.views import APIView


def compute_media_signature(path: str, expires: int) -> str:
    return hashlib.sha256(f'{path}:{expires}:{settings.SECRET_KEY}'.encode()).hexdigest()[:16]


def verify_media_signature(path: str, expires: str, sig: str) -> bool:
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    if expires_int < int(time.time()):
        return False
    return sig == compute_media_signature(path, expires_int)


class ProtectedMediaView(APIView):
    """Serve uploaded files when query signature and expiry are valid."""

    authentication_classes = []

    def get(self, request, path):
        expires = request.query_params.get('expires')
        sig = request.query_params.get('sig')
        if not expires or not sig or not verify_media_signature(path, expires, sig):
            raise Http404('Invalid or expired media URL')
        file_path = Path(settings.MEDIA_ROOT) / path
        if not file_path.is_file():
            raise Http404('File not found')
        return FileResponse(file_path.open('rb'), as_attachment=False)
