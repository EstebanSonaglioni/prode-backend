from rest_framework import serializers
from .models import UploadedImage


class BannerSerializer(serializers.ModelSerializer):
    """Minimal serializer for nested banner display."""
    image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UploadedImage
        fields = ['id', 'image_url']
        read_only_fields = ['id', 'image_url']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class UploadedImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField(read_only=True)
    content_type_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = UploadedImage
        fields = [
            'id', 'image', 'image_url', 'category', 'uploaded_by',
            'uploaded_at', 'content_type', 'object_id', 'content_type_name',
        ]
        read_only_fields = ['id', 'uploaded_by', 'uploaded_at', 'image_url', 'content_type_name']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    def get_content_type_name(self, obj):
        if obj.content_type:
            return f"{obj.content_type.app_label}.{obj.content_type.model}"
        return None

    def validate_image(self, value):
        # Allowed formats: jpg, jpeg, png, webp, gif
        allowed_extensions = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
        ext = value.name.split('.')[-1].lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"Invalid image format. Allowed: {', '.join(allowed_extensions)}."
            )

        # Max size: 5MB
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        if value.size > max_size:
            raise serializers.ValidationError("Image file too large. Max size is 5MB.")

        return value

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user
        category = attrs.get('category')

        # Normal users can only upload profile_photo
        if not user.is_staff and category != 'profile_photo':
            raise serializers.ValidationError(
                {"category": "Normal users can only upload profile photos."}
            )

        # If profile_photo, must be linked to the user themselves
        if category == 'profile_photo':
            content_type = attrs.get('content_type')
            object_id = attrs.get('object_id')
            if content_type and object_id:
                if not (content_type.model == 'user' and object_id == user.id):
                    raise serializers.ValidationError(
                        {"category": "Profile photos must be linked to your own user account."}
                    )
            # Auto-link to the current user if not provided
            if not content_type or not object_id:
                from django.contrib.contenttypes.models import ContentType
                user_ct = ContentType.objects.get_for_model(user)
                attrs['content_type'] = user_ct
                attrs['object_id'] = user.id

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['uploaded_by'] = request.user
        return super().create(validated_data)
