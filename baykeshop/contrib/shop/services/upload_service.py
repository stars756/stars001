from django.conf import settings
from django.core.files.storage import FileSystemStorage


class UploadService:
    """文件上传服务"""

    @staticmethod
    def save_uploaded_file(image):
        storage = FileSystemStorage(
            location=settings.MEDIA_ROOT / "uploads",
            base_url=settings.MEDIA_URL + "uploads/",
        )
        file_name = storage.save(image.name, image)
        return storage.url(file_name)
