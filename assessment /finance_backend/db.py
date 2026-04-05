from datetime import datetime, timezone
from uuid import uuid4
import sqlite3

from .security import ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER, hash_password


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('viewer', 'analyst', 'admin')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS financial_records (
    id TEXT PRIMARY KEY,
    amount_cents INTEGER NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
    category TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    notes TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (created_by) REFERENCES users(id),
    FOREIGN KEY (updated_by) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_records_date ON financial_records(entry_date);
CREATE INDEX IF NOT EXISTS idx_records_type ON financial_records(type);
CREATE INDEX IF NOT EXISTS idx_records_category ON financial_records(category);
CREATE INDEX IF NOT EXISTS idx_records_deleted ON financial_records(is_deleted);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: str) -> None:
    with connect(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()


def seed_demo_data(database_path: str) -> None:
    with connect(database_path) as connection:
        user_count = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if user_count:
            return

        now = utcnow()
        admin_id = str(uuid4())
        analyst_id = str(uuid4())
        viewer_id = str(uuid4())

        users = [
            (
                admin_id,
                "Admin User",
                "admin@finance.local",
                hash_password("AdminPass123!"),
                ROLE_ADMIN,
                1,
                now,
                now,
            ),
            (
                analyst_id,
                "Analyst User",
                "analyst@finance.local",
                hash_password("AnalystPass123!"),
                ROLE_ANALYST,
                1,
                now,
                now,
            ),
            (
                viewer_id,
                "Viewer User",
                "viewer@finance.local",
                hash_password("ViewerPass123!"),
                ROLE_VIEWER,
                1,
                now,
                now,
            ),
        ]
        connection.executemany(
            """
            INSERT INTO users (id, name, email, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            users,
        )

        demo_records = [
            ("650000", "income", "Salary", "2026-04-01", "Primary monthly salary"),
            ("120000", "income", "Freelance", "2026-03-15", "Website redesign invoice"),
            ("180000", "expense", "Rent", "2026-04-02", "Apartment rent"),
            ("25000", "expense", "Utilities", "2026-03-28", "Electricity and internet"),
            ("42050", "expense", "Groceries", "2026-04-03", "Weekly groceries"),
            ("90000", "income", "Investments", "2026-02-20", "Quarterly dividends"),
        ]
        records = []
        for amount_cents, record_type, category, entry_date, notes in demo_records:
            record_id = str(uuid4())
            records.append(
                (
                    record_id,
                    int(amount_cents),
                    record_type,
                    category,
                    entry_date,
                    notes,
                    0,
                    admin_id,
                    admin_id,
                    now,
                    now,
                )
            )
        connection.executemany(
            """
            INSERT INTO financial_records (
                id, amount_cents, type, category, entry_date, notes, is_deleted,
                created_by, updated_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        connection.commit()
