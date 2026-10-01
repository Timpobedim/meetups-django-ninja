from apps.comments.models import Comment
from helpers.testing import ApiTestCase


class CommentsTest(ApiTestCase):
    def setUp(self) -> None:
        self.organizer = self.make_user("organizer")
        self.guest = self.make_user("guest")
        self.event = self.make_event(self.organizer)
        self.url = f"/api/events/{self.event.slug}/comments"

    def test_create_and_list(self) -> None:
        created = self.call(
            "POST", self.url, {"comment": {"body": "Будет ли запись докладов?"}}, user=self.guest
        )
        listed = self.call("GET", self.url)

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["comment"]["author"]["username"], "guest")
        self.assertEqual([item["body"] for item in listed.json()["comments"]], ["Будет ли запись докладов?"])

    def test_anonymous_can_not_comment(self) -> None:
        response = self.call("POST", self.url, {"comment": {"body": "?"}})

        self.assertEqual(response.status_code, 401)

    def test_blank_comment_and_unknown_event(self) -> None:
        blank = self.call("POST", self.url, {"comment": {"body": "   "}}, user=self.guest)
        missing = self.call("POST", "/api/events/nope/comments", {"comment": {"body": "?"}}, user=self.guest)

        self.assertEqual(blank.status_code, 422)
        self.assertEqual(missing.status_code, 404)

    def test_author_and_organizer_can_delete(self) -> None:
        first = Comment.objects.create(event=self.event, author=self.guest, content="первый")
        second = Comment.objects.create(event=self.event, author=self.guest, content="второй")

        by_author = self.call("DELETE", f"{self.url}/{first.pk}", user=self.guest)
        by_organizer = self.call("DELETE", f"{self.url}/{second.pk}", user=self.organizer)

        self.assertEqual(by_author.status_code, 204)
        self.assertEqual(by_organizer.status_code, 204)
        self.assertFalse(Comment.objects.exists())

    def test_stranger_can_not_delete(self) -> None:
        comment = Comment.objects.create(event=self.event, author=self.guest, content="мой")
        stranger = self.make_user("stranger")

        response = self.call("DELETE", f"{self.url}/{comment.pk}", user=stranger)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"errors": {"comment": ["нет прав"]}})

    def test_comment_is_looked_up_within_event(self) -> None:
        comment = Comment.objects.create(event=self.event, author=self.guest, content="мой")
        other_event = self.make_event(self.organizer, "Другой митап")

        response = self.call(
            "DELETE", f"/api/events/{other_event.slug}/comments/{comment.pk}", user=self.guest
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"errors": {"comment": ["не найдено"]}})

    def test_following_flag_for_comment_author(self) -> None:
        Comment.objects.create(event=self.event, author=self.guest, content="мнение")
        self.guest.followers.add(self.organizer)

        response = self.call("GET", self.url, user=self.organizer)

        self.assertTrue(response.json()["comments"][0]["author"]["following"])
