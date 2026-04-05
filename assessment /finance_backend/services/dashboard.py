"""Dashboard aggregations used by the frontend."""

from datetime import date, timedelta
from typing import Any, Dict, List

from ..db import connect
from .common import amount_from_cents, serialize_record


class DashboardService:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path

    def get_summary(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        where_clause, parameters = build_summary_filters(filters)

        with connect(self.database_path) as connection:
            totals_row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN fr.type = 'income' THEN fr.amount_cents ELSE 0 END), 0) AS income_cents,
                    COALESCE(SUM(CASE WHEN fr.type = 'expense' THEN fr.amount_cents ELSE 0 END), 0) AS expense_cents,
                    COUNT(*) AS record_count
                FROM financial_records fr
                WHERE {where_clause}
                """.format(where_clause=where_clause),
                parameters,
            ).fetchone()

            category_rows = connection.execute(
                """
                SELECT
                    fr.category,
                    fr.type,
                    SUM(fr.amount_cents) AS total_cents,
                    COUNT(*) AS record_count
                FROM financial_records fr
                WHERE {where_clause}
                GROUP BY fr.category, fr.type
                ORDER BY total_cents DESC, fr.category ASC
                """.format(where_clause=where_clause),
                parameters,
            ).fetchall()

            recent_rows = connection.execute(
                """
                SELECT
                    fr.*,
                    creator.name AS created_by_name,
                    updater.name AS updated_by_name
                FROM financial_records fr
                LEFT JOIN users creator ON creator.id = fr.created_by
                LEFT JOIN users updater ON updater.id = fr.updated_by
                WHERE {where_clause}
                ORDER BY fr.entry_date DESC, fr.updated_at DESC
                LIMIT ?
                """.format(where_clause=where_clause),
                parameters + [filters["recent_limit"]],
            ).fetchall()

        income_cents = int(totals_row["income_cents"])
        expense_cents = int(totals_row["expense_cents"])
        return {
            "totals": {
                "income": amount_from_cents(income_cents),
                "expenses": amount_from_cents(expense_cents),
                "net_balance": amount_from_cents(income_cents - expense_cents),
                "record_count": int(totals_row["record_count"]),
            },
            "category_totals": [
                {
                    "category": row["category"],
                    "type": row["type"],
                    "total": amount_from_cents(int(row["total_cents"])),
                    "record_count": int(row["record_count"]),
                }
                for row in category_rows
            ],
            "recent_activity": [serialize_record(row) for row in recent_rows],
            "filters": {
                "start_date": filters.get("start_date"),
                "end_date": filters.get("end_date"),
            },
        }

    def get_trends(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        granularity = filters["granularity"]
        periods = filters["periods"]
        end_date = filters.get("end_date") or date.today()
        bucket_starts = build_bucket_starts(granularity, end_date, periods)
        first_bucket_start = bucket_starts[0]

        conditions = ["is_deleted = 0", "entry_date >= ?", "entry_date <= ?"]
        parameters: List[Any] = [first_bucket_start.isoformat(), end_date.isoformat()]
        if filters.get("category"):
            conditions.append("lower(category) = lower(?)")
            parameters.append(filters["category"])

        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT entry_date, type, amount_cents
                FROM financial_records
                WHERE {where_clause}
                ORDER BY entry_date ASC
                """.format(where_clause=" AND ".join(conditions)),
                parameters,
            ).fetchall()

        buckets = {
            bucket_label(bucket_start, granularity): {
                "period_start": bucket_start.isoformat(),
                "period_label": bucket_label(bucket_start, granularity),
                "income_cents": 0,
                "expense_cents": 0,
                "record_count": 0,
            }
            for bucket_start in bucket_starts
        }

        for row in rows:
            entry_date = date.fromisoformat(row["entry_date"])
            label = bucket_label(normalize_period_start(entry_date, granularity), granularity)
            if label not in buckets:
                continue
            if row["type"] == "income":
                buckets[label]["income_cents"] += int(row["amount_cents"])
            else:
                buckets[label]["expense_cents"] += int(row["amount_cents"])
            buckets[label]["record_count"] += 1

        points = []
        for bucket_start in bucket_starts:
            label = bucket_label(bucket_start, granularity)
            bucket = buckets[label]
            points.append(
                {
                    "period_start": bucket["period_start"],
                    "period_label": bucket["period_label"],
                    "income": amount_from_cents(bucket["income_cents"]),
                    "expenses": amount_from_cents(bucket["expense_cents"]),
                    "net_balance": amount_from_cents(
                        bucket["income_cents"] - bucket["expense_cents"]
                    ),
                    "record_count": bucket["record_count"],
                }
            )

        return {
            "granularity": granularity,
            "range": {
                "start_date": first_bucket_start,
                "end_date": end_date,
            },
            "points": points,
        }


def build_summary_filters(filters: Dict[str, Any]) -> tuple[str, List[Any]]:
    conditions = ["fr.is_deleted = 0"]
    parameters: List[Any] = []

    if filters.get("start_date"):
        conditions.append("fr.entry_date >= ?")
        parameters.append(filters["start_date"].isoformat())
    if filters.get("end_date"):
        conditions.append("fr.entry_date <= ?")
        parameters.append(filters["end_date"].isoformat())

    return " AND ".join(conditions), parameters


def build_bucket_starts(granularity: str, end_date: date, periods: int) -> List[date]:
    bucket_starts: List[date] = []
    current = normalize_period_start(end_date, granularity)
    for _ in range(periods):
        bucket_starts.append(current)
        current = previous_period_start(current, granularity)
    bucket_starts.reverse()
    return bucket_starts


def normalize_period_start(value: date, granularity: str) -> date:
    if granularity == "weekly":
        return value - timedelta(days=value.weekday())
    return value.replace(day=1)


def previous_period_start(value: date, granularity: str) -> date:
    if granularity == "weekly":
        return value - timedelta(days=7)
    if value.month == 1:
        return value.replace(year=value.year - 1, month=12, day=1)
    return value.replace(month=value.month - 1, day=1)


def bucket_label(value: date, granularity: str) -> str:
    if granularity == "weekly":
        iso_year, iso_week, _ = value.isocalendar()
        return "{year}-W{week:02d}".format(year=iso_year, week=iso_week)
    return value.strftime("%Y-%m")
