from datetime import timedelta
from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from parameterized import parameterized

from apps.events.models import Event
from helpers.jwt_utils import create_jwt_token
from helpers.testing import ApiTestCase

FUTURE = "2031-03-14T19:00:00+03:00"


def event_payload(**overrides: Any) -> dict[str, Any]:
    event = {
        "title": "Встреча Python-разработчиков",
        "description": "Асинхронность и FastAPI",
        "body": "Три доклада и нетворкинг",
        "startsAt": FUTURE,
        "city": "Москва",
        "isOnline": False,
        "venue": "Коворкинг «Точка»",
        "capacity": 50,
        "tagList": ["Python", "fastapi", "python"],
    }
    event.update(overrides)
    return {"event": event}


class CreateAndReadEventTest(ApiTestCase):
    def setUp(self) -> None:
        self.organizer = self.make_user("organizer")

    def test_create_event(self) -> None:
        response = self.call("POST", "/api/events", event_payload(), user=self.organizer)

        self.assertEqual(response.status_code, 201)
        event = response.json()["event"]
        self.assertEqual(event["slug"], "vstrecha-python-razrabotchikov")
        self.assertEqual(event["tagList"], ["fastapi", "python"])
        self.assertEqual(event["seatsLeft"], 50)
        self.assertEqual(event["attendeesCount"], 0)
        self.assertFalse(event["attending"])
        self.assertEqual(event["organizer"]["username"], "organizer")
        self.assertEqual(event["body"], "Три доклада и нетворкинг")

    def test_duplicate_title_gets_unique_slug(self) -> None:
        first = self.call("POST", "/api/events", event_payload(), user=self.organizer).json()["event"]["slug"]
        second = self.call("POST", "/api/events", event_payload(), user=self.organizer).json()["event"][
            "slug"
        ]

        self.assertNotEqual(first, second)
        self.assertTrue(second.startswith(first + "-"))

    def test_create_requires_auth(self) -> None:
        response = self.call("POST", "/api/events", event_payload())

        self.assertEqual(response.status_code, 401)

    @parameterized.expand(
        [
            ("past_date", {"startsAt": "2020-01-01T10:00:00+03:00"}, "startsAt"),
            ("blank_title", {"title": "  "}, "title"),
            ("zero_capacity", {"capacity": 0}, "capacity"),
            ("too_many_tags", {"tagList": [f"t{i}" for i in range(11)]}, "tagList"),
        ],
    )
    def test_validation(self, _name: str, overrides: dict[str, Any], field: str) -> None:
        response = self.call("POST", "/api/events", event_payload(**overrides), user=self.organizer)

        self.assertEqual(response.status_code, 422)
        self.assertIn(field, response.json()["errors"])

    def test_retrieve_and_404(self) -> None:
        event = self.make_event(self.organizer, tags=["python"])

        found = self.call("GET", f"/api/events/{event.slug}")
        missing = self.call("GET", "/api/events/no-such-event")

        self.assertEqual(found.json()["event"]["title"], "Python-митап")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json(), {"errors": {"event": ["не найдено"]}})

    def test_tags_are_listed(self) -> None:
        self.make_event(self.organizer, "A", tags=["sql", "python"])
        self.make_event(self.organizer, "B", tags=["airflow"])

        response = self.call("GET", "/api/tags")

        self.assertEqual(response.json(), {"tags": ["airflow", "python", "sql"]})


class ListEventsTest(ApiTestCase):
    def setUp(self) -> None:
        self.organizer = self.make_user("organizer")
        self.other = self.make_user("other")

    def slugs(self, path: str, **kwargs: Any) -> list[str]:
        return [item["slug"] for item in self.call("GET", path, **kwargs).json()["events"]]

    def test_pagination_newest_first(self) -> None:
        created = [self.make_event(self.organizer, f"Митап {index}") for index in range(5)]

        response = self.call("GET", "/api/events?limit=2&offset=1").json()

        self.assertEqual(response["eventsCount"], 5)
        self.assertEqual([item["slug"] for item in response["events"]], [created[3].slug, created[2].slug])
        self.assertNotIn("body", response["events"][0])

    @parameterized.expand(
        [("zero_limit", "limit=0"), ("big_limit", "limit=500"), ("negative_offset", "offset=-1")]
    )
    def test_invalid_page(self, _name: str, query: str) -> None:
        response = self.call("GET", f"/api/events?{query}")

        self.assertEqual(response.status_code, 422)

    def test_filters(self) -> None:
        python = self.make_event(self.organizer, "Python", tags=["python"], city="Москва")
        online = self.make_event(self.other, "Online SQL", tags=["sql"], is_online=True, city="")
        online.attendees.add(self.organizer)

        self.assertEqual(self.slugs("/api/events?tag=PYTHON"), [python.slug])
        self.assertEqual(self.slugs("/api/events?organizer=other"), [online.slug])
        self.assertEqual(self.slugs("/api/events?attendee=organizer"), [online.slug])
        self.assertEqual(self.slugs("/api/events?city=Моск"), [python.slug])
        self.assertEqual(self.slugs("/api/events?online=true"), [online.slug])
        self.assertEqual(self.slugs("/api/events?online=false"), [python.slug])

    def test_upcoming_is_sorted_by_start_and_hides_past(self) -> None:
        later = self.make_event(self.organizer, "Позже", starts_at=timezone.now() + timedelta(days=30))
        sooner = self.make_event(self.organizer, "Раньше", starts_at=timezone.now() + timedelta(days=2))
        self.make_event(self.organizer, "Прошло", starts_at=timezone.now() - timedelta(days=1))

        self.assertEqual(self.slugs("/api/events?upcoming=true"), [sooner.slug, later.slug])

    def test_attendee_filter_does_not_distort_count(self) -> None:
        event = self.make_event(self.organizer)
        for index in range(3):
            event.attendees.add(self.make_user(f"fan{index}"))
        event.attendees.add(self.other)

        response = self.call("GET", "/api/events?attendee=other").json()

        self.assertEqual(response["events"][0]["attendeesCount"], 4)

    def test_feed(self) -> None:
        followed_event = self.make_event(self.organizer, "От подписки")
        self.make_event(self.other, "Без подписки")
        self.organizer.followers.add(self.other)

        response = self.call("GET", "/api/events/feed", user=self.other).json()
        anonymous = self.call("GET", "/api/events/feed")

        self.assertEqual([item["slug"] for item in response["events"]], [followed_event.slug])
        self.assertTrue(response["events"][0]["organizer"]["following"])
        self.assertEqual(anonymous.status_code, 401)

    def test_list_has_no_n_plus_one(self) -> None:
        viewer = self.make_user("viewer")
        for index in range(10):
            event = self.make_event(self.organizer, f"Митап {index}", tags=["python", "sql"])
            event.attendees.add(viewer)
        self.organizer.followers.add(viewer)
        # Токен создаётся до замера: create_session блокирует пользователя и пишет сессию.
        token = create_jwt_token(viewer)

        # аутентификация (пользователь) + страница + prefetch тегов + COUNT
        with CaptureQueriesContext(connection) as queries:
            response = self.call("GET", "/api/events", token=token)

        page_queries = [q for q in queries.captured_queries if "jwt_ninja_session" not in q["sql"]]
        self.assertEqual(len(response.json()["events"]), 10)
        self.assertLessEqual(len(page_queries), 5)
        self.assertTrue(all(item["attending"] for item in response.json()["events"]))


class AttendanceTest(ApiTestCase):
    def setUp(self) -> None:
        self.organizer = self.make_user("organizer")
        self.guest = self.make_user("guest")

    def test_attend_and_leave(self) -> None:
        event = self.make_event(self.organizer, capacity=2)

        joined = self.call("POST", f"/api/events/{event.slug}/attend", user=self.guest)
        twice = self.call("POST", f"/api/events/{event.slug}/attend", user=self.guest)
        left = self.call("DELETE", f"/api/events/{event.slug}/attend", user=self.guest)
        not_attending = self.call("DELETE", f"/api/events/{event.slug}/attend", user=self.guest)

        self.assertEqual(joined.status_code, 200)
        self.assertTrue(joined.json()["event"]["attending"])
        self.assertEqual(joined.json()["event"]["seatsLeft"], 1)
        self.assertEqual(twice.status_code, 409)
        self.assertFalse(left.json()["event"]["attending"])
        self.assertEqual(left.json()["event"]["attendeesCount"], 0)
        self.assertEqual(not_attending.status_code, 404)

    def test_no_seats_left(self) -> None:
        event = self.make_event(self.organizer, capacity=1)
        event.attendees.add(self.make_user("first"))

        response = self.call("POST", f"/api/events/{event.slug}/attend", user=self.guest)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"errors": {"event": ["свободных мест нет"]}})

    def test_past_event(self) -> None:
        event = self.make_event(self.organizer, starts_at=timezone.now() - timedelta(hours=1))

        response = self.call("POST", f"/api/events/{event.slug}/attend", user=self.guest)

        self.assertEqual(response.status_code, 400)

    def test_unknown_event(self) -> None:
        response = self.call("POST", "/api/events/nope/attend", user=self.guest)

        self.assertEqual(response.status_code, 404)


class ModifyEventTest(ApiTestCase):
    def setUp(self) -> None:
        self.organizer = self.make_user("organizer")
        self.stranger = self.make_user("stranger")
        self.event = self.make_event(self.organizer, tags=["python"], capacity=10)

    def test_organizer_updates_title_tags_and_slug_follows_title(self) -> None:
        response = self.call(
            "PUT",
            f"/api/events/{self.event.slug}",
            {"event": {"title": "Митап по Django", "tagList": ["django"], "city": "Казань"}},
            user=self.organizer,
        )

        event = response.json()["event"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(event["slug"], "mitap-po-django")
        self.assertEqual(event["tagList"], ["django"])
        self.assertEqual(event["city"], "Казань")

    def test_capacity_can_not_drop_below_attendees(self) -> None:
        for index in range(3):
            self.event.attendees.add(self.make_user(f"a{index}"))

        response = self.call(
            "PUT", f"/api/events/{self.event.slug}", {"event": {"capacity": 2}}, user=self.organizer
        )

        self.assertEqual(response.status_code, 409)

    def test_update_validation(self) -> None:
        response = self.call(
            "PUT",
            f"/api/events/{self.event.slug}",
            {"event": {"startsAt": "2020-01-01T10:00:00+03:00"}},
            user=self.organizer,
        )

        self.assertEqual(response.status_code, 422)

    def test_stranger_can_not_modify(self) -> None:
        update = self.call(
            "PUT", f"/api/events/{self.event.slug}", {"event": {"title": "X"}}, user=self.stranger
        )
        delete = self.call("DELETE", f"/api/events/{self.event.slug}", user=self.stranger)

        self.assertEqual(update.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.assertEqual(delete.json(), {"errors": {"event": ["нет прав"]}})

    def test_organizer_deletes_event(self) -> None:
        response = self.call("DELETE", f"/api/events/{self.event.slug}", user=self.organizer)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())
