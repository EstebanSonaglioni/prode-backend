# Generated manually for the media app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import media.models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='UploadedImage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('image', models.ImageField(upload_to=media.models.get_upload_path)),
                ('category', models.CharField(choices=[('profile_photo', 'Profile Photo'), ('banner', 'Banner'), ('tournament_logo', 'Tournament Logo'), ('team_flag', 'Team Flag'), ('other', 'Other')], default='other', max_length=30)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.contenttype')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='uploaded_images', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Uploaded Image',
                'verbose_name_plural': 'Uploaded Images',
                'ordering': ['-uploaded_at'],
            },
        ),
    ]
