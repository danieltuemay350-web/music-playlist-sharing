from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import PlaylistCollaborator


def get_playlist_collaboration(user, playlist):
    if not user or not user.is_authenticated or playlist.owner_id == user.id:
        return None

    collaborators = getattr(playlist, "_prefetched_objects_cache", {}).get("collaborators")
    if collaborators is not None:
        return next((item for item in collaborators if item.user_id == user.id), None)

    return playlist.collaborators.filter(user_id=user.id).first()


def get_playlist_role(user, playlist):
    if not user or not user.is_authenticated:
        return None
    if playlist.owner_id == user.id:
        return "owner"

    collaboration = get_playlist_collaboration(user, playlist)
    return collaboration.role if collaboration else None


def can_view_playlist(user, playlist):
    return playlist.is_public or get_playlist_role(user, playlist) is not None


def can_edit_playlist_content(user, playlist):
    role = get_playlist_role(user, playlist)
    return role in ["owner", PlaylistCollaborator.Role.EDITOR]


def can_manage_playlist(user, playlist):
    return bool(user and user.is_authenticated and playlist.owner_id == user.id)


class PlaylistAccessPermission(BasePermission):
    def has_permission(self, request, view):
        if view.action in [
            "list",
            "create",
            "update",
            "partial_update",
            "destroy",
            "add_song",
            "remove_song",
        ]:
            return bool(request.user and request.user.is_authenticated)
        return True

    def has_object_permission(self, request, view, obj):
        if view.action in ["update", "partial_update", "destroy"]:
            return can_manage_playlist(request.user, obj)

        if view.action in ["add_song", "remove_song"]:
            return can_edit_playlist_content(request.user, obj)

        if request.method in SAFE_METHODS:
            return can_view_playlist(request.user, obj)

        return can_manage_playlist(request.user, obj)
