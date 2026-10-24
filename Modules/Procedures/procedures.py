"""Provide user-record database and Excel import/export workflows."""

# standard library packages (Python-native)
import json
from pathlib import Path
from typing import Any

# local imports
from Modules import database
from Utils import writeToFile


def get_all_user_records(database_path: str | Path = database.DATABASE_PATH) -> list[dict[str, Any]]:
	"""Return all stored users in the application's user-record format."""
	return database.get_all_user_records(database_path)

def load_user_records(file_path: str | Path, database_path: str | Path = database.DATABASE_PATH) -> int:
    """Insert users from a JSON export if their logins are not already present in the database."""
    with Path(file_path).open(encoding="utf-8") as input_file:
        records = json.load(input_file)
    
    if not isinstance(records, list):
        raise ValueError("JSON file must contain a list of user records.")
    
    # prepare a list to hold new records and a set to track seen logins
    new_records = []
    seen_logins = set()
    
    for record in records:
        if not isinstance(record, dict):
            continue
        
        login = record.get("login")
        if not isinstance(login, str) or not login.strip():
            continue
        
        login = login.strip()
        login_key = login.casefold()
        if login_key in seen_logins:
            continue
        
        # avoids duplicate operations by tracking seen logins
        seen_logins.add(login_key)
        record["login"] = login
        
        # record field value normalization
        for field in ("emails", "socialAccounts"):
            value = record.get(field) or []
            record[field] = set(value) if isinstance(value, (list, tuple, set)) else {value}
        
        record["relationships"] = record.get("relationships") if isinstance(record.get("relationships"), dict) else {}
        record["starred_users"] = record.get("starred_users") if isinstance(record.get("starred_users"), dict) else {}
        record["organizations"] = record.get("organizations") or []
        
        # normalize boolean fields to ensure consistent data types
        for field in ("timestompedCommits", "isFollowBotter"):
            value = record.get(field, False)
            
            if isinstance(value, str):
                value = value.strip().casefold() in {"true", "1", "yes"}
                
            record[field] = bool(value)
        # -- end of record field normalization
        
        new_records.append(record) # add record to the list of new records to be inserted
    
    # Ensure the table exists before checking current logins.
    database.store_user_records([], database_path)
    
    # fetch existing logins to avoid inserting duplicates
    existing_logins = {
        record["login"].casefold()
        for record in database.get_all_user_records(database_path)
    }
    
    # filter out records that already exist in the database
    new_records = [
        record for record in new_records
        if record["login"].casefold() not in existing_logins
    ]
    
    # insert the filtered new records into the database
    return database.store_user_records(new_records, database_path)

def export_all_user_records() -> str:
	"""Export all records from the users table to a JSON file."""
	user_records = database.get_all_user_records()
	file_title = f"_DB_Export_{len(user_records)}_Users"
	return writeToFile.write_to_json(user_records, file_title)
