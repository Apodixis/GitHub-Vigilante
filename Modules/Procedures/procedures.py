"""Provide user-record database and Excel import/export workflows."""

import ast, openpyxl
from contextlib import closing
from pathlib import Path
from typing import Any

import Modules.database as database
import Modules.state as state
import Utils.writeToFile as writeToFile


def get_all_user_records(
	database_path: str | Path = database.DATABASE_PATH,
) -> list[dict[str, Any]]:
	"""Return all stored users in the application's user-record format."""
	return database.get_all_user_records(database_path)

def load_user_records(
	file_path: str | Path,
	database_path: str | Path = database.DATABASE_PATH,
) -> int:
	"""Insert users from a search-format workbook if their logins are not stored."""
	with closing(openpyxl.load_workbook(file_path, read_only=True, data_only=True)) as workbook:
		worksheet = workbook.active
		rows = worksheet.iter_rows(values_only=True)
		header_row = next(rows, None)
		if not header_row:
			return 0
		headers = {
			str(value): index
			for index, value in enumerate(header_row)
			if value is not None
		}
		if "login" not in headers:
			raise ValueError("Excel worksheet must include a 'login' column.")
		
		new_records = []
		seen_logins = set()
		for row in rows:
			record = {
				name: row[index]
				for name, index in headers.items()
				if index < len(row)
			}
			
			login = record.get("login")
			if not isinstance(login, str) or not login.strip():
				continue
			
			login = login.strip()
			login_key = login.casefold()
			if login_key in seen_logins:
				continue
			seen_logins.add(login_key)
			record["login"] = login
			
			for field in ("emails", "socialAccounts", "organizations"):
				value = record.get(field)
				items = value if isinstance(value, (list, tuple, set)) else str(value or "").split(",")
				items = [item.strip() for item in items if str(item).strip()]
				record[field] = set(items) if field != "organizations" else items
			
			for field in ("relationships", "starred_users"):
				value = record.get(field)
				if isinstance(value, str) and value.strip():
					try:
						value = ast.literal_eval(value)
					except (SyntaxError, ValueError):
						value = {}
				record[field] = value if isinstance(value, dict) else {}
			
			value = record.get("timestompedCommits")
			if isinstance(value, str):
				record["timestompedCommits"] = value.strip().casefold() == "true"
			else:
				record["timestompedCommits"] = bool(value)
			
			new_records.append(record)
	
	# Ensure the table exists before checking current logins.
	database.store_user_records([], database_path)
	existing_logins = {
		record["login"].casefold()
		for record in database.get_all_user_records(database_path)
	}
	new_records = [
		record for record in new_records
		if record["login"].casefold() not in existing_logins
	]
	return database.store_user_records(new_records, database_path)

def export_all_user_records() -> str:
	"""Export all records from the users table to an Excel file."""
	user_records = database.get_all_user_records()
	state.outfile_title = f"_DB_Export_{len(user_records)}_Users"
	return writeToFile.write_to_excel(user_records)
