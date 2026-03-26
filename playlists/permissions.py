from rest_framework.permissions import SAFE_METHODS, BasePermission


class PlaylistAccessPermission(BasePermission):
    def has_permission(self, request, view):
        if view.action in ["list", "create", "update", "partial_update", "destroy", "add_song", "remove_song"]:
            return request.user and request.user.is_authenticated
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return obj.is_public or (
                request.user.is_authenticated and obj.owner_id == request.user.id
            )
        return request.user.is_authenticated and obj.owner_id == request.user.id
