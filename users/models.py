import uuid
import os

from django.contrib.auth.models import AbstractUser
from django.db import models


def get_avatar_upload_path(instance, filename):
    """Generate a unique filename for avatar uploads to prevent overwrites."""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext.lower()}"
    return os.path.join('avatars', filename)


class User(AbstractUser):
    avatar = models.ImageField(upload_to=get_avatar_upload_path, blank=True, null=True)

    def get_avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return None
