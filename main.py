# standard library packages (Python-native)
import os, time
from pathlib import Path

# local imports
from Modules import database, search, state
from Utils import menus, writeToFile, dataTransformations as transform

# third-party packages
import requests


#--------------------------------------------------------------------------------
## GITHUB PERSONAL ACCESS TOKEN DECLARATION

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv and ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)
elif not ENV_PATH.exists():
    print(f"[env] No .env file found at: {ENV_PATH}. Please create and update GITHUB_API_TOKEN with your GitHub Personal Access Token.")

# Always check existing environment token first
token = os.getenv("GITHUB_API_TOKEN")

# Fallback to prompt user for token if not found in environment variables
if not token:
    token = input("Enter your GitHub Personal Access Token: ").strip()

# Exit if token is still not populated
if not token:
    print("GitHub Personal Access Token is required to proceed.")
    menus.quit_program()

# Used in selection_menu() for enrichment determination
enrichment_options = [
    "Enrich Results: May take significantly longer",
    "Skip Enrichment"
    ]

# Used in exact and email-reverse searches to determine whether cached user data is reused.
cache_options = [
    "Use cached user data when available",
    "Ignore cached user data and fetch from GitHub"
    ]

## GITHUB PERSONAL ACCESS TOKEN DECLARATION
#--------------------------------------------------------------------------------
## PERSONAL ACCESS TOKEN TEST BLOCK

def validate_personal_access_token(token: str) -> tuple[bool, str]:
    """
    Input: GitHub Personal Access Token
    Output: Tuple (is_valid, message) indicating whether the token is valid and an associated message
    Method: REST API request with token authorization to confirm token validity
    """
    url = "https://api.github.com/user"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    
    print("Validating GitHub Personal Access Token...")
    
    try:
        r = requests.get(url, headers=headers, timeout=(3,10)) # 3s connect, 10s read timeout
    
    except requests.Timeout:
        return False, "Request timed out. Check your network connection."
    except requests.RequestException as e:
        return False, f"Network error occurred while validating token: {e}"
    
    # Handle HTTP response error status codes
    if r.status_code == 401:
        return False, "Token is invalid, expired, or revoked."
    if r.status_code == 403:
        return False, "Token rejected or rate-limited."
    if r.status_code != 200:
        return False, f"Token validation failed with status code {r.status_code}: {r.text[:200]}"
    
    # If the request is successful, store the authenticated user's login in the global state for later use
    state.authorized_login = r.json().get("login") # fetch authenticated user's login for use in constructing the user-agent string
    
    return True, "Token is valid."

## PERSONAL ACCESS TOKEN TEST BLOCK
#--------------------------------------------------------------------------------

def _decision_tree() -> int:
    menus.clear_terminal()
    
    print("1) User Search")
    print("2) Organization Search")
    print("3) Repository Search")
    print("4) Pivot Engine")
    
    while True:
        choice = input("Enter 1, 2, 3, or 4: ").strip()
        try:
            choice_int = int(choice)
            if choice_int not in range(1, 5):
                print("Invalid selection. Please enter 1, 2, 3, or 4.")
                continue
            
            else:
                return choice_int
        
        except ValueError:
            print("Invalid selection. Please enter 1, 2, 3, or 4.")

def _user_search(token) -> tuple[list[dict], list[str], list[str]]:
    '''
    Broadens target analysis by fetching followership, Organizations, and account metadata. Also returns noteworthy followers:
    1. Exact: Returns info on the input User(s) and their followership and stargazing relationships
    2. Partial: Returns info on all Users returned by the partial search query
    3. Email Reverse: Returns info on all Users associated with the input email(s) and their followership and stargazing relationships
    '''
    search_method = "User"
    
    # Initialize lists to store searched logins and emails
    searched_logins: list[str] = []
    searched_emails: list[str] = []
    
    # Prompt user to select the search mode (Exact, Partial, or Email Reverse)
    search_mode_options = [
        "User Search - Exact Match",
        "User Search - Partial Match",
        "User Search - Email Reverse Search"
        ]
    search_mode = menus.selection_menu(search_mode_options) # User Search Mode Selection
    # -- END OF SEARCH MODE SELECTION
    
    if search_mode in {"1", "3"}:
        cache_choice = menus.selection_menu(cache_options)
        state.use_user_cache = cache_choice == "1"
    
    menus.clear_terminal()
    
    if search_mode == "1": # User Search Exact
        targets = menus.multiple_input_prompt("User login") # user input menu
        
        # Store the searched logins for output summaries
        searched_logins = [targets] if isinstance(targets, str) else list(targets)
        
        menus.clear_terminal()
        
        search_method += "_Exact"
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        depth = menus.recursion_menu() # prompt user for desired recursion depth
        
        # fetch user data for the logins in targets
        user_data, target = search.user_search_exact(token, targets, depth)
    
    elif search_mode == "2": # User Search Partial
        search_method += "_Partial"
        while True:
            target_substring = input("Enter the user login substring to analyze: ").strip()
            if not target_substring:
                print(f"Enter a user login substring.")
                continue
            break
        
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        user_data, target = search.user_search_partial(token, target_substring)
    
    elif search_mode == "3": # User Search Email
        search_method += "_Email"
        targets = menus.multiple_input_prompt("Email") # email input menu
        
        # Store the searched emails for output summaries
        searched_emails = [targets] if isinstance(targets, str) else list(targets)
        
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        
        # reverse search supplied emails to find associated GitHub logins and committer data
        logins, committer_data = search.email_reverse_search(token, targets)
        
        depth = menus.recursion_menu() # prompt user for desired recursion depth
        
        # fetch user data for the logins returned by the email reverse search
        user_data, target = search.user_search_exact(
            token,
            logins,
            depth,
            extra_emails=committer_data,
        )
        
        # ensures outfile naming convention lists total count of actual user logins retrieved
        target = (
            user_data[0]["login"]
            if len(user_data) == 1
            else f"{len(user_data)}-Users"
        )
    
    if search_mode in {"1", "3"}:
        enriched = "_Enriched"
    
    else: # allows optional enrichment of other search modes (partial + other future methods)
        # pause the timer while waiting on user input, then resume by shifting start_time forward
        prompt_start = time.perf_counter()
        choice = menus.selection_menu(enrichment_options)
        start_time += time.perf_counter() - prompt_start
        
        if choice == "1":
            enriched = "_Enriched"
            user_data = transform.user_commit_history(token, user_data)
        else:
            enriched = ""
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    # update outfile_title to reflect methods used to generate outfile data
    state.outfile_title = f"_{search_method}_{target}{enriched}"
    
    return user_data, searched_logins, searched_emails

def _organization_search(token) -> tuple[list[dict], str, str]:
    '''
    Broadens target analysis by fetching Organization and members info. Intersect search mode can identify users holding significant membership to multiple suspicious organizations:
    1. Exact: Returns info on the input Organizations and their members (useful for preliminary exploration of suspected malicious organizations).
    '''
    search_method = "Org"
    
    targets = menus.multiple_input_prompt("Organization") # user input menu
    menus.clear_terminal()
    
    start_time = time.perf_counter() # Start time measurement (Benchmarking)
    org_data, member_data, target = search.organization_search(token, targets)
    
    # pause the timer while waiting on user input, then resume by shifting start_time forward
    prompt_start = time.perf_counter()
    choice = menus.selection_menu(enrichment_options)
    start_time += time.perf_counter() - prompt_start
    
    if choice == "1": # enrich current results data, takes significantly longer
        enriched = "_Enriched" # leading underscore included to match outfile naming convention
        member_data = transform.user_commit_history(token, member_data)
    
    else: # skip enrichment
        enriched = ""
    
    # score results
    results = transform.scoring_battery(org_data + member_data)
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    state.outfile_title = f"_{search_method}_{target}{enriched}"
    return results # returns target user for inclusion in file naming convention

def _repository_search(token) -> tuple[list[dict], list[str], list[str]]:
    '''
    Broadens target analysis by fetching followership, Organizations, and account metadata. Also returns noteworthy followers:
    1. Full Information: Returns all user and repository metadata associated with the input repositories
    2. Similar Repositories: Returns repositories that are similar to the input repositories based on various criteria.
    3. Code Proliferation: Returns repositories that have significant code overlap with the input repositories.
    '''
    # Prompt user to select the search mode (Full Information, Similar Repositories, or Code Proliferation)
    search_mode_options = [
        "Full Information",
        "Similar Repositories",
        "Code Proliferation"
    ]
    
    search_mode = menus.selection_menu(search_mode_options) # Repository Search Mode Selection
    menus.clear_terminal()
    
    if search_mode == "1": # Full Information
        targets = menus.multiple_input_prompt("Repository owner/name pairs") # repository input menu
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        logins, valid_repo_count = search.repository_search_exact(token, targets) # Fetch logins of users associated with the target repositories
        
        search_method = f"{valid_repo_count}-Repos" # used in outfile naming convention
        enriched = "_Enriched" # used in outfile naming convention
        
        searched_logins = sorted(logins)
        if not logins:
            print("No repository owner or contributor logins returned.")
            menus.quit_program()
        
        # fetch and enrich user data for the logins associated with the target repositories
        user_data, target = search.user_search_exact(token, logins, recursions=0)
    
    elif search_mode == "2": # Similar Repositories
        #### PLACEHOLDER: Implement repository search functionality for each mode
        targets = menus.multiple_input_prompt("Repository owner/name pairs") # repository input menu
        menus.quit_program()
        
    elif search_mode == "3": # Code Proliferation
        #### PLACEHOLDER: Implement repository search functionality for each mode
        targets = menus.multiple_input_prompt("Repository owner/name pairs") # repository input menu
        menus.quit_program()
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    # update outfile_title to reflect methods used to generate outfile data
    state.outfile_title = f"_{search_method}_{target}{enriched}"
    
    return user_data, searched_logins, []

def _pivot_engine(token):
    '''
    Broadens target analysis by fetching followership, Organizations, and account metadata. Also returns noteworthy followers:
    1. Email Pseudonyms: Returns all unique Login, Fullname pairs associated with each input email
    2. Fullname Pseudonyms: Returns all unique Login, Email pairs associated with each input fullname (This may return a large number of users, depending on the search term.)
    '''
    search_method = "Pseudonyms"
    
    targets = menus.multiple_input_prompt("fullname and/or email") # email input menu
    menus.clear_terminal()
    
    start_time = time.perf_counter() # Start time measurement (Benchmarking)
    committer_data, target = search.pseudonym_search(token, targets, target_type="")
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    state.outfile_title = f"_{search_method}_{target}"
    return committer_data # returns target user for inclusion in file naming convention

if __name__ == '__main__':
    is_valid, message = validate_personal_access_token(token)
    if not is_valid:
        print(message)
        menus.quit_program()
    
    # initialize the SQLite database to prevent errors when checking for existing user records or storing new records
    database.initialize_database()
    
    choice = _decision_tree() # Begin program execution
    menus.clear_terminal()
    
    # Initialize variables for output summaries
    searched_logins = []
    searched_emails = []
    summary_user_records = None
    
    if choice == 1: # User Search
        _results_data, searched_logins, searched_emails = _user_search(token)
        
        # score user results based on existing database records
        results_data = transform.score_user_results(
            _results_data,
            database.get_all_user_records(),
        )
        
        # build user records summary for output file
        summary_user_records = results_data
        
        # write user records to sqlite database
        stored_count = database.store_user_records(results_data)
        print(f"Stored {stored_count} user records in {database.DATABASE_PATH}")
    
    elif choice == 2: # Organization Search
        results_data = _organization_search(token)
        
        # build user records summary for output file
        summary_user_records = [
            user for user in results_data
            if user.get("membership") != "N/A"
        ]
    
    elif choice == 3: # Repository Search
        _results_data, searched_logins, searched_emails = _repository_search(token)
        
        # score user results based on existing database records
        results_data = transform.score_user_results(
            _results_data,
            database.get_all_user_records(),
        )
        
        # build user records summary for output file
        summary_user_records = results_data
        
        # write user records to sqlite database
        stored_count = database.store_user_records(results_data)
        print(f"Stored {stored_count} user records in {database.DATABASE_PATH}")
    
    elif choice == 4: # Pivot Engine
        results_data = _pivot_engine(token)
        
        # build user records summary for output file
        summary_user_records = results_data
    
    if not results_data:
        print("\nNO RESULTS RETURNED")
        menus.quit_program()
    
    writeToFile.write_to_excel(
        results_data,
        searched_logins=searched_logins,
        searched_emails=searched_emails,
        user_records=summary_user_records,
    ) # Write results data to an Excel file