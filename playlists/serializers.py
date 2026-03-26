from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import F, Max
from rest_framework import serializers

from .models import (
    Playlist,
    PlaylistCollaborator,
    PlaylistComment,
    PlaylistSong,
    Song,
)
from .permissions import get_playlist_role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class RegistrationResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    refresh = serializers.CharField()
    access = serializers.CharField()


class SongSerializer(serializers.ModelSerializer):
    class Meta:
        model = Song
        fields = ["id", "title", "artist", "external_url", "platform"]


class PlaylistSongSerializer(serializers.ModelSerializer):
    song = SongSerializer(read_only=True)

    class Meta:
        model = PlaylistSong
        fields = ["id", "order", "song"]


class PlaylistCollaboratorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    added_by = serializers.CharField(source="added_by.username", read_only=True)

    class Meta:
        model = PlaylistCollaborator
        fields = ["id", "user", "role", "added_by", "created_at"]
        read_only_fields = fields


class PlaylistCollaboratorWriteSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(required=False, write_only=True)
    username = serializers.CharField(required=False, write_only=True)

    class Meta:
        model = PlaylistCollaborator
        fields = ["id", "user_id", "username", "role"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        user_id = attrs.get("user_id")
        username = attrs.get("username")
        playlist = self.context["playlist"]

        if self.instance is None and not user_id and not username:
            raise serializers.ValidationError(
                {"user_id": "Provide either user_id or username."}
            )

        if self.instance is not None and (user_id or username):
            raise serializers.ValidationError(
                {"user_id": "Updating collaborator user is not supported."}
            )

        if self.instance is None:
            query = User.objects.all()
            if user_id:
                user = query.filter(pk=user_id).first()
            else:
                user = query.filter(username=username).first()

            if user is None:
                raise serializers.ValidationError(
                    {"user_id": "The selected user does not exist."}
                )
            if playlist.owner_id == user.id:
                raise serializers.ValidationError(
                    {"user_id": "The playlist owner is already the owner."}
                )
            if playlist.collaborators.filter(user_id=user.id).exists():
                raise serializers.ValidationError(
                    {"user_id": "This user is already a collaborator."}
                )

            attrs["user"] = user

        return attrs

    def create(self, validated_data):
        validated_data.pop("user_id", None)
        validated_data.pop("username", None)
        return PlaylistCollaborator.objects.create(**validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("user_id", None)
        validated_data.pop("username", None)
        instance.role = validated_data.get("role", instance.role)
        instance.save(update_fields=["role"])
        return instance


class PlaylistCommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = PlaylistComment
        fields = ["id", "user", "content", "created_at", "updated_at"]
        read_only_fields = fields


class PlaylistCommentWriteSerializer(serializers.ModelSerializer):
    content = serializers.CharField(max_length=1000)

    class Meta:
        model = PlaylistComment
        fields = ["id", "content"]
        read_only_fields = ["id"]


class PlaylistListSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.username", read_only=True)
    song_count = serializers.IntegerField(read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    comments_count = serializers.IntegerField(read_only=True)
    collaborators_count = serializers.IntegerField(read_only=True)
    user_role = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = [
            "id",
            "name",
            "description",
            "owner",
            "is_public",
            "created_at",
            "song_count",
            "likes_count",
            "comments_count",
            "collaborators_count",
            "user_role",
            "is_liked",
        ]
        read_only_fields = fields

    def get_user_role(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return get_playlist_role(user, obj)

    def get_is_liked(self, obj):
        annotated_value = getattr(obj, "is_liked", None)
        if annotated_value is not None:
            return annotated_value

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        return obj.likes.filter(user=user).exists()


class PlaylistWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Playlist
        fields = ["id", "name", "description", "is_public"]
        read_only_fields = ["id"]


class PlaylistDetailSerializer(PlaylistListSerializer):
    songs = PlaylistSongSerializer(source="playlist_songs", many=True, read_only=True)
    collaborators = serializers.SerializerMethodField()
    share_token = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()

    class Meta(PlaylistListSerializer.Meta):
        fields = PlaylistListSerializer.Meta.fields + [
            "share_token",
            "share_url",
            "songs",
            "collaborators",
        ]
        read_only_fields = fields

    def get_collaborators(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or obj.owner_id != user.id:
            return []
        return PlaylistCollaboratorSerializer(obj.collaborators.all(), many=True).data

    def get_share_token(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or obj.owner_id != user.id:
            return None
        share_link = next(iter(obj.share_links.all()), None)
        return share_link.token if share_link else None

    def get_share_url(self, obj):
        share_token = self.get_share_token(obj)
        request = self.context.get("request")
        if not share_token or not request:
            return None
        return request.build_absolute_uri(f"/api/share/{share_token}/")


class PublicPlaylistDetailSerializer(PlaylistListSerializer):
    songs = PlaylistSongSerializer(source="playlist_songs", many=True, read_only=True)

    class Meta(PlaylistListSerializer.Meta):
        fields = PlaylistListSerializer.Meta.fields + ["songs"]
        read_only_fields = fields


class AddSongToPlaylistSerializer(serializers.Serializer):
    song_id = serializers.IntegerField(required=False)
    title = serializers.CharField(required=False, max_length=255)
    artist = serializers.CharField(required=False, max_length=255)
    external_url = serializers.URLField(required=False, max_length=500)
    platform = serializers.CharField(required=False, max_length=100)
    order = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        playlist = self.context["playlist"]
        song_id = attrs.get("song_id")

        if song_id is not None:
            try:
                song = Song.objects.get(pk=song_id)
            except Song.DoesNotExist as exc:
                raise serializers.ValidationError({"song_id": "Song does not exist."}) from exc
        else:
            missing_fields = [
                field
                for field in ["title", "artist", "external_url", "platform"]
                if not attrs.get(field)
            ]
            if missing_fields:
                raise serializers.ValidationError(
                    {
                        field: "This field is required when song_id is not provided."
                        for field in missing_fields
                    }
                )
            song = Song.objects.filter(
                title=attrs["title"],
                artist=attrs["artist"],
                external_url=attrs["external_url"],
                platform=attrs["platform"],
            ).first()

        duplicate_song_data = {
            "song__title": song.title if song else attrs["title"],
            "song__artist": song.artist if song else attrs["artist"],
            "song__external_url": song.external_url if song else attrs["external_url"],
            "song__platform": song.platform if song else attrs["platform"],
        }
        if playlist.playlist_songs.filter(**duplicate_song_data).exists():
            raise serializers.ValidationError(
                {"song_id": "This song already exists in the playlist."}
            )

        max_order = playlist.playlist_songs.aggregate(max_order=Max("order"))["max_order"] or 0
        requested_order = attrs.get("order", max_order + 1)
        if requested_order > max_order + 1:
            raise serializers.ValidationError(
                {"order": f"Order must be between 1 and {max_order + 1}."}
            )

        attrs["song"] = song
        if song is None:
            attrs["song_data"] = {
                "title": attrs["title"],
                "artist": attrs["artist"],
                "external_url": attrs["external_url"],
                "platform": attrs["platform"],
            }
        attrs["order"] = requested_order
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        playlist = self.context["playlist"]
        order = validated_data["order"]
        song = validated_data.get("song")

        if song is None:
            song, _ = Song.objects.get_or_create(**validated_data["song_data"])

        PlaylistSong.objects.filter(
            playlist=playlist,
            order__gte=order,
        ).update(order=F("order") + 1)

        return PlaylistSong.objects.create(
            playlist=playlist,
            song=song,
            order=order,
        )
