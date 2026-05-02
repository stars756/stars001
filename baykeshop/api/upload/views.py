import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from baykeshop.api.throttles import UploadRateThrottle

from .serializers import UploadImageSerializer


class UploadImageView(GenericAPIView):
    serializer_class = UploadImageSerializer
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = [UploadRateThrottle]

    def post(self, request, *args, **kwargs):
        """上传图片"""
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        image = serializer.validated_data["file"]

        # 从已验证的 MIME 类型推导扩展名（防御深度）
        MIME_EXT = {'image/jpeg': 'jpg', 'image/png': 'png',
                     'image/gif': 'gif', 'image/webp': 'webp'}
        content_type = getattr(image, 'content_type', '')
        ext = MIME_EXT.get(content_type, 'jpg')

        safe_name = f"{uuid.uuid4()}.{ext}"

        storage = FileSystemStorage(
            location=settings.MEDIA_ROOT / "uploads",
            base_url=settings.MEDIA_URL + "uploads/",
        )
        file_name = storage.save(safe_name, image)
        url = storage.url(file_name)
        return Response({"location": url})
