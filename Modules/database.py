import sqlite3, json
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

import config


DATABASE_PATH = Path(__file__).resolve().parent.parent / "github_vigilante.sqlite3"

# define the set of alpha values used for pagerank calculations
_ALPHAS = tuple(sorted(set(config.graph_pagerank_alphas) | {config.graph_pagerank_alpha}))

# define user table schema
_USER_COLUMN_DEFINITIONS = [
    ("login", "TEXT PRIMARY KEY COLLATE NOCASE"),
    ("graph_score", "REAL NOT NULL"),
    ("substring_score", "REAL NOT NULL"),
    ("composite_score", "REAL NOT NULL"),
    ("emails", "TEXT NOT NULL"),
    ("name", "TEXT"),
    ("socialAccounts", "TEXT NOT NULL"),
    ("relationships", "TEXT NOT NULL"),
    ("organizations", "TEXT NOT NULL"),
    ("org_count", "INTEGER"),
    ("company", "TEXT"),
    ("location", "TEXT"),
    ("bio", "TEXT"),
    ("createdAt", "TEXT"),
    ("updatedAt", "TEXT"),
    ("timestompedCommits", "INTEGER NOT NULL"),
    ("isFollowBotter", "INTEGER NOT NULL"),
    ("substring_matches", "INTEGER NOT NULL"),
    ("starred_users", "TEXT NOT NULL"),
]

# define pagerank-related columns for each alpha value
_USER_COLUMN_DEFINITIONS.extend(
    (f"pagerank_alpha_{alpha:g}", "REAL NOT NULL")
    for alpha in _ALPHAS
)

# define tuples for user columns, JSON fields, set fields, and boolean fields
_USER_COLUMNS = tuple(name for name, _ in _USER_COLUMN_DEFINITIONS)
_JSON_FIELDS = {"emails", "socialAccounts", "relationships", "organizations", "starred_users"}
_SET_FIELDS = {"emails", "socialAccounts"}
_BOOL_FIELDS = {"timestompedCommits", "isFollowBotter"}

# define default values for user fields, omitted columns default to None
_DEFAULTS: dict[str, Any] = {
    "graph_score": 0.0,
    "substring_score": 0.0,
    "composite_score": 0.0,
    "emails": [],
    "socialAccounts": [],
    "relationships": {},
    "organizations": [],
    "org_count": 0,
    "timestompedCommits": False,
    "isFollowBotter": False,
    "substring_matches": 0,
    "starred_users": {},
}

# define default values for each alpha value's PageRank column
for _alpha in _ALPHAS:
    _DEFAULTS[f"pagerank_alpha_{_alpha:g}"] = 0.0

# ensures safe quoting of SQL identifiers
def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'

def _create_users_table_sql(table_name: str = "users") -> str:
    """Generate the SQL statement to create the users table."""
    columns = ",\n    ".join(
        f"{_quote_identifier(name)} {column_type}"
        for name, column_type in _USER_COLUMN_DEFINITIONS
    )
    return f"CREATE TABLE IF NOT EXISTS {_quote_identifier(table_name)} (\n    {columns}\n)"

def _upsert_user_sql(table_name: str = "users") -> str:
    """Generate the SQL statement to upsert a user record."""
    columns = ", ".join(_quote_identifier(name) for name in _USER_COLUMNS)
    placeholders = ", ".join("?" for _ in _USER_COLUMNS)
    updates = ", ".join(
        f"{_quote_identifier(name)} = excluded.{_quote_identifier(name)}"
        for name in _USER_COLUMNS
        if name != "login"
    )
    return (
        f"INSERT INTO {_quote_identifier(table_name)} ({columns}) "
        f"VALUES ({placeholders}) ON CONFLICT({_quote_identifier('login')}) "
        f"DO UPDATE SET {updates}"
    )

# pre-generated SQL statements for creating and upserting user records
_CREATE_USERS_TABLE = _create_users_table_sql()
_UPSERT_USER = _upsert_user_sql()

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
    
    values = []
    for column in _USER_COLUMNS:
        if column == "composite_score" and column not in user and "score" in user:
            value = user["score"]
        else:
            value = user.get(column, _DEFAULTS.get(column))
        if column in _JSON_FIELDS:
            value = _json_text(_DEFAULTS[column] if value is None else value)
        elif column in _BOOL_FIELDS:
            value = int(bool(value))
        values.append(login.strip() if column == "login" else value)
    return tuple(values)

def get_user_record(
    login: str,
    database_path: str | Path = DATABASE_PATH,
) -> dict[str, Any] | None:
    """Load a previously stored complete user record, restoring JSON fields."""
    if not isinstance(login, str) or not login.strip():
        return None
    
    # ensure the database file exists before attempting to connect
    path = Path(database_path)
    if not path.is_file():
        return None
    
    connection = sqlite3.connect(path)
    
    # ensure the connection is properly closed after use
    with closing(connection) as conn:
        conn.row_factory = sqlite3.Row
        
        # fetch the user row matching the given login
        row = conn.execute("SELECT * FROM users WHERE login = ?", (login.strip(),),).fetchone()
    
    if row is None:
        return None
    
    return _user_record_from_row(row)

def _user_record_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """Restore a row in the canonical exact-search field order."""
    row_columns = set(row.keys())
    record = {}
    
    # iterate over the canonical user columns to build the record in order
    for column in _USER_COLUMNS:
        if column in row_columns:
            value = row[column]
        
        # if the column exists in the row, use its value
        elif column == "composite_score" and "score" in row_columns:
            value = row["score"]
        
        # if it doesn't exist, use the default value
        else:
            value = _DEFAULTS.get(column)
        
        # restore JSON fields to their original types
        if column in _JSON_FIELDS:
            if isinstance(value, str):
                value = json.loads(value)
            
            # if None, use the default value for this column
            elif value is None:
                value = _DEFAULTS[column]
            
            # restore set fields to their original types
            if column in _SET_FIELDS:
                value = set(value or [])
        
        # restore boolean fields to their original types
        elif column in _BOOL_FIELDS:
            value = bool(value)
        
        # assign the final value to the record for this column
        record[column] = value
    
    return record

def get_all_user_records(database_path: str | Path = DATABASE_PATH) -> list[dict[str, Any]]:
    """Load all stored user records, restoring their JSON fields."""
    path = Path(database_path)
    if not path.is_file():
        return []
    
    # check if the database file exists before attempting to connect
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        
        # create a cursor to fetch all user rows from the database
        with closing(connection.cursor()) as cursor:
            rows = cursor.execute("SELECT * FROM users ORDER BY login COLLATE NOCASE").fetchall()
    
    return [_user_record_from_row(row) for row in rows]


def normalize_user_table(database_path: str | Path = DATABASE_PATH) -> int:
    """Rebuild the users table in canonical exact-search field order."""
    temporary_table = "users_normalized_tmp"
    
    # connect to the database and begin normalizing the users table
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        
        try:
            # check if the users table exists in the database
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
            ).fetchone() is not None
            
            # fetch all existing user rows if the table exists
            rows = connection.execute("SELECT * FROM users").fetchall() if table_exists else []
            
            # convert the fetched rows into normalized user records
            records = [_user_record_from_row(row) for row in rows]
            
            # convert the normalized records into row values suitable for insertion
            values = [
                row
                for record in records
                if (row := _user_values(record)) is not None
            ]
            
            # drop the temporary table if it exists to start fresh.
            connection.execute(f"DROP TABLE IF EXISTS {_quote_identifier(temporary_table)}")
            
            # create the temporary normalized users table
            connection.execute(_create_users_table_sql(temporary_table))
            
            # insert the normalized user records into the temporary table
            connection.executemany(_upsert_user_sql(temporary_table), values)
            
            # drop the original users table if it exists before renaming the temporary table
            if table_exists:
                connection.execute("DROP TABLE users")
            
            # rename the temporary table to users
            connection.execute(f"ALTER TABLE {_quote_identifier(temporary_table)} RENAME TO users")
            connection.commit()
        
        # rollback the transaction if any exception occurs
        except Exception:
            connection.rollback()
            raise
    
    return len(values)


def _ensure_users_table_schema(database_path: str | Path) -> None:
    """Ensure the users table schema matches the expected columns."""
    with closing(sqlite3.connect(database_path)) as connection:
        # check if the users table exists, otherwise normalization is not necessary
        table_exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone() is not None
        if not table_exists:
            return
        
        # get the column names of the users table
        columns = tuple(row[1] for row in connection.execute("PRAGMA table_info(users)"))
	
    # if the columns do not match the expected schema, normalize the users table
    if columns != _USER_COLUMNS:
        normalize_user_table(database_path)

def store_user_records(records: Iterable[dict[str, Any]], database_path: str | Path = DATABASE_PATH) -> int:
    """Create or update user rows and return the number of rows processed."""
    _ensure_users_table_schema(database_path) # check if the users table schema is up-to-date and normalize if necessary
    values = [
        row
        for record in records
        if record.get("membership") != "N/A"
        if (row := _user_values(record)) is not None
    ]
    
    # open a connection to the database and store the user records
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(_CREATE_USERS_TABLE)
            connection.executemany(_UPSERT_USER, values)
    
    return len(values)