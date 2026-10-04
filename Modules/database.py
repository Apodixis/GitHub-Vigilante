import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


DATABASE_PATH = Path(__file__).resolve().parent.parent / "github_vigilante.sqlite3"

# creates a user table if missing and defines schema
_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    login TEXT PRIMARY KEY COLLATE NOCASE,
    score REAL,
    emails TEXT NOT NULL,
    socialAccounts TEXT NOT NULL,
    name TEXT,
    relationships TEXT NOT NULL,
    starred_users TEXT NOT NULL,
    organizations TEXT NOT NULL,
    org_count INTEGER,
    company TEXT,
    location TEXT,
    bio TEXT,
    createdAt TEXT,
    updatedAt TEXT,
    timestompedCommits INTEGER NOT NULL
)
"""

# inserts user record data or updates existing records if an existing record is present in the database
_UPSERT_USER = """
INSERT INTO users (
    login, score, emails, socialAccounts, name, relationships, starred_users,
    organizations, org_count, company, location, bio, createdAt, updatedAt,
    timestompedCommits
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(login) DO UPDATE SET
    score = excluded.score,
    emails = excluded.emails,
    socialAccounts = excluded.socialAccounts,
    name = excluded.name,
    relationships = excluded.relationships,
    starred_users = excluded.starred_users,
    organizations = excluded.organizations,
    org_count = excluded.org_count,
    company = excluded.company,
    location = excluded.location,
    bio = excluded.bio,
    createdAt = excluded.createdAt,
    updatedAt = excluded.updatedAt,
    timestompedCommits = excluded.timestompedCommits
"""

def _json_text(value: Any) -> str:
    """Convert a value to a JSON-formatted string. Handles sets by sorting them first."""
    if isinstance(value, set):
        value = sorted(value)
    return json.dumps(value, sort_keys=True)

def _user_values(user: dict[str, Any]) -> tuple[Any, ...] | None:
    """Extracts and formats user data for database insertion"""
    login = user.get("login")
    if not isinstance(login, str) or not login.strip():
        return None
    
    return (
        login.strip(),
        user.get("score"),
        _json_text(user.get("emails") or []),
        _json_text(user.get("socialAccounts") or []),
        user.get("name"),
        _json_text(user.get("relationships") or {}),
        _json_text(user.get("starred_users") or {}),
        _json_text(user.get("organizations") or []),
        user.get("org_count"),
        user.get("company"),
        user.get("location"),
        user.get("bio"),
        user.get("createdAt"),
        user.get("updatedAt"),
        int(bool(user.get("timestompedCommits", False))),
    )

def get_user_record(
    login: str,
    database_path: str | Path = DATABASE_PATH,
) -> dict[str, Any] | None:
    """Load a previously stored complete user record, restoring JSON fields."""
    if not isinstance(login, str) or not login.strip():
        return None
    
    path = Path(database_path)
    if not path.is_file():
        return None
    
    connection = sqlite3.connect(path)
    try:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM users WHERE login = ?",
            (login.strip(),),
        ).fetchone()
    finally:
        connection.close()
    
    if row is None:
        return None
    
    return {
        "login": row["login"],
        "score": row["score"],
        "emails": set(json.loads(row["emails"])),
        "socialAccounts": set(json.loads(row["socialAccounts"])),
        "name": row["name"],
        "relationships": json.loads(row["relationships"]),
        "starred_users": json.loads(row["starred_users"]),
        "organizations": json.loads(row["organizations"]),
        "org_count": row["org_count"],
        "company": row["company"],
        "location": row["location"],
        "bio": row["bio"],
        "createdAt": row["createdAt"],
        "updatedAt": row["updatedAt"],
        "timestompedCommits": bool(row["timestompedCommits"]),
    }

def store_user_records(
    records: Iterable[dict[str, Any]],
    database_path: str | Path = DATABASE_PATH,
) -> int:
    """Create or update user rows and return the number of rows processed."""
    values = [
        row
        for record in records
        if "starred_users" in record
        if record.get("membership") != "N/A"
        if (row := _user_values(record)) is not None
    ]
    
    with sqlite3.connect(database_path) as connection:
        connection.execute(_CREATE_USERS_TABLE)
        connection.executemany(_UPSERT_USER, values)
    
    return len(values)