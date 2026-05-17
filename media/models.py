import uuid
import os
from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


def get_upload_path(instance, filename):
    """Store images under media/<category>/<uuid>_filename"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext.lower()}"
    return os.path.join(instance.category, filename)


class UploadedImage(models.Model):
    CATEGORY_CHOICES = [
        ('profile_photo', 'Profile Photo'),
        ('banner', 'Banner'),
        ('tournament_logo', 'Tournament Logo'),
        ('team_flag', 'Team Flag'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ImageField(upload_to=get_upload_path)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='other')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_images')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Generic relation to link the image to any object (Tournament, User, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Uploaded Image'
        verbose_name_plural = 'Uploaded Images'

    def __str__(self):
        return f"{self.category} - {self.id}"
