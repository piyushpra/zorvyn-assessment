from typing import Any, Dict, Type
import traceback

from pydantic import BaseModel, ValidationError

from .config import Settings, load_settings
from .db import initialize_database, seed_demo_data
from .errors import AppError, from_validation_error
from .http import Request, Router, build_request, json_response
from .schemas import (
    LoginRequest,
    RecordCreateRequest,
    RecordListQuery,
    RecordUpdateRequest,
    SummaryQuery,
    TrendQuery,
    UserCreateRequest,
    UserUpdateRequest,
)
from .security import ALL_ROLES, ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER, extract_bearer_token
from .services import DashboardService, RecordService, UserService


class FinanceApplication:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        initialize_database(settings.database_path)
        if settings.seed_demo_data:
            seed_demo_data(settings.database_path)

        self.users = UserService(settings.database_path)
        self.records = RecordService(settings.database_path)
        self.dashboard = DashboardService(settings.database_path)
        self.router = Router()
        self._register_routes()

    def __call__(self, environ: Dict[str, Any], start_response: Any) -> Any:
        try:
            request = build_request(environ)
            route, path_params, allowed_methods = self.router.resolve(request.method, request.path)
            if route is None:
                if allowed_methods:
                    raise AppError(
                        405,
                        "method_not_allowed",
                        "Method {method} is not allowed for this route.".format(method=request.method),
                        details={"allowed_methods": allowed_methods},
                    )
                raise AppError(404, "not_found", "Resource not found.")

            request.path_params = path_params
            if route.auth_required:
                token = extract_bearer_token(request.headers)
                if token is None:
                    raise AppError(401, "authentication_required", "A bearer token is required.")
                request.auth_token = token
                request.user = self.users.get_authenticated_user(token)

                if route.roles and request.user["role"] not in route.roles:
                    raise AppError(
                        403,
                        "forbidden",
                        "This user role is not allowed to perform the requested action.",
                    )

            response_data = route.handler(request)
            return json_response(start_response, route.status_code, {"data": response_data})
        except AppError as error:
            return json_response(start_response, error.status_code, error.to_dict())
        except Exception:
            if self.settings.debug:
                details = traceback.format_exc()
            else:
                details = None
            error = AppError(500, "internal_server_error", "An unexpected error occurred.", details)
            return json_response(start_response, error.status_code, error.to_dict())

    def _register_routes(self) -> None:
        self.router.add("GET", "/", self.home, auth_required=False)
        self.router.add("GET", "/health", self.health, auth_required=False)
        self.router.add("POST", "/api/v1/auth/login", self.login, auth_required=False)
        self.router.add("GET", "/api/v1/auth/me", self.me, roles=list(ALL_ROLES))
        self.router.add("POST", "/api/v1/auth/logout", self.logout, roles=list(ALL_ROLES))

        self.router.add("GET", "/api/v1/users", self.list_users, roles=[ROLE_ADMIN])
        self.router.add("POST", "/api/v1/users", self.create_user, roles=[ROLE_ADMIN], status_code=201)
        self.router.add("GET", "/api/v1/users/{user_id}", self.get_user, roles=[ROLE_ADMIN])
        self.router.add("PATCH", "/api/v1/users/{user_id}", self.update_user, roles=[ROLE_ADMIN])
        self.router.add("DELETE", "/api/v1/users/{user_id}", self.delete_user, roles=[ROLE_ADMIN])

        self.router.add("GET", "/api/v1/records", self.list_records, roles=[ROLE_ADMIN, ROLE_ANALYST])
        self.router.add("POST", "/api/v1/records", self.create_record, roles=[ROLE_ADMIN], status_code=201)
        self.router.add("GET", "/api/v1/records/{record_id}", self.get_record, roles=[ROLE_ADMIN, ROLE_ANALYST])
        self.router.add("PATCH", "/api/v1/records/{record_id}", self.update_record, roles=[ROLE_ADMIN])
        self.router.add("DELETE", "/api/v1/records/{record_id}", self.delete_record, roles=[ROLE_ADMIN])

        self.router.add(
            "GET",
            "/api/v1/dashboard/summary",
            self.summary,
            roles=[ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN],
        )
        self.router.add(
            "GET",
            "/api/v1/dashboard/trends",
            self.trends,
            roles=[ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN],
        )

    @staticmethod
    def home(_: Request) -> Dict[str, Any]:
        return {
            "service": "finance-data-processing-backend",
            "version": "1.0.0",
            "docs_hint": "See README.md for setup instructions and API examples.",
        }

    def health(self, _: Request) -> Dict[str, Any]:
        return {
            "status": "ok",
            "database_path": self.settings.database_path,
            "seed_demo_data": self.settings.seed_demo_data,
        }

    def login(self, request: Request) -> Dict[str, Any]:
        payload = self._parse_body(request, LoginRequest)
        return self.users.authenticate(payload["email"], payload["password"])

    @staticmethod
    def me(request: Request) -> Dict[str, Any]:
        return request.user or {}

    def logout(self, request: Request) -> Dict[str, Any]:
        self.users.revoke_token(request.auth_token or "")
        return {"message": "Logged out successfully."}

    def list_users(self, _: Request) -> Dict[str, Any]:
        return self.users.list_users()

    def create_user(self, request: Request) -> Dict[str, Any]:
        payload = self._parse_body(request, UserCreateRequest)
        return self.users.create_user(payload)

    def get_user(self, request: Request) -> Dict[str, Any]:
        return self.users.get_user(request.path_params["user_id"])

    def update_user(self, request: Request) -> Dict[str, Any]:
        payload = self._parse_body(request, UserUpdateRequest)
        return self.users.update_user(
            request.path_params["user_id"],
            payload,
            actor_user_id=request.user["id"],
        )

    def delete_user(self, request: Request) -> Dict[str, Any]:
        return self.users.deactivate_user(
            request.path_params["user_id"],
            actor_user_id=request.user["id"],
        )

    def list_records(self, request: Request) -> Dict[str, Any]:
        filters = self._parse_query(request, RecordListQuery)
        return self.records.list_records(filters)

    def create_record(self, request: Request) -> Dict[str, Any]:
        payload = self._parse_body(request, RecordCreateRequest)
        return self.records.create_record(payload, actor_user_id=request.user["id"])

    def get_record(self, request: Request) -> Dict[str, Any]:
        return self.records.get_record(request.path_params["record_id"])

    def update_record(self, request: Request) -> Dict[str, Any]:
        payload = self._parse_body(request, RecordUpdateRequest)
        return self.records.update_record(
            request.path_params["record_id"],
            payload,
            actor_user_id=request.user["id"],
        )

    def delete_record(self, request: Request) -> Dict[str, Any]:
        return self.records.delete_record(
            request.path_params["record_id"],
            actor_user_id=request.user["id"],
        )

    def summary(self, request: Request) -> Dict[str, Any]:
        filters = self._parse_query(request, SummaryQuery)
        return self.dashboard.get_summary(filters)

    def trends(self, request: Request) -> Dict[str, Any]:
        filters = self._parse_query(request, TrendQuery)
        return self.dashboard.get_trends(filters)

    @staticmethod
    def _parse_body(request: Request, model_class: Type[BaseModel]) -> Dict[str, Any]:
        payload = request.json()
        if not isinstance(payload, dict):
            raise AppError(400, "invalid_json", "Request body must be a JSON object.")
        try:
            model = model_class.model_validate(payload)
        except ValidationError as error:
            raise from_validation_error(error)
        return model.model_dump(exclude_none=True)

    @staticmethod
    def _parse_query(request: Request, model_class: Type[BaseModel]) -> Dict[str, Any]:
        try:
            model = model_class.model_validate(request.query_params)
        except ValidationError as error:
            raise from_validation_error(error)
        return model.model_dump(exclude_none=True)


def create_app(settings: Settings = None) -> FinanceApplication:
    return FinanceApplication(settings or load_settings())
