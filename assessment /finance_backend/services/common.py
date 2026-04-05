"""Shared helpers used across service classes."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
import sqlite3


TWOPLACES = Decimal("0.01")


def cents_from_decimal(amount: Decimal) -> int:
    quantized = amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return int((quantized * 100).to_integral_value())


def amount_from_cents(amount_cents: int) -> str:
    amount = (Decimal(amount_cents) / Decimal("100")).quantize(TWOPLACES)
    return format(amount, ".2f")


def serialize_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def serialize_record(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "amount": amount_from_cents(row["amount_cents"]),
        "type": row["type"],
        "category": row["category"],
        "date": row["entry_date"],
        "notes": row["notes"],
        "is_deleted": bool(row["is_deleted"]),
        "created_by": {
            "id": row["created_by"],
            "name": row["created_by_name"],
        },
        "updated_by": {
            "id": row["updated_by"],
            "name": row["updated_by_name"],
        },
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
