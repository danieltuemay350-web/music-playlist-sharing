from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import filters, generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    Playlist,
    PlaylistCollaborator,
    PlaylistComment,
    PlaylistLike,
    PlaylistSong,
    ShareLink,
    Song,
)
from .pagination import StandardResultsSetPagination
from .permissions import (
    PlaylistAccessPermission,
    can_edit_playlist_content,
    can_manage_playlist,
    can_view_playlist,
)
from .serializers import (
    AddSongToPlaylistSerializer,
    PlaylistCollaboratorSerializer,
    PlaylistCollaboratorWriteSerializer,
    PlaylistCommentSerializer,
    PlaylistCommentWriteSerializer,
    PlaylistDetailSerializer,
    PlaylistListSerializer,
    PlaylistWriteSerializer,
    PublicPlaylistDetailSerializer,
    RegisterSerializer,
    RegistrationResponseSerializer,
    SongSerializer,
)


def parse_bool(value):
    if value is None:
        return None
    if value.lower() in ["true", "1", "yes"]:
        return True
    if value.lower() in ["false", "0", "no"]:
        return False
    return None


def annotated_playlist_queryset(request=None):
    playlist_song_queryset = PlaylistSong.objects.select_related("song").order_by("order")
    collaborator_queryset = PlaylistCollaborator.objects.select_related(
        "user",
        "added_by",
    ).order_by("created_at")

    queryset = Playlist.objects.select_related("owner").prefetch_related(
        Prefetch("playlist_songs", queryset=playlist_song_queryset),
        Prefetch("collaborators", queryset=collaborator_queryset),
        "share_links",
    ).annotate(
        song_count=Count("playlist_songs", distinct=True),
        likes_count=Count("likes", distinct=True),
        comments_count=Count("comments", distinct=True),
        collaborators_count=Count("collaborators", distinct=True),
    )

    if request and request.user.is_authenticated:
        queryset = queryset.annotate(
            is_liked=Exists(
                PlaylistLike.objects.filter(
                    playlist_id=OuterRef("pk"),
                    user=request.user,
                )
            )
        )

    return queryset


def require_authenticated(request):
    if not request.user or not request.user.is_authenticated:
        raise NotAuthenticated("Authentication credentials were not provided.")


def require_playlist_view_access(request, playlist):
    if can_view_playlist(request.user, playlist):
        return

    if not request.user or not request.user.is_authenticated:
        raise NotAuthenticated("Authentication credentials were not provided.")

    raise PermissionDenied("You do not have access to this playlist.")


def require_playlist_edit_access(request, playlist):
    require_authenticated(request)
    if not can_edit_playlist_content(request.user, playlist):
        raise PermissionDenied("You do not have permission to edit this playlist.")


def require_playlist_owner(request, playlist):
    require_authenticated(request)
    if not can_manage_playlist(request.user, playlist):
        raise PermissionDenied("Only the playlist owner can perform this action.")


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


class SongViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SongSerializer
    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "artist", "platform"]
    ordering_fields = ["title", "artist", "platform", "id"]
    ordering = ["artist", "title"]

    def get_queryset(self):
        queryset = Song.objects.all()
        platform = self.request.query_params.get("platform")
        artist = self.request.query_params.get("artist")

        if platform:
            queryset = queryset.filter(platform__iexact=platform)
        if artist:
            queryset = queryset.filter(artist__icontains=artist)

        return queryset


class PlaylistViewSet(viewsets.ModelViewSet):
    permission_classes = [PlaylistAccessPermission]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description", "owner__username"]
    ordering_fields = [
        "created_at",
        "name",
        "song_count",
        "likes_count",
        "comments_count",
        "collaborators_count",
    ]
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "put", "delete"]

    def get_queryset(self):
        queryset = annotated_playlist_queryset(self.request)

        if self.action != "list":
            return queryset

        require_authenticated(self.request)
        scope = self.request.query_params.get("scope", "all")
        role = self.request.query_params.get("role")
        is_public = parse_bool(self.request.query_params.get("is_public"))
        owner = self.request.query_params.get("owner")

        if scope == "liked":
            queryset = queryset.filter(likes__user=self.request.user)
        else:
            queryset = queryset.filter(
                Q(owner=self.request.user) | Q(collaborators__user=self.request.user)
            )
            if scope == "owned":
                queryset = queryset.filter(owner=self.request.user)
            elif scope == "collaborating":
                queryset = queryset.filter(collaborators__user=self.request.user)

        if role == "owner":
            queryset = queryset.filter(owner=self.request.user)
        elif role in [PlaylistCollaborator.Role.EDITOR, PlaylistCollaborator.Role.VIEWER]:
            queryset = queryset.filter(
                collaborators__user=self.request.user,
                collaborators__role=role,
            )

        if is_public is not None:
            queryset = queryset.filter(is_public=is_public)
        if owner:
            queryset = queryset.filter(owner__username__icontains=owner)

        return queryset.distinct()

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
        refreshed_playlist = annotated_playlist_queryset(request).get(pk=playlist.pk)
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

        refreshed_playlist = annotated_playlist_queryset(request).get(pk=playlist.pk)
        return Response(
            PlaylistDetailSerializer(
                refreshed_playlist,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )


class PublicPlaylistListAPIView(generics.ListAPIView):
    serializer_class = PlaylistListSerializer
    permission_classes = [AllowAny]
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description", "owner__username"]
    ordering_fields = [
        "created_at",
        "name",
        "song_count",
        "likes_count",
        "comments_count",
    ]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = annotated_playlist_queryset(self.request).filter(is_public=True)
        owner = self.request.query_params.get("owner")
        if owner:
            queryset = queryset.filter(owner__username__icontains=owner)
        return queryset.distinct()


class PublicPlaylistRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = PublicPlaylistDetailSerializer
    permission_classes = [AllowAny]
    lookup_url_kwarg = "id"

    def get_queryset(self):
        return annotated_playlist_queryset(self.request).filter(is_public=True)


class SharedPlaylistRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = PublicPlaylistDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = "token"
    lookup_url_kwarg = "token"

    def get_object(self):
        return get_object_or_404(
            annotated_playlist_queryset(self.request),
            share_links__token=self.kwargs["token"],
        )


class PlaylistCollaboratorListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_playlist(self):
        playlist = get_object_or_404(annotated_playlist_queryset(self.request), pk=self.kwargs["id"])
        require_playlist_owner(self.request, playlist)
        return playlist

    def get_queryset(self):
        playlist = self.get_playlist()
        return playlist.collaborators.select_related("user", "added_by").order_by("created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PlaylistCollaboratorWriteSerializer
        return PlaylistCollaboratorSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["playlist"] = self.get_playlist()
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collaborator = serializer.save(
            playlist=self.get_playlist(),
            added_by=request.user,
        )
        return Response(
            PlaylistCollaboratorSerializer(collaborator).data,
            status=status.HTTP_201_CREATED,
        )


class PlaylistCollaboratorDetailAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PlaylistCollaboratorWriteSerializer

    def get_playlist(self):
        playlist = get_object_or_404(annotated_playlist_queryset(self.request), pk=self.kwargs["id"])
        require_playlist_owner(self.request, playlist)
        return playlist

    def get_object(self):
        playlist = self.get_playlist()
        return get_object_or_404(
            playlist.collaborators.select_related("user", "added_by"),
            pk=self.kwargs["collaborator_id"],
        )

    def put(self, request, *args, **kwargs):
        collaborator = self.get_object()
        serializer = self.get_serializer(
            collaborator,
            data=request.data,
            context={"playlist": collaborator.playlist},
        )
        serializer.is_valid(raise_exception=True)
        collaborator = serializer.save()
        return Response(PlaylistCollaboratorSerializer(collaborator).data)

    def delete(self, request, *args, **kwargs):
        collaborator = self.get_object()
        collaborator.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlaylistCommentListCreateAPIView(generics.ListCreateAPIView):
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["content", "user__username"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]

    def get_playlist(self):
        return get_object_or_404(annotated_playlist_queryset(self.request), pk=self.kwargs["id"])

    def get_queryset(self):
        playlist = self.get_playlist()
        require_playlist_view_access(self.request, playlist)
        queryset = playlist.comments.select_related("user").order_by("-created_at")
        user = self.request.query_params.get("user")
        if user:
            queryset = queryset.filter(user__username__icontains=user)
        return queryset

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PlaylistCommentWriteSerializer
        return PlaylistCommentSerializer

    def create(self, request, *args, **kwargs):
        playlist = self.get_playlist()
        require_authenticated(request)
        require_playlist_view_access(request, playlist)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(playlist=playlist, user=request.user)
        return Response(
            PlaylistCommentSerializer(comment).data,
            status=status.HTTP_201_CREATED,
        )


class PlaylistCommentDetailAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PlaylistCommentWriteSerializer

    def get_playlist(self):
        playlist = get_object_or_404(annotated_playlist_queryset(self.request), pk=self.kwargs["id"])
        require_playlist_view_access(self.request, playlist)
        return playlist

    def get_object(self):
        playlist = self.get_playlist()
        return get_object_or_404(
            playlist.comments.select_related("user"),
            pk=self.kwargs["comment_id"],
        )

    def put(self, request, *args, **kwargs):
        comment = self.get_object()
        if comment.user_id != request.user.id:
            raise PermissionDenied("You can only edit your own comments.")

        serializer = self.get_serializer(comment, data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save()
        return Response(PlaylistCommentSerializer(comment).data)

    def delete(self, request, *args, **kwargs):
        comment = self.get_object()
        if comment.user_id != request.user.id and comment.playlist.owner_id != request.user.id:
            raise PermissionDenied("You can only delete your own comments.")

        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlaylistLikeAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_playlist(self):
        playlist = get_object_or_404(annotated_playlist_queryset(self.request), pk=self.kwargs["id"])
        require_playlist_view_access(self.request, playlist)
        return playlist

    def post(self, request, *args, **kwargs):
        playlist = self.get_playlist()
        PlaylistLike.objects.get_or_create(playlist=playlist, user=request.user)
        refreshed_playlist = annotated_playlist_queryset(request).get(pk=playlist.pk)
        return Response(
            {
                "liked": True,
                "likes_count": refreshed_playlist.likes_count,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, *args, **kwargs):
        playlist = self.get_playlist()
        PlaylistLike.objects.filter(playlist=playlist, user=request.user).delete()
        refreshed_playlist = annotated_playlist_queryset(request).get(pk=playlist.pk)
        return Response(
            {
                "liked": False,
                "likes_count": refreshed_playlist.likes_count,
            },
            status=status.HTTP_200_OK,
        )
