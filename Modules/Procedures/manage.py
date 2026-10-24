"""Interactive entry point for database interaction (importing and exporting records)."""

# standard library packages (Python-native)
import inspect, json, os, sys
from pathlib import Path

# Add the project root to Python's import search path.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

# local imports
from main import token, validate_personal_access_token
from Modules import database, search, state
from Modules.Procedures import procedures
from Utils import menus, writeToFile, dataTransformations as transform


# network-related procedures that require a GitHub Personal Access Token to function
token_required = {
    "expand_database"
}

def load_user_records(file_path: str | Path, database_path: str | Path = database.DATABASE_PATH) -> int:
	"""Import new users from a database export JSON file."""
	return procedures.load_user_records(file_path, database_path)

def export_all_user_records() -> str:
	"""Export all database users to JSON."""
	return procedures.export_all_user_records()

def write_user_records_to_excel(database_path: str | Path = database.DATABASE_PATH) -> str:
	"""Export all stored user records to an Excel workbook."""
	user_records = database.get_all_user_records(database_path)
	excel_records = [
		{
			key: sorted(value) if isinstance(value, set) else value
			for key, value in user.items()
		}
		for user in user_records
	]
	previous_outfile_title = state.outfile_title
	state.outfile_title = f"_DB_Export_{len(excel_records)}_Users"
	try:
		return writeToFile.write_to_excel(
			excel_records,
			user_records=excel_records,
		)
	finally:
		state.outfile_title = previous_outfile_title

def normalize_user_records(database_path: str | Path = database.DATABASE_PATH) -> int:
	"""Rebuild the users table using the exact-search record schema and field order."""
	return database.normalize_user_table(database_path)

def expand_database(token: str = token) -> int:
    """Fetch missing related users for scores >= 10, using the loaded token by default."""
    if not isinstance(token, str) or not token.strip():
        raise ValueError("A GitHub Personal Access Token is required.")
    
    # retrieve all user records from the database to identify missing relationship logins
    user_records = database.get_all_user_records()
    
    # extract all recorded logins from the user records
    recorded_logins = {
        login.strip().casefold()
        for user in user_records
        if isinstance((login := user.get("login")), str) and login.strip()
    }
    
    # extract all peripheral logins related to users with a composite score ≥ 10 (tradeoff that mitigates low-risk graph expansion)
    related_logins = {
        login.strip().casefold()
        for user in user_records
        if user.get("composite_score") >= 10
        for login in (user.get("relationships") or {})
        if isinstance(login, str) and login.strip()
    }
    
    # build targets list from related logins that do not have corresponding records (unfetched)
    target_logins = related_logins - recorded_logins
    if not target_logins:
        print("No missing relationship logins found.")
        return 0
    
    # fetch and persist the missing relationship logins
    print(f"Fetching {len(target_logins)} missing relationship logins at depth 0.")
    fetched_records, _ = search.user_search_exact(token, target_logins, recursions=0)
    return len(fetched_records)

def score_users(database_path: str | Path = database.DATABASE_PATH) -> int:
	"""Score all stored users and save the updated records to the database."""
	user_records = database.get_all_user_records(database_path)
	if not user_records:
		return 0
	scored_records = transform.scoring_battery(user_records)
	return database.store_user_records(scored_records, database_path)

def validate_users(database_path: str | Path = database.DATABASE_PATH) -> dict[str, int | float | None]:
    """Calculate validation metrics for stored users without updating the database."""
    user_records = database.get_all_user_records(database_path)
    return transform.validation_email_metrics(user_records)

def validate_users_by_alpha(database_path: str | Path = database.DATABASE_PATH) -> dict[float, dict[str, int | float | None]]:
    """Exists solely to determine ideal alpha value for graph development."""
    user_records = database.get_all_user_records(database_path)
    return transform.validation_metrics_by_alpha(user_records)

def _run_function_prompt() -> None:
    """Prompt for a function name and optional JSON arguments, then invoke it."""
    available_functions = { # lists all functions declared in this module
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
        
        # check if the function requires a personal access token
        elif function_name in token_required:
            # test if personal access token is valid
            is_valid, message = validate_personal_access_token(token)
            if not is_valid:
                print(message)
                menus.quit_program()
        
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