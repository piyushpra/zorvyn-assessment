"""User and authentication business rules."""

from typing import Any, Dict
from uuid import uuid4
import sqlite3

from ..db import connect, utcnow
from ..errors import AppError
from ..security import ROLE_ADMIN, hash_password, issue_token, verify_password
from .common import serialize_user


class UserService:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path

    def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
            if row is None or not verify_password(password, row["password_hash"]):
                raise AppError(401, "invalid_credentials", "Invalid email or password.")
            if not row["is_active"]:
                raise AppError(403, "inactive_user", "This account is inactive.")

            now = utcnow()
            token = issue_token()
            connection.execute(
                """
                INSERT INTO auth_tokens (token, user_id, created_at, last_used_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, row["id"], now, now),
            )
            connection.commit()
            return {
                "access_token": token,
                "token_type": "Bearer",
                "user": serialize_user(row),
            }

    def get_authenticated_user(self, token: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT u.*
                FROM auth_tokens t
                JOIN users u ON u.id = t.user_id
                WHERE t.token = ?
                """,
                (token,),
            ).fetchone()
            if row is None:
                raise AppError(401, "authentication_required", "A valid bearer token is required.")
            if not row["is_active"]:
                raise AppError(403, "inactive_user", "This account is inactive.")

            connection.execute(
                "UPDATE auth_tokens SET last_used_at = ? WHERE token = ?",
                (utcnow(), token),
            )
            connection.commit()
            return serialize_user(row)

    def revoke_token(self, token: str) -> None:
        with connect(self.database_path) as connection:
            connection.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
            connection.commit()

    def list_users(self) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
            return {"items": [serialize_user(row) for row in rows], "count": len(rows)}

    def get_user(self, user_id: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            row = self._fetch_user(connection, user_id)
            return serialize_user(row)

    def create_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        now = utcnow()
        user_id = str(uuid4())

        try:
            with connect(self.database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO users (id, name, email, password_hash, role, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        payload["name"],
                        payload["email"],
                        hash_password(payload["password"]),
                        payload["role"],
                        int(payload["is_active"]),
                        now,
                        now,
                    ),
                )
                row = self._fetch_user(connection, user_id)
                connection.commit()
                return serialize_user(row)
        except sqlite3.IntegrityError:
            raise AppError(409, "duplicate_email", "A user with this email already exists.")

    def update_user(self, user_id: str, payload: Dict[str, Any], actor_user_id: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            current_user = self._fetch_user(connection, user_id)
            self._validate_user_update(connection, current_user, payload, actor_user_id)

            updated_values = {
                "name": payload.get("name", current_user["name"]),
                "email": payload.get("email", current_user["email"]),
                "password_hash": (
                    hash_password(payload["password"])
                    if payload.get("password")
                    else current_user["password_hash"]
                ),
                "role": payload.get("role", current_user["role"]),
                "is_active": int(payload.get("is_active", bool(current_user["is_active"]))),
                "updated_at": utcnow(),
                "id": user_id,
            }

            try:
                connection.execute(
                    """
                    UPDATE users
                    SET name = :name,
                        email = :email,
                        password_hash = :password_hash,
                        role = :role,
                        is_active = :is_active,
                        updated_at = :updated_at
                    WHERE id = :id
                    """,
                    updated_values,
                )
            except sqlite3.IntegrityError:
                raise AppError(409, "duplicate_email", "A user with this email already exists.")

            if not updated_values["is_active"]:
                connection.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))

            updated_user = self._fetch_user(connection, user_id)
            connection.commit()
            return serialize_user(updated_user)

    def deactivate_user(self, user_id: str, actor_user_id: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            user = self._fetch_user(connection, user_id)
            if actor_user_id == user_id:
                raise AppError(409, "invalid_operation", "You cannot delete your own account.")
            if user["role"] == ROLE_ADMIN and user["is_active"] and self._count_active_admins(connection) <= 1:
                raise AppError(
                    409,
                    "last_active_admin",
                    "At least one active admin must remain in the system.",
                )

            connection.execute(
                "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
                (utcnow(), user_id),
            )
            connection.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))
            updated_user = self._fetch_user(connection, user_id)
            connection.commit()
            return {
                "message": "User deactivated successfully.",
                "user": serialize_user(updated_user),
            }

    def _validate_user_update(
        self,
        connection: sqlite3.Connection,
        current_user: sqlite3.Row,
        payload: Dict[str, Any],
        actor_user_id: str,
    ) -> None:
        new_role = payload.get("role", current_user["role"])
        new_is_active = payload.get("is_active", bool(current_user["is_active"]))

        if actor_user_id == current_user["id"] and payload.get("is_active") is False:
            raise AppError(409, "invalid_operation", "You cannot deactivate your own account.")
        if actor_user_id == current_user["id"] and payload.get("role") and new_role != current_user["role"]:
            raise AppError(409, "invalid_operation", "You cannot change your own role.")

        is_last_admin_change = (
            current_user["role"] == ROLE_ADMIN
            and current_user["is_active"]
            and (new_role != ROLE_ADMIN or not new_is_active)
        )
        if is_last_admin_change and self._count_active_admins(connection) <= 1:
            raise AppError(
                409,
                "last_active_admin",
                "At least one active admin must remain in the system.",
            )

    @staticmethod
    def _count_active_admins(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = ? AND is_active = 1",
            (ROLE_ADMIN,),
        ).fetchone()
        return int(row["count"])

    @staticmethod
    def _fetch_user(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise AppError(404, "user_not_found", "User not found.")
        return row
