"""Financial record CRUD and filtering."""

from typing import Any, Dict, List, Tuple
from uuid import uuid4
import sqlite3

from ..db import connect, utcnow
from ..errors import AppError
from .common import cents_from_decimal, serialize_record


class RecordService:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path

    def list_records(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        where_clause, parameters = build_record_filters(filters)
        limit = filters["limit"]
        offset = filters["offset"]

        with connect(self.database_path) as connection:
            total = connection.execute(
                "SELECT COUNT(*) AS count FROM financial_records fr WHERE {where_clause}".format(
                    where_clause=where_clause
                ),
                parameters,
            ).fetchone()["count"]

            rows = connection.execute(
                """
                SELECT
                    fr.*,
                    creator.name AS created_by_name,
                    updater.name AS updated_by_name
                FROM financial_records fr
                LEFT JOIN users creator ON creator.id = fr.created_by
                LEFT JOIN users updater ON updater.id = fr.updated_by
                WHERE {where_clause}
                ORDER BY fr.entry_date DESC, fr.created_at DESC
                LIMIT ? OFFSET ?
                """.format(where_clause=where_clause),
                parameters + [limit, offset],
            ).fetchall()

            return {
                "items": [serialize_record(row) for row in rows],
                "pagination": {
                    "total": int(total),
                    "limit": limit,
                    "offset": offset,
                },
            }

    def get_record(self, record_id: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            row = self._fetch_record(connection, record_id)
            return serialize_record(row)

    def create_record(self, payload: Dict[str, Any], actor_user_id: str) -> Dict[str, Any]:
        now = utcnow()
        record_id = str(uuid4())

        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO financial_records (
                    id, amount_cents, type, category, entry_date, notes, is_deleted,
                    created_by, updated_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    cents_from_decimal(payload["amount"]),
                    payload["type"],
                    payload["category"],
                    payload["date"].isoformat(),
                    payload.get("notes"),
                    actor_user_id,
                    actor_user_id,
                    now,
                    now,
                ),
            )
            record = self._fetch_record(connection, record_id)
            connection.commit()
            return serialize_record(record)

    def update_record(self, record_id: str, payload: Dict[str, Any], actor_user_id: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            current_record = self._fetch_record(connection, record_id)
            updated_values = {
                "amount_cents": (
                    cents_from_decimal(payload["amount"])
                    if payload.get("amount")
                    else current_record["amount_cents"]
                ),
                "type": payload.get("type", current_record["type"]),
                "category": payload.get("category", current_record["category"]),
                "entry_date": (
                    payload["date"].isoformat()
                    if payload.get("date")
                    else current_record["entry_date"]
                ),
                "notes": payload.get("notes", current_record["notes"]),
                "updated_by": actor_user_id,
                "updated_at": utcnow(),
                "id": record_id,
            }
            connection.execute(
                """
                UPDATE financial_records
                SET amount_cents = :amount_cents,
                    type = :type,
                    category = :category,
                    entry_date = :entry_date,
                    notes = :notes,
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                updated_values,
            )
            updated_record = self._fetch_record(connection, record_id)
            connection.commit()
            return serialize_record(updated_record)

    def delete_record(self, record_id: str, actor_user_id: str) -> Dict[str, Any]:
        with connect(self.database_path) as connection:
            record = self._fetch_record(connection, record_id, include_deleted=True)
            if record["is_deleted"]:
                raise AppError(409, "already_deleted", "This record is already deleted.")

            connection.execute(
                """
                UPDATE financial_records
                SET is_deleted = 1, updated_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (actor_user_id, utcnow(), record_id),
            )
            deleted_record = self._fetch_record(connection, record_id, include_deleted=True)
            connection.commit()
            return {
                "message": "Record deleted successfully.",
                "record": serialize_record(deleted_record),
            }

    def _fetch_record(
        self,
        connection: sqlite3.Connection,
        record_id: str,
        include_deleted: bool = False,
    ) -> sqlite3.Row:
        where_clause = "fr.id = ?"
        if not include_deleted:
            where_clause += " AND fr.is_deleted = 0"

        row = connection.execute(
            """
            SELECT
                fr.*,
                creator.name AS created_by_name,
                updater.name AS updated_by_name
            FROM financial_records fr
            LEFT JOIN users creator ON creator.id = fr.created_by
            LEFT JOIN users updater ON updater.id = fr.updated_by
            WHERE {where_clause}
            """.format(where_clause=where_clause),
            (record_id,),
        ).fetchone()
        if row is None:
            raise AppError(404, "record_not_found", "Financial record not found.")
        return row


def build_record_filters(filters: Dict[str, Any], alias: str = "fr") -> Tuple[str, List[Any]]:
    conditions = ["{alias}.is_deleted = 0".format(alias=alias)]
    parameters: List[Any] = []

    if filters.get("type"):
        conditions.append("{alias}.type = ?".format(alias=alias))
        parameters.append(filters["type"])
    if filters.get("category"):
        conditions.append("lower({alias}.category) = lower(?)".format(alias=alias))
        parameters.append(filters["category"])
    if filters.get("start_date"):
        conditions.append("{alias}.entry_date >= ?".format(alias=alias))
        parameters.append(filters["start_date"].isoformat())
    if filters.get("end_date"):
        conditions.append("{alias}.entry_date <= ?".format(alias=alias))
        parameters.append(filters["end_date"].isoformat())
    if filters.get("q"):
        conditions.append(
            "(lower({alias}.category) LIKE ? OR lower(COALESCE({alias}.notes, '')) LIKE ?)".format(
                alias=alias
            )
        )
        search_term = "%{term}%".format(term=filters["q"].lower())
        parameters.extend([search_term, search_term])

    return " AND ".join(conditions), parameters
