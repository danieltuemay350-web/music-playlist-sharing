from django.contrib import admin

from .models import Playlist, PlaylistSong, ShareLink, Song


class PlaylistSongInline(admin.TabularInline):
    model = PlaylistSong
    extra = 0
    ordering = ["order"]
    autocomplete_fields = ["song"]


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "artist", "platform"]
    search_fields = ["title", "artist", "platform"]


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "owner", "is_public", "created_at"]
    list_filter = ["is_public", "created_at"]
    search_fields = ["name", "owner__username", "owner__email"]
    autocomplete_fields = ["owner"]
    inlines = [PlaylistSongInline]


@admin.register(PlaylistSong)
class PlaylistSongAdmin(admin.ModelAdmin):
    list_display = ["id", "playlist", "song", "order"]
    list_filter = ["playlist"]
    search_fields = ["playlist__name", "song__title", "song__artist"]
    autocomplete_fields = ["playlist", "song"]


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ["id", "playlist", "token", "created_at"]
    search_fields = ["playlist__name", "token"]
    autocomplete_fields = ["playlist"]
