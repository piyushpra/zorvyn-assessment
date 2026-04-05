from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from http import HTTPStatus
from typing import Any, Callable, Dict, List, Optional, Tuple
import json
import re
from urllib.parse import parse_qs

from .errors import AppError


_JSON_UNSET = object()


@dataclass
class Request:
    method: str
    path: str
    query_params: Dict[str, str]
    headers: Dict[str, str]
    body: bytes
    path_params: Dict[str, str] = field(default_factory=dict)
    user: Optional[Dict[str, Any]] = None
    auth_token: Optional[str] = None
    _json_cache: Any = field(default=_JSON_UNSET, init=False, repr=False)

    def json(self) -> Any:
        if self._json_cache is not _JSON_UNSET:
            return self._json_cache
        if not self.body:
            self._json_cache = {}
            return self._json_cache
        try:
            self._json_cache = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AppError(
                status_code=400,
                code="invalid_json",
                message="Request body must be valid UTF-8 encoded JSON.",
                details=str(error),
            )
        return self._json_cache


class Route:
    def __init__(
        self,
        method: str,
        path_template: str,
        handler: Callable[[Request], Any],
        roles: Optional[List[str]] = None,
        auth_required: bool = True,
        status_code: int = 200,
    ) -> None:
        self.method = method.upper()
        self.path_template = path_template
        self.handler = handler
        self.roles = roles or []
        self.auth_required = auth_required
        self.status_code = status_code
        self.pattern = re.compile(
            "^" + re.sub(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", r"(?P<\1>[^/]+)", path_template) + "$"
        )


class Router:
    def __init__(self) -> None:
        self.routes: List[Route] = []

    def add(
        self,
        method: str,
        path_template: str,
        handler: Callable[[Request], Any],
        roles: Optional[List[str]] = None,
        auth_required: bool = True,
        status_code: int = 200,
    ) -> None:
        self.routes.append(
            Route(
                method=method,
                path_template=path_template,
                handler=handler,
                roles=roles,
                auth_required=auth_required,
                status_code=status_code,
            )
        )

    def resolve(self, method: str, path: str) -> Tuple[Optional[Route], Dict[str, str], List[str]]:
        allowed_methods: List[str] = []
        for route in self.routes:
            match = route.pattern.match(path)
            if not match:
                continue
            if route.method == method:
                return route, match.groupdict(), allowed_methods
            allowed_methods.append(route.method)
        return None, {}, sorted(set(allowed_methods))


def build_request(environ: Dict[str, Any]) -> Request:
    content_length_text = environ.get("CONTENT_LENGTH") or "0"
    try:
        content_length = int(content_length_text)
    except ValueError:
        content_length = 0

    query_params = {
        key: values[-1]
        for key, values in parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=False).items()
    }

    headers: Dict[str, str] = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            header_name = key[5:].replace("_", "-").lower()
            headers[header_name] = value
    if environ.get("CONTENT_TYPE"):
        headers["content-type"] = environ["CONTENT_TYPE"]
    if environ.get("CONTENT_LENGTH"):
        headers["content-length"] = environ["CONTENT_LENGTH"]

    body = environ["wsgi.input"].read(content_length) if content_length > 0 else b""
    return Request(
        method=environ["REQUEST_METHOD"].upper(),
        path=environ.get("PATH_INFO", "") or "/",
        query_params=query_params,
        headers=headers,
        body=body,
    )


def json_response(start_response: Callable[..., Any], status_code: int, payload: Dict[str, Any]) -> List[bytes]:
    body = json.dumps(payload, default=_json_default).encode("utf-8")
    start_response(
        "{code} {phrase}".format(code=status_code, phrase=HTTPStatus(status_code).phrase),
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return value.to_dict()
    raise TypeError("Object of type {name} is not JSON serializable".format(name=type(value).__name__))
