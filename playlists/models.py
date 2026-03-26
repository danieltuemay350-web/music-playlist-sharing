import uuid

from django.conf import settings
from django.db import models


def generate_share_token():
    return uuid.uuid4().hex


class Song(models.Model):
    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255)
    external_url = models.URLField(max_length=500)
    platform = models.CharField(max_length=100)

    class Meta:
        ordering = ["artist", "title"]

    def __str__(self):
        return f"{self.title} - {self.artist}"


class Playlist(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="playlists",
    )
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    songs = models.ManyToManyField(Song, through="PlaylistSong", related_name="playlists")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class PlaylistSong(models.Model):
    playlist = models.ForeignKey(
        Playlist,
        on_delete=models.CASCADE,
        related_name="playlist_songs",
    )
    song = models.ForeignKey(
        Song,
        on_delete=models.CASCADE,
        related_name="playlist_entries",
    )
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["playlist", "song"],
                name="unique_song_per_playlist",
            ),
        ]
        indexes = [
            models.Index(fields=["playlist", "order"]),
        ]

    def __str__(self):
        return f"{self.playlist.name}: {self.song.title} ({self.order})"


class ShareLink(models.Model):
    playlist = models.ForeignKey(
        Playlist,
        on_delete=models.CASCADE,
        related_name="share_links",
    )
    token = models.CharField(max_length=64, unique=True, default=generate_share_token)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Share link for {self.playlist.name}"
