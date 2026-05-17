from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse, Http404
from .models import UploadedImage
from .serializers import UploadedImageSerializer
from .permissions import CanUploadImage


class UploadedImageViewSet(viewsets.ModelViewSet):
    queryset = UploadedImage.objects.all()
    serializer_class = UploadedImageSerializer
    permission_classes = [IsAuthenticated, CanUploadImage]
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        # Admins see everything; normal users see only their own uploads
        if user.is_staff:
            return UploadedImage.objects.all()
        return UploadedImage.objects.filter(uploaded_by=user)

    @action(detail=True, methods=['get'], url_path='download')
    def download(self, request, pk=None):
        """Return the raw image bytes."""
        try:
            image_obj = self.get_object()
        except UploadedImage.DoesNotExist:
            raise Http404("Image not found.")

        file_path = image_obj.image.path
        if not file_path:
            raise Http404("Image file not found.")

        return FileResponse(open(file_path, 'rb'), content_type='image/*')
