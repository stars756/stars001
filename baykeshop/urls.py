from django.urls import include, path
from drf_spectacular.views import (
                                   SpectacularAPIView,
                                   SpectacularRedocView,
                                   SpectacularSwaggerView,
)

urlpatterns = [
    path('member/', include('baykeshop.contrib.member.urls')),
    path('article/', include('baykeshop.contrib.article.urls')),
    path('', include('baykeshop.contrib.shop.urls')),
    # 接口url
    path('api/', include('baykeshop.api.urls', namespace='baykeshop_api')),
    # API 文档（drf-spectacular）
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
