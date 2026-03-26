from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Playlist, PlaylistSong, ShareLink, Song

User = get_user_model()


class PlaylistAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="StrongPass123!",
        )

    def test_register_returns_jwt_tokens(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["username"], "newuser")

    def test_add_song_maintains_order_and_rejects_duplicates(self):
        self.client.force_authenticate(self.user)
        playlist_response = self.client.post(
            reverse("playlist-list"),
            {
                "name": "Road Trip",
                "description": "Weekend drive playlist",
                "is_public": False,
            },
            format="json",
        )
        playlist_id = playlist_response.data["id"]

        first_song = self.client.post(
            reverse("playlist-add-song", kwargs={"pk": playlist_id}),
            {
                "title": "Song A",
                "artist": "Artist A",
                "external_url": "https://example.com/a",
                "platform": "Spotify",
            },
            format="json",
        )
        second_song = self.client.post(
            reverse("playlist-add-song", kwargs={"pk": playlist_id}),
            {
                "title": "Song B",
                "artist": "Artist B",
                "external_url": "https://example.com/b",
                "platform": "YouTube",
            },
            format="json",
        )
        third_song = self.client.post(
            reverse("playlist-add-song", kwargs={"pk": playlist_id}),
            {
                "title": "Song C",
                "artist": "Artist C",
                "external_url": "https://example.com/c",
                "platform": "Spotify",
                "order": 2,
            },
            format="json",
        )

        self.assertEqual(first_song.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_song.status_code, status.HTTP_201_CREATED)
        self.assertEqual(third_song.status_code, status.HTTP_201_CREATED)

        detail_response = self.client.get(reverse("playlist-detail", kwargs={"pk": playlist_id}))
        ordered_titles = [item["song"]["title"] for item in detail_response.data["songs"]]
        ordered_positions = [item["order"] for item in detail_response.data["songs"]]

        self.assertEqual(ordered_titles, ["Song A", "Song C", "Song B"])
        self.assertEqual(ordered_positions, [1, 2, 3])

        duplicate_response = self.client.post(
            reverse("playlist-add-song", kwargs={"pk": playlist_id}),
            {
                "title": "Song A",
                "artist": "Artist A",
                "external_url": "https://example.com/a",
                "platform": "Spotify",
            },
            format="json",
        )

        self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_and_share_endpoints_allow_unauthenticated_access(self):
        public_playlist = Playlist.objects.create(
            name="Public Picks",
            description="Open for everyone",
            owner=self.user,
            is_public=True,
        )
        private_playlist = Playlist.objects.create(
            name="Private Picks",
            description="Shared by token only",
            owner=self.user,
            is_public=False,
        )
        share_link = ShareLink.objects.create(playlist=private_playlist)
        song = Song.objects.create(
            title="Shared Song",
            artist="Shared Artist",
            external_url="https://example.com/shared",
            platform="Spotify",
        )
        PlaylistSong.objects.create(playlist=public_playlist, song=song, order=1)
        PlaylistSong.objects.create(playlist=private_playlist, song=song, order=1)

        public_response = self.client.get(
            reverse("public-playlist-detail", kwargs={"id": public_playlist.id})
        )
        shared_response = self.client.get(
            reverse("shared-playlist", kwargs={"token": share_link.token})
        )
        direct_private_response = self.client.get(
            reverse("playlist-detail", kwargs={"pk": private_playlist.id})
        )

        self.assertEqual(public_response.status_code, status.HTTP_200_OK)
        self.assertEqual(shared_response.status_code, status.HTTP_200_OK)
        self.assertEqual(direct_private_response.status_code, status.HTTP_401_UNAUTHORIZED)
