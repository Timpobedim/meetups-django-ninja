from unittest.mock import patch

from jwt_ninja.models import Session
from parameterized import parameterized

from apps.accounts.models import User
from helpers.jwt_utils import TokenAuth, create_jwt_token
from helpers.testing import ApiTestCase


class RegistrationAndLoginTest(ApiTestCase):
    def test_registration_returns_working_token(self) -> None:
        response = self.call(
            "POST",
            "/api/users",
            {"user": {"email": "Anna@Example.com", "username": "anna", "password": "password123"}},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()["user"]
        self.assertEqual(body["email"], "anna@example.com")
        me = self.call("GET", "/api/user", token=body["token"])
        self.assertEqual(me.json()["user"]["username"], "anna")

    def test_email_uniqueness_ignores_case(self) -> None:
        self.make_user("anna")

        response = self.call(
            "POST",
            "/api/users",
            {"user": {"email": "ANNA@example.com", "username": "other", "password": "password123"}},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"errors": {"email": ["уже занято"]}})

    def test_username_conflict_is_reported_by_field(self) -> None:
        self.make_user("anna")

        response = self.call(
            "POST",
            "/api/users",
            {"user": {"email": "new@example.com", "username": "anna", "password": "password123"}},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"errors": {"username": ["уже занято"]}})

    @parameterized.expand(
        [
            ("bad_email", {"email": "not-an-email", "username": "u1", "password": "password123"}, "email"),
            (
                "blank_username",
                {"email": "u@example.com", "username": " ", "password": "password123"},
                "username",
            ),
            ("short_password", {"email": "u@example.com", "username": "u1", "password": "short"}, "password"),
        ],
    )
    def test_registration_validation(self, _name: str, user: dict[str, str], field: str) -> None:
        response = self.call("POST", "/api/users", {"user": user})

        self.assertEqual(response.status_code, 422)
        self.assertIn(field, response.json()["errors"])

    def test_login(self) -> None:
        self.make_user("anna")

        ok = self.call(
            "POST", "/api/users/login", {"user": {"email": "ANNA@example.com", "password": "password123"}}
        )
        wrong = self.call(
            "POST", "/api/users/login", {"user": {"email": "anna@example.com", "password": "nope-nope"}}
        )

        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["user"]["token"])
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), {"errors": {"credentials": ["неверный email или пароль"]}})


class CurrentUserTest(ApiTestCase):
    def setUp(self) -> None:
        self.user = self.make_user("anna")
        self.token = create_jwt_token(self.user)

    def test_requires_token(self) -> None:
        missing = self.call("GET", "/api/user")
        invalid = self.call("GET", "/api/user", token="broken.token.value")

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json(), {"errors": {"token": ["отсутствует"]}})
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.json(), {"errors": {"token": ["invalid_token"]}})

    def test_bearer_prefix_is_accepted_and_no_extra_session_is_created(self) -> None:
        sessions_before = Session.objects.count()

        response = self.call("GET", "/api/user", token=self.token, prefix="Bearer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["token"], self.token)
        self.assertEqual(Session.objects.count(), sessions_before)

    def test_backend_returning_none_is_treated_as_anonymous(self) -> None:
        # jwtninja так не делает, но контракт HttpBearer допускает None — защитная ветка TokenAuth.
        with patch.object(TokenAuth, "authenticate", return_value=None):
            private = self.call("GET", "/api/user", token=self.token)
            public = self.call("GET", "/api/events", token=self.token)

        self.assertEqual(private.status_code, 401)
        self.assertEqual(public.status_code, 200)

    def test_partial_update(self) -> None:
        response = self.call(
            "PUT",
            "/api/user",
            {
                "user": {
                    "bio": "Организую Python-митапы",
                    "image": "https://example.com/a.png",
                    "username": "anna_p",
                }
            },
            token=self.token,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()["user"]
        self.assertEqual(body["bio"], "Организую Python-митапы")
        self.assertEqual(body["username"], "anna_p")
        self.assertEqual(body["token"], self.token)

    def test_email_taken_on_update(self) -> None:
        self.make_user("boris")

        response = self.call("PUT", "/api/user", {"user": {"email": "BORIS@example.com"}}, token=self.token)

        self.assertEqual(response.status_code, 409)

    def test_username_taken_on_update(self) -> None:
        self.make_user("boris")

        response = self.call("PUT", "/api/user", {"user": {"username": "boris"}}, token=self.token)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"errors": {"username": ["уже занято"]}})

    def test_password_change_revokes_old_tokens(self) -> None:
        response = self.call(
            "PUT", "/api/user", {"user": {"password": "brand-new-password"}}, token=self.token
        )
        new_token = response.json()["user"]["token"]

        old = self.call("GET", "/api/user", token=self.token)
        new = self.call("GET", "/api/user", token=new_token)

        self.assertNotEqual(new_token, self.token)
        self.assertEqual(old.status_code, 401)
        self.assertEqual(old.json(), {"errors": {"token": ["session_expired"]}})
        self.assertEqual(new.status_code, 200)

    def test_update_rejects_blank_values(self) -> None:
        response = self.call("PUT", "/api/user", {"user": {"username": ""}}, token=self.token)

        self.assertEqual(response.status_code, 422)


class ProfilesTest(ApiTestCase):
    def setUp(self) -> None:
        self.anna = self.make_user("anna")
        self.boris = self.make_user("boris")

    def test_anonymous_profile(self) -> None:
        response = self.call("GET", "/api/profiles/boris")

        self.assertEqual(
            response.json(),
            {"profile": {"username": "boris", "bio": None, "image": None, "following": False}},
        )

    def test_unknown_profile(self) -> None:
        response = self.call("GET", "/api/profiles/nobody")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"errors": {"profile": ["не найдено"]}})

    def test_follow_and_unfollow(self) -> None:
        followed = self.call("POST", "/api/profiles/boris/follow", user=self.anna)
        twice = self.call("POST", "/api/profiles/boris/follow", user=self.anna)
        seen = self.call("GET", "/api/profiles/boris", user=self.anna)
        unfollowed = self.call("DELETE", "/api/profiles/boris/follow", user=self.anna)
        again = self.call("DELETE", "/api/profiles/boris/follow", user=self.anna)

        self.assertTrue(followed.json()["profile"]["following"])
        self.assertEqual(twice.status_code, 409)
        self.assertTrue(seen.json()["profile"]["following"])
        self.assertFalse(unfollowed.json()["profile"]["following"])
        self.assertEqual(again.status_code, 409)

    def test_can_not_follow_self(self) -> None:
        follow = self.call("POST", "/api/profiles/anna/follow", user=self.anna)
        unfollow = self.call("DELETE", "/api/profiles/anna/follow", user=self.anna)

        self.assertEqual(follow.status_code, 403)
        self.assertEqual(follow.json(), {"errors": {"profile": ["нет прав"]}})
        self.assertEqual(unfollow.status_code, 403)


class JwtNinjaEndpointsTest(ApiTestCase):
    def test_login_endpoint_of_jwtninja_keeps_its_error_format(self) -> None:
        self.make_user("anna")

        ok = self.call("POST", "/auth/login/", {"username": "anna@example.com", "password": "password123"})
        bad = self.call(
            "POST", "/auth/login/", {"username": "anna@example.com", "password": "wrong-password"}
        )

        self.assertEqual(ok.status_code, 200)
        self.assertIn("access_token", ok.json())
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.json(), {"error_code": "invalid_credentials"})

    def test_refresh_token_is_not_accepted_as_access_token(self) -> None:
        # В референсе собственный authenticate не проверял тип токена — refresh проходил как access.
        self.make_user("anna")
        tokens = self.call(
            "POST", "/auth/login/", {"username": "anna@example.com", "password": "password123"}
        ).json()

        response = self.call("GET", "/api/user", token=tokens["refresh_token"])

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"errors": {"token": ["invalid_token_type"]}})

    def test_sessions_list_uses_our_token(self) -> None:
        user = self.make_user("anna")
        token = create_jwt_token(user)

        response = self.call("GET", "/auth/sessions/", token=token, prefix="Bearer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)


class UserModelTest(ApiTestCase):
    def test_superuser_and_helpers(self) -> None:
        admin = User.objects.create_superuser("admin@example.com", "admin-password", username="admin")
        passwordless = User.objects.create_user("x@example.com", username="x")

        self.assertTrue(admin.is_staff)
        self.assertEqual(admin.get_full_name(), "admin")
        self.assertEqual(admin.get_short_name(), "admin")
        self.assertFalse(passwordless.has_usable_password())
        with self.assertRaises(ValueError):
            User.objects.create_superuser("y@example.com", "pw-pw-pw-pw", username="y", is_staff=False)
        with self.assertRaises(ValueError):
            User.objects.create_superuser("z@example.com", "pw-pw-pw-pw", username="z", is_superuser=False)
