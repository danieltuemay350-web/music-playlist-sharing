from django.db import transaction
from django.db.models import Count, F, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Playlist, PlaylistSong, ShareLink
from .permissions import PlaylistAccessPermission
from .serializers import (
    AddSongToPlaylistSerializer,
    PlaylistDetailSerializer,
    PlaylistListSerializer,
    PlaylistWriteSerializer,
    PublicPlaylistDetailSerializer,
    RegisterSerializer,
    RegistrationResponseSerializer,
)


def playlist_queryset():
    playlist_song_queryset = PlaylistSong.objects.select_related("song").order_by("order")
    return Playlist.objects.select_related("owner").prefetch_related(
        Prefetch("playlist_songs", queryset=playlist_song_queryset),
        "share_links",
    )


class RegisterAPIView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        response_data = {
            "user": user,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
        headers = self.get_success_headers(serializer.data)
        return Response(
            RegistrationResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class LoginAPIView(TokenObtainPairView):
    permission_classes = [AllowAny]


class PlaylistViewSet(viewsets.ModelViewSet):
    permission_classes = [PlaylistAccessPermission]
    http_method_names = ["get", "post", "put", "delete"]

    def get_queryset(self):
        queryset = playlist_queryset()
        if self.action == "list":
            return queryset.filter(owner=self.request.user).annotate(
                song_count=Count("playlist_songs")
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return PlaylistListSerializer
        if self.action in ["create", "update", "partial_update"]:
            return PlaylistWriteSerializer
        if self.action == "add_song":
            return AddSongToPlaylistSerializer
        return PlaylistDetailSerializer

    def perform_create(self, serializer):
        playlist = serializer.save(owner=self.request.user)
        ShareLink.objects.create(playlist=playlist)

    @action(detail=True, methods=["post"], url_path="add-song")
    def add_song(self, request, pk=None):
        playlist = self.get_object()
        serializer_context = self.get_serializer_context()
        serializer_context["playlist"] = playlist
        serializer = self.get_serializer(data=request.data, context=serializer_context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        refreshed_playlist = playlist_queryset().get(pk=playlist.pk)
        return Response(
            PlaylistDetailSerializer(
                refreshed_playlist,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path=r"remove-song/(?P<song_id>\d+)")
    def remove_song(self, request, pk=None, song_id=None):
        playlist = self.get_object()
        playlist_song = get_object_or_404(PlaylistSong, playlist=playlist, song_id=song_id)

        with transaction.atomic():
            removed_order = playlist_song.order
            playlist_song.delete()
            PlaylistSong.objects.filter(
                playlist=playlist,
                order__gt=removed_order,
            ).update(order=F("order") - 1)

        playlist.refresh_from_db()
        refreshed_playlist = playlist_queryset().get(pk=playlist.pk)
        return Response(
            PlaylistDetailSerializer(
                refreshed_playlist,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )


class PublicPlaylistRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = PublicPlaylistDetailSerializer
    permission_classes = [AllowAny]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return playlist_queryset().filter(is_public=True)


class SharedPlaylistRetrieveAPIView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    lookup_field = "token"
    queryset = ShareLink.objects.select_related("playlist__owner").prefetch_related(
        Prefetch(
            "playlist__playlist_songs",
            queryset=PlaylistSong.objects.select_related("song").order_by("order"),
        ),
        "playlist__share_links",
    )

    def retrieve(self, request, *args, **kwargs):
        share_link = self.get_object()
        serializer = PublicPlaylistDetailSerializer(
            share_link.playlist,
            context={"request": request},
        )
        return Response(serializer.data)
