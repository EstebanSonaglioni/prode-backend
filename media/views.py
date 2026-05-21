from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import FileResponse, Http404, HttpResponseRedirect
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
        """Return the raw image bytes, or redirect to S3 URL if using remote storage."""
        try:
            image_obj = self.get_object()
        except UploadedImage.DoesNotExist:
            raise Http404("Image not found.")

        if not image_obj.image:
            raise Http404("Image file not found.")

        try:
            file_path = image_obj.image.path
            return FileResponse(open(file_path, 'rb'), content_type='image/*')
        except (NotImplementedError, ValueError, FileNotFoundError):
            # Remote storage (S3): redirect to public URL
            return HttpResponseRedirect(image_obj.image.url)
