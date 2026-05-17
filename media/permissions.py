from rest_framework import permissions


class CanUploadImage(permissions.BasePermission):
    """
    Normal users can only create profile_photo images linked to themselves.
    Staff users can create any category.
    Any authenticated user can retrieve their own images.
    Staff can retrieve any image.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if view.action == 'create':
            category = request.data.get('category', 'other')
            if category != 'profile_photo' and not request.user.is_staff:
                return False
            return True

        # For list/retrieve/update/destroy, we filter in get_queryset
        return True

    def has_object_permission(self, request, view, obj):
        # Allow if owner or staff
        if request.user.is_staff:
            return True
        return obj.uploaded_by == request.user
