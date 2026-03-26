from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    LoginAPIView,
    PlaylistCollaboratorDetailAPIView,
    PlaylistCollaboratorListCreateAPIView,
    PlaylistCommentDetailAPIView,
    PlaylistCommentListCreateAPIView,
    PlaylistLikeAPIView,
    PlaylistViewSet,
    PublicPlaylistListAPIView,
    PublicPlaylistRetrieveAPIView,
    RegisterAPIView,
    SharedPlaylistRetrieveAPIView,
    SongViewSet,
)

router = DefaultRouter()
router.register("playlists", PlaylistViewSet, basename="playlist")
router.register("songs", SongViewSet, basename="song")

urlpatterns = [
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("public/playlists/", PublicPlaylistListAPIView.as_view(), name="public-playlist-list"),
    path(
        "public/playlists/<int:id>/",
        PublicPlaylistRetrieveAPIView.as_view(),
        name="public-playlist-detail",
    ),
    path("share/<str:token>/", SharedPlaylistRetrieveAPIView.as_view(), name="shared-playlist"),
    path(
        "playlists/<int:id>/collaborators/",
        PlaylistCollaboratorListCreateAPIView.as_view(),
        name="playlist-collaborator-list",
    ),
    path(
        "playlists/<int:id>/collaborators/<int:collaborator_id>/",
        PlaylistCollaboratorDetailAPIView.as_view(),
        name="playlist-collaborator-detail",
    ),
    path(
        "playlists/<int:id>/comments/",
        PlaylistCommentListCreateAPIView.as_view(),
        name="playlist-comment-list",
    ),
    path(
        "playlists/<int:id>/comments/<int:comment_id>/",
        PlaylistCommentDetailAPIView.as_view(),
        name="playlist-comment-detail",
    ),
    path(
        "playlists/<int:id>/like/",
        PlaylistLikeAPIView.as_view(),
        name="playlist-like",
    ),
]

urlpatterns += router.urls
