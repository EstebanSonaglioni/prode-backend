from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UploadedImageViewSet

router = DefaultRouter()
router.register(r'images', UploadedImageViewSet, basename='uploadedimage')

urlpatterns = [
    path('', include(router.urls)),
]
