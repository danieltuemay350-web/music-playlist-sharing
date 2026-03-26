from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import F, Max
from rest_framework import serializers

from .models import Playlist, PlaylistSong, Song

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


class PlaylistListSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.username", read_only=True)
    song_count = serializers.IntegerField(read_only=True)

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
        ]
        read_only_fields = ["id", "owner", "created_at", "song_count"]


class PlaylistWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Playlist
        fields = ["id", "name", "description", "is_public"]
        read_only_fields = ["id"]


class PlaylistDetailSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.username", read_only=True)
    songs = PlaylistSongSerializer(source="playlist_songs", many=True, read_only=True)
    share_token = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()

    class Meta:
        model = Playlist
        fields = [
            "id",
            "name",
            "description",
            "owner",
            "is_public",
            "created_at",
            "share_token",
            "share_url",
            "songs",
        ]
        read_only_fields = fields

    def get_share_token(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated or request.user != obj.owner:
            return None
        share_link = next(iter(obj.share_links.all()), None)
        return share_link.token if share_link else None

    def get_share_url(self, obj):
        share_token = self.get_share_token(obj)
        request = self.context.get("request")
        if not share_token or not request:
            return None
        return request.build_absolute_uri(f"/api/share/{share_token}/")


class PublicPlaylistDetailSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.username", read_only=True)
    songs = PlaylistSongSerializer(source="playlist_songs", many=True, read_only=True)

    class Meta:
        model = Playlist
        fields = [
            "id",
            "name",
            "description",
            "owner",
            "is_public",
            "created_at",
            "songs",
        ]
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
