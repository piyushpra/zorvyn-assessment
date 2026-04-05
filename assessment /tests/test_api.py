import json
import unittest
from io import BytesIO
from tempfile import TemporaryDirectory

from finance_backend.app import create_app
from finance_backend.config import Settings


class FinanceBackendAPITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.app = create_app(
            Settings(
                database_path="{root}/finance.db".format(root=self.temp_dir.name),
                host="127.0.0.1",
                port=8000,
                debug=True,
                seed_demo_data=True,
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def request(self, method, path, body=None, token=None, query=""):
        payload = b""
        if body is not None:
            payload = json.dumps(body).encode("utf-8")

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(payload)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": BytesIO(payload),
        }
        if token:
            environ["HTTP_AUTHORIZATION"] = "Bearer {token}".format(token=token)

        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        response = b"".join(self.app(environ, start_response))
        body_data = json.loads(response.decode("utf-8"))
        status_code = int(captured["status"].split(" ", 1)[0])
        return status_code, body_data

    def login(self, email, password):
        status_code, payload = self.request(
            "POST",
            "/api/v1/auth/login",
            body={"email": email, "password": password},
        )
        self.assertEqual(status_code, 200)
        return payload["data"]["access_token"], payload["data"]["user"]

    def test_login_and_me_returns_authenticated_user(self):
        token, user = self.login("admin@finance.local", "AdminPass123!")
        self.assertEqual(user["role"], "admin")

        status_code, payload = self.request("GET", "/api/v1/auth/me", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual(payload["data"]["email"], "admin@finance.local")

    def test_viewer_can_access_summary_but_not_records(self):
        token, _ = self.login("viewer@finance.local", "ViewerPass123!")

        status_code, summary = self.request("GET", "/api/v1/dashboard/summary", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual(summary["data"]["totals"]["income"], "8600.00")

        status_code, forbidden = self.request("GET", "/api/v1/records", token=token)
        self.assertEqual(status_code, 403)
        self.assertEqual(forbidden["error"]["code"], "forbidden")

    def test_analyst_can_list_records_but_cannot_create_record(self):
        token, _ = self.login("analyst@finance.local", "AnalystPass123!")

        status_code, records = self.request("GET", "/api/v1/records", token=token)
        self.assertEqual(status_code, 200)
        self.assertEqual(records["data"]["pagination"]["total"], 6)

        status_code, payload = self.request(
            "POST",
            "/api/v1/records",
            token=token,
            body={
                "amount": "50.00",
                "type": "expense",
                "category": "Taxi",
                "date": "2026-04-04",
            },
        )
        self.assertEqual(status_code, 403)
        self.assertEqual(payload["error"]["code"], "forbidden")

    def test_admin_can_manage_record_lifecycle(self):
        token, _ = self.login("admin@finance.local", "AdminPass123!")

        status_code, created = self.request(
            "POST",
            "/api/v1/records",
            token=token,
            body={
                "amount": "199.99",
                "type": "expense",
                "category": "Software",
                "date": "2026-04-05",
                "notes": "Team tooling",
            },
        )
        self.assertEqual(status_code, 201)
        record_id = created["data"]["id"]
        self.assertEqual(created["data"]["amount"], "199.99")

        status_code, updated = self.request(
            "PATCH",
            "/api/v1/records/{record_id}".format(record_id=record_id),
            token=token,
            body={"category": "Subscriptions", "amount": "249.99"},
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(updated["data"]["category"], "Subscriptions")
        self.assertEqual(updated["data"]["amount"], "249.99")

        status_code, deleted = self.request(
            "DELETE",
            "/api/v1/records/{record_id}".format(record_id=record_id),
            token=token,
        )
        self.assertEqual(status_code, 200)
        self.assertTrue(deleted["data"]["record"]["is_deleted"])

        status_code, missing = self.request(
            "GET",
            "/api/v1/records/{record_id}".format(record_id=record_id),
            token=token,
        )
        self.assertEqual(status_code, 404)
        self.assertEqual(missing["error"]["code"], "record_not_found")

    def test_admin_can_create_and_deactivate_users_but_not_self(self):
        token, admin_user = self.login("admin@finance.local", "AdminPass123!")

        status_code, created = self.request(
            "POST",
            "/api/v1/users",
            token=token,
            body={
                "name": "QA Reviewer",
                "email": "qa@example.com",
                "password": "QualityPass123!",
                "role": "viewer",
                "is_active": True,
            },
        )
        self.assertEqual(status_code, 201)
        user_id = created["data"]["id"]

        status_code, deactivated = self.request(
            "DELETE",
            "/api/v1/users/{user_id}".format(user_id=user_id),
            token=token,
        )
        self.assertEqual(status_code, 200)
        self.assertFalse(deactivated["data"]["user"]["is_active"])

        status_code, payload = self.request(
            "DELETE",
            "/api/v1/users/{user_id}".format(user_id=admin_user["id"]),
            token=token,
        )
        self.assertEqual(status_code, 409)
        self.assertEqual(payload["error"]["code"], "invalid_operation")

    def test_validation_errors_return_422(self):
        token, _ = self.login("admin@finance.local", "AdminPass123!")

        status_code, payload = self.request(
            "POST",
            "/api/v1/records",
            token=token,
            body={
                "amount": "-10.00",
                "type": "expense",
                "category": "",
                "date": "2026-04-05",
            },
        )
        self.assertEqual(status_code, 422)
        self.assertEqual(payload["error"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
