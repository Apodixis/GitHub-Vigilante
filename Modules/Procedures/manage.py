"""Interactive entry point for database interaction (importing and exporting records)."""

# standard library packages (Python-native)
import inspect, json, os, sys
from pathlib import Path

# third-party packages
from sklearn.metrics import average_precision_score

# Add the project root to Python's import search path.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

# local imports
import config
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
    """Fetch missing related users for scores >= 10, then rescore all stored users."""
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
    score_users() # Scores all stored users after fetching additional related logins
    return len(fetched_records)

def score_users(database_path: str | Path = database.DATABASE_PATH) -> int:
	"""Score all stored users and save the updated records to the database."""
	user_records = database.get_all_user_records(database_path)
	if not user_records:
		return 0
	scored_records = transform.scoring_battery(user_records)
	return database.store_user_records(scored_records, database_path)

def validate_users(database_path: str | Path = database.DATABASE_PATH) -> dict[str, int | float | None]:
    """Evaluate stored scores against held-out labels without updating the database."""
    results = database.get_all_user_records(database_path)
    
    # Prepare sets of validation and blacklisted logins and emails for later comparison
    validation_logins = {
        login.strip().casefold()
        for login in config.VALIDATION_SET_LOGINS
        if isinstance(login, str) and login.strip()
    }
    blacklist_logins = {
        login.strip().casefold()
        for login in config.BAD_LOGINS
        if isinstance(login, str) and login.strip()
    }
    blacklist_emails = {
        email.strip().casefold()
        for email in config.BAD_EMAILS
        if isinstance(email, str) and email.strip()
    }
    
    # Remove any emails that are present in the blacklist (avoids validation test contamination)
    validation_emails = {
        email.strip().casefold()
        for email in config.VALIDATION_SET_EMAILS
        if isinstance(email, str) and email.strip()
    } - blacklist_emails
    
    # If there are no validation logins or emails, return early with zeroed metrics
    if not (validation_logins or validation_emails):
        return {
            "validation_emails_total": 0,
            "validation_emails_found": 0,
            "validation_email_coverage": None,
            "validation_logins_total": 0,
            "validation_logins_found": 0,
            "validation_positive_accounts_found": 0,
            "validation_average_precision": None,
            "validation_recall_k": 0,
            "validation_recall_at_k": None,
            "validation_mean_reciprocal_rank": None,
            "validation_average_rank": None,
        }
    
    # Index users by their login for quick lookup
    users_by_login = {}
    for user in results:
        login = user.get("login")
        if isinstance(login, str) and login.strip():
            users_by_login[login.casefold()] = user
    
    # Initialize candidate list and sets to track found emails and logins
    candidates = []
    found_emails = set()
    found_logins = set()
    
    # Iterate over each user and process their emails and validation status
    for login, user in users_by_login.items():
        raw_emails = user.get("emails") or []
        if isinstance(raw_emails, str):
            raw_emails = [raw_emails]
        
        # Normalize and clean up the user's email addresses
        user_emails = {
            email.strip().casefold()
            for email in raw_emails
            if isinstance(email, str) and email.strip()
        }
        
        # Identify which of the user's emails are in the validation set
        matched_emails = user_emails & validation_emails
        found_emails.update(matched_emails)
        
        # Determine if the user's login matches the validation set
        if login in validation_logins:
            found_logins.add(login)
        
        # Retrieve the composite score for the user
        score = user.get("composite_score", 0.0)
        if not isinstance(score, (int, float)):
            score = 0.0
        
        # Determine if the account is a validation account
        is_validation_account = login in validation_logins or bool(matched_emails)
        
        # Retrieve the graph score for the user
        graph_score = user.get("graph_score", 0.0)
        
        # Skip blacklisted accounts
        if login in blacklist_logins or user_emails.intersection(blacklist_emails):
            continue
        
        # Skip out-of-network validation accounts
        if is_validation_account and graph_score == 0:
            continue
        
        candidates.append((login, float(score), matched_emails, is_validation_account))
    
    # Extract labels and scores for validation accounts
    labels = [is_validation_account for _, _, _, is_validation_account in candidates]
    scores = [score for _, score, _, _ in candidates]
    
    # Calculate the average precision for validation accounts
    average_precision = (
        average_precision_score(labels, scores)
        if any(labels) and not all(labels)
        else None
    )
    
    # Rank candidates by score (descending) and login (ascending)
    ranked_candidates = sorted(candidates, key=lambda item: (-item[1], item[0]))
    
    # Extract the top-k candidates based on the number of relevant accounts
    relevant_account_count = sum(labels)
    top_k = ranked_candidates[:relevant_account_count]
    
    # Determine the ranks of validation accounts in the sorted candidate list
    validation_ranks = [
        rank
        for rank, candidate in enumerate(ranked_candidates, start=1)
        if candidate[3]
    ]
    
    # Calculate the average rank of validation accounts
    average_rank = (
        sum(validation_ranks) / relevant_account_count
        if relevant_account_count
        else None
    )
    
    # Calculate the mean reciprocal rank of validation accounts
    reciprocal_rank_total = sum(1 / rank for rank in validation_ranks)
    mean_reciprocal_rank = (
        reciprocal_rank_total / relevant_account_count
        if relevant_account_count
        else None
    )
    
    # Return a dictionary of evaluation metrics for the validation accounts
    return {
        "validation_emails_total": len(validation_emails),
        "validation_emails_found": len(found_emails),
        "validation_email_coverage": (
            len(found_emails) / len(validation_emails) if validation_emails else None
        ),
        "validation_logins_total": len(validation_logins),
        "validation_logins_found": len(found_logins),
        "validation_positive_accounts_found": relevant_account_count,
        "validation_average_precision": average_precision,
        "validation_recall_k": relevant_account_count,
        "validation_recall_at_k": (
            sum(candidate[3] for candidate in top_k) / relevant_account_count
            if relevant_account_count
            else None
        ),
        "validation_mean_reciprocal_rank": mean_reciprocal_rank,
        "validation_average_rank": average_rank,
    }

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