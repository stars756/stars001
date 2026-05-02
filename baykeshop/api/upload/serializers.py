from django.core.exceptions import ValidationError
from PIL import Image
from rest_framework import serializers

ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
MAX_SIZE = 2 * 1024 * 1024


class UploadImageSerializer(serializers.Serializer):
    file = serializers.ImageField(write_only=True)

    def validate_file(self, value):
        if value.size > MAX_SIZE:
            raise ValidationError(f"图片大小不能超过 {MAX_SIZE // 1024 // 1024}MB")
        if hasattr(value, 'content_type') and value.content_type not in ALLOWED_MIME:
            raise ValidationError("不支持的图片类型，仅支持 JPEG/PNG/GIF/WebP")
        try:
            img = Image.open(value)
            img.verify()
        except Exception:
            raise ValidationError("无法识别的图片格式或文件已损坏")
        value.seek(0)
        return value
