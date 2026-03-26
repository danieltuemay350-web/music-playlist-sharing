from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Playlist,
    PlaylistCollaborator,
    PlaylistComment,
    PlaylistLike,
    PlaylistSong,
    ShareLink,
    Song,
)

User = get_user_model()


class PlaylistAPITests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="StrongPass123!",
        )
        self.editor = User.objects.create_user(
            username="editor",
            email="editor@example.com",
            password="StrongPass123!",
        )
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="StrongPass123!",
        )
        self.outsider = User.objects.create_user(
            username="outsider",
            email="outsider@example.com",
            password="StrongPass123!",
        )

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def create_playlist_via_api(self, name="Road Trip", is_public=False):
        self.authenticate(self.owner)
        response = self.client.post(
            reverse("playlist-list"),
            {
                "name": name,
                "description": f"{name} description",
                "is_public": is_public,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(None)
        return response.data["id"]

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

    def test_editor_collaborator_can_manage_songs_but_viewer_cannot(self):
        playlist_id = self.create_playlist_via_api(name="Team Mix", is_public=False)

        self.authenticate(self.owner)
        editor_response = self.client.post(
            reverse("playlist-collaborator-list", kwargs={"id": playlist_id}),
            {"user_id": self.editor.id, "role": PlaylistCollaborator.Role.EDITOR},
            format="json",
        )
        viewer_response = self.client.post(
            reverse("playlist-collaborator-list", kwargs={"id": playlist_id}),
            {"user_id": self.viewer.id, "role": PlaylistCollaborator.Role.VIEWER},
            format="json",
        )
        self.assertEqual(editor_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(viewer_response.status_code, status.HTTP_201_CREATED)

        self.authenticate(self.editor)
        detail_response = self.client.get(reverse("playlist-detail", kwargs={"pk": playlist_id}))
        add_song_response = self.client.post(
            reverse("playlist-add-song", kwargs={"pk": playlist_id}),
            {
                "title": "Song A",
                "artist": "Artist A",
                "external_url": "https://example.com/a",
                "platform": "Spotify",
            },
            format="json",
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["user_role"], PlaylistCollaborator.Role.EDITOR)
        self.assertEqual(add_song_response.status_code, status.HTTP_201_CREATED)

        self.authenticate(self.viewer)
        viewer_detail = self.client.get(reverse("playlist-detail", kwargs={"pk": playlist_id}))
        viewer_add_song = self.client.post(
            reverse("playlist-add-song", kwargs={"pk": playlist_id}),
            {
                "title": "Song B",
                "artist": "Artist B",
                "external_url": "https://example.com/b",
                "platform": "YouTube",
            },
            format="json",
        )

        self.assertEqual(viewer_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(viewer_detail.data["user_role"], PlaylistCollaborator.Role.VIEWER)
        self.assertEqual(viewer_add_song.status_code, status.HTTP_403_FORBIDDEN)

    def test_comments_and_likes_work_for_accessible_playlists(self):
        playlist_id = self.create_playlist_via_api(name="Open Mix", is_public=True)

        self.authenticate(self.outsider)
        like_response = self.client.post(reverse("playlist-like", kwargs={"id": playlist_id}))
        comment_response = self.client.post(
            reverse("playlist-comment-list", kwargs={"id": playlist_id}),
            {"content": "Great playlist for coding."},
            format="json",
        )
        comment_list = self.client.get(
            reverse("playlist-comment-list", kwargs={"id": playlist_id}),
            {"search": "coding"},
        )
        detail_response = self.client.get(reverse("playlist-detail", kwargs={"pk": playlist_id}))

        self.assertEqual(like_response.status_code, status.HTTP_200_OK)
        self.assertEqual(like_response.data["liked"], True)
        self.assertEqual(comment_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(comment_list.status_code, status.HTTP_200_OK)
        self.assertEqual(comment_list.data["count"], 1)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["likes_count"], 1)
        self.assertEqual(detail_response.data["comments_count"], 1)

        unlike_response = self.client.delete(reverse("playlist-like", kwargs={"id": playlist_id}))
        self.assertEqual(unlike_response.status_code, status.HTTP_200_OK)
        self.assertEqual(unlike_response.data["likes_count"], 0)

    def test_playlist_list_supports_pagination_scope_filter_and_search(self):
        Playlist.objects.create(
            name="Ignored Public",
            description="Not owned by test user",
            owner=self.outsider,
            is_public=True,
        )
        owned_private = Playlist.objects.create(
            name="Road Trip",
            description="Weekend drive",
            owner=self.owner,
            is_public=False,
        )
        Playlist.objects.create(
            name="Road Work",
            description="Public road playlist",
            owner=self.owner,
            is_public=True,
        )
        collaborative = Playlist.objects.create(
            name="Shared Focus",
            description="Study playlist",
            owner=self.outsider,
            is_public=False,
        )
        PlaylistCollaborator.objects.create(
            playlist=collaborative,
            user=self.owner,
            role=PlaylistCollaborator.Role.EDITOR,
            added_by=self.outsider,
        )
        PlaylistLike.objects.create(playlist=owned_private, user=self.owner)

        self.authenticate(self.owner)
        owned_response = self.client.get(
            reverse("playlist-list"),
            {"scope": "owned", "search": "Road", "page_size": 1},
        )
        collaborating_response = self.client.get(
            reverse("playlist-list"),
            {"scope": "collaborating"},
        )
        liked_response = self.client.get(
            reverse("playlist-list"),
            {"scope": "liked"},
        )
        public_owned_response = self.client.get(
            reverse("playlist-list"),
            {"scope": "owned", "is_public": "true"},
        )

        self.assertEqual(owned_response.status_code, status.HTTP_200_OK)
        self.assertEqual(owned_response.data["count"], 2)
        self.assertEqual(len(owned_response.data["results"]), 1)
        self.assertEqual(collaborating_response.data["count"], 1)
        self.assertEqual(collaborating_response.data["results"][0]["name"], "Shared Focus")
        self.assertEqual(liked_response.data["count"], 1)
        self.assertEqual(liked_response.data["results"][0]["name"], "Road Trip")
        self.assertEqual(public_owned_response.data["count"], 1)
        self.assertEqual(public_owned_response.data["results"][0]["name"], "Road Work")

    def test_public_playlist_and_song_endpoints_support_search_and_filtering(self):
        spotify_song = Song.objects.create(
            title="Focus Flow",
            artist="Artist One",
            external_url="https://example.com/focus-flow",
            platform="Spotify",
        )
        youtube_song = Song.objects.create(
            title="Night Drive",
            artist="Artist Two",
            external_url="https://example.com/night-drive",
            platform="YouTube",
        )
        public_playlist = Playlist.objects.create(
            name="Focus Session",
            description="Productive vibes",
            owner=self.owner,
            is_public=True,
        )
        private_playlist = Playlist.objects.create(
            name="Secret Session",
            description="Hidden vibes",
            owner=self.owner,
            is_public=False,
        )
        PlaylistSong.objects.create(playlist=public_playlist, song=spotify_song, order=1)
        PlaylistSong.objects.create(playlist=private_playlist, song=youtube_song, order=1)

        public_list = self.client.get(
            reverse("public-playlist-list"),
            {"search": "Focus"},
        )
        song_list = self.client.get(
            reverse("song-list"),
            {"search": "Artist", "platform": "Spotify"},
        )

        self.assertEqual(public_list.status_code, status.HTTP_200_OK)
        self.assertEqual(public_list.data["count"], 1)
        self.assertEqual(public_list.data["results"][0]["name"], "Focus Session")
        self.assertEqual(song_list.status_code, status.HTTP_200_OK)
        self.assertEqual(song_list.data["count"], 1)
        self.assertEqual(song_list.data["results"][0]["title"], "Focus Flow")

    def test_owner_can_update_and_remove_collaborators_and_shared_playlist_still_works(self):
        playlist_id = self.create_playlist_via_api(name="Private Picks", is_public=False)
        playlist = Playlist.objects.get(pk=playlist_id)
        share_link = ShareLink.objects.get(playlist=playlist)

        self.authenticate(self.owner)
        create_response = self.client.post(
            reverse("playlist-collaborator-list", kwargs={"id": playlist_id}),
            {"username": self.editor.username, "role": PlaylistCollaborator.Role.VIEWER},
            format="json",
        )
        collaborator_id = create_response.data["id"]
        update_response = self.client.put(
            reverse(
                "playlist-collaborator-detail",
                kwargs={"id": playlist_id, "collaborator_id": collaborator_id},
            ),
            {"role": PlaylistCollaborator.Role.EDITOR},
            format="json",
        )
        delete_response = self.client.delete(
            reverse(
                "playlist-collaborator-detail",
                kwargs={"id": playlist_id, "collaborator_id": collaborator_id},
            )
        )
        shared_response = self.client.get(
            reverse("shared-playlist", kwargs={"token": share_link.token})
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data["role"], PlaylistCollaborator.Role.EDITOR)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(shared_response.status_code, status.HTTP_200_OK)
        self.assertEqual(shared_response.data["name"], "Private Picks")

    def test_direct_private_playlist_access_requires_relationship(self):
        private_playlist = Playlist.objects.create(
            name="Private Vault",
            description="Restricted playlist",
            owner=self.owner,
            is_public=False,
        )

        anonymous_response = self.client.get(
            reverse("playlist-detail", kwargs={"pk": private_playlist.id})
        )

        self.authenticate(self.outsider)
        outsider_response = self.client.get(
            reverse("playlist-detail", kwargs={"pk": private_playlist.id})
        )

        self.assertIn(anonymous_response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        self.assertEqual(outsider_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            PlaylistComment.objects.filter(playlist=private_playlist, user=self.outsider).exists()
        )
