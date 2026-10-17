"""Interactive entry point for database interaction (importing and exporting records)."""

import inspect, json, sys
from pathlib import Path

# Add the project root to Python's import search path.
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
	sys.path.insert(0, str(project_root))

import Modules.database as database
import Modules.Procedures.procedures as procedures
import Utils.dataTransformations as transform


def load_user_records(
	file_path: str | Path,
	database_path: str | Path = database.DATABASE_PATH,
) -> int:
	"""Import new users from a database export JSON file."""
	return procedures.load_user_records(file_path, database_path)

def export_all_user_records() -> str:
	"""Export all database users to JSON."""
	return procedures.export_all_user_records()

def normalize_user_records(
	database_path: str | Path = database.DATABASE_PATH,
) -> int:
	"""Rebuild the users table using the exact-search record schema and field order."""
	return database.normalize_user_table(database_path)

def score_users(database_path: str | Path = database.DATABASE_PATH) -> int:
	"""Score all stored users and save the updated records to the database."""
	user_records = database.get_all_user_records(database_path)
	if not user_records:
		return 0
	scored_records = transform.scoring_battery(user_records)
	return database.store_user_records(scored_records, database_path)

def _run_function_prompt() -> None:
	"""Prompt for a function name and optional JSON arguments, then invoke it."""
	available_functions = { # lists all function declared in this module
		name: function
		for name, function in globals().items()
		if not name.startswith("_")
		and inspect.isfunction(function)
		and function.__module__ == __name__
	}
	print("Available functions:")
	for name in available_functions:
		print(f"  {name}")
	
	# function call loop
	while True:
		function_name = input("Function name (or 'exit'): ").strip()
		if function_name.lower() in {"exit", "quit"}:
			return
		
		function = available_functions.get(function_name)
		if function is None:
			print(f"Unknown function: {function_name}")
			continue
		
		arguments_text = input("Arguments as JSON (blank for none): ").strip()
		
		# parse JSON arguments for the function call
		try:
			arguments = json.loads(arguments_text) if arguments_text else []
			
			if isinstance(arguments, list):
				result = function(*arguments)
			elif isinstance(arguments, dict):
				result = function(**arguments)
			else:
				print("Arguments must be a JSON array or object.")
				continue
			
			print(f"Result: {result!r}")
		
		except Exception as error:
			print(f"Call failed: {error}")

if __name__ == "__main__":
	_run_function_prompt()