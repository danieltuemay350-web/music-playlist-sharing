from django.contrib import admin

from .models import (
    Playlist,
    PlaylistCollaborator,
    PlaylistComment,
    PlaylistLike,
    PlaylistSong,
    ShareLink,
    Song,
)


class PlaylistSongInline(admin.TabularInline):
    model = PlaylistSong
    extra = 0
    ordering = ["order"]
    autocomplete_fields = ["song"]


class PlaylistCollaboratorInline(admin.TabularInline):
    model = PlaylistCollaborator
    extra = 0
    autocomplete_fields = ["user", "added_by"]


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "artist", "platform"]
    search_fields = ["title", "artist", "platform"]


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "name",
        "owner",
        "is_public",
        "created_at",
    ]
    list_filter = ["is_public", "created_at"]
    search_fields = ["name", "description", "owner__username", "owner__email"]
    autocomplete_fields = ["owner"]
    inlines = [PlaylistSongInline, PlaylistCollaboratorInline]


@admin.register(PlaylistCollaborator)
class PlaylistCollaboratorAdmin(admin.ModelAdmin):
    list_display = ["id", "playlist", "user", "role", "added_by", "created_at"]
    list_filter = ["role", "created_at"]
    search_fields = ["playlist__name", "user__username", "user__email"]
    autocomplete_fields = ["playlist", "user", "added_by"]


@admin.register(PlaylistSong)
class PlaylistSongAdmin(admin.ModelAdmin):
    list_display = ["id", "playlist", "song", "order"]
    list_filter = ["playlist"]
    search_fields = ["playlist__name", "song__title", "song__artist"]
    autocomplete_fields = ["playlist", "song"]


@admin.register(PlaylistComment)
class PlaylistCommentAdmin(admin.ModelAdmin):
    list_display = ["id", "playlist", "user", "created_at", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["playlist__name", "user__username", "content"]
    autocomplete_fields = ["playlist", "user"]


@admin.register(PlaylistLike)
class PlaylistLikeAdmin(admin.ModelAdmin):
    list_display = ["id", "playlist", "user", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["playlist__name", "user__username", "user__email"]
    autocomplete_fields = ["playlist", "user"]


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ["id", "playlist", "token", "created_at"]
    search_fields = ["playlist__name", "token"]
    autocomplete_fields = ["playlist"]
