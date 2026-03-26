from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    LoginAPIView,
    PlaylistViewSet,
    PublicPlaylistRetrieveAPIView,
    RegisterAPIView,
    SharedPlaylistRetrieveAPIView,
)

router = DefaultRouter()
router.register("playlists", PlaylistViewSet, basename="playlist")

urlpatterns = [
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path(
        "public/playlists/<int:id>/",
        PublicPlaylistRetrieveAPIView.as_view(),
        name="public-playlist-detail",
    ),
    path("share/<str:token>/", SharedPlaylistRetrieveAPIView.as_view(), name="shared-playlist"),
]

urlpatterns += router.urls
