import os, time, requests
from pathlib import Path

import Modules.state as state # used to store global state variables like authorized_login
import Utils.menus as menus # used to print option trees and to handle user input collection
import Modules.search as search # consists of logic for each search method
import Utils.dataTransformations as transform # used for transforming and enriching GitHub user data
import Utils.writeToFile as writeToFile # used to write results to file (.xlsx)

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
        
    if r.status_code == 401:
        return False, "Token is invalid, expired, or revoked."
    if r.status_code == 403:
        return False, "Token rejected or rate-limited."
    if r.status_code != 200:
        return False, f"Token validation failed with status code {r.status_code}: {r.text[:200]}"
    
    state.authorized_login = r.json().get("login") # fetch authenticated user's login for use in constructing the user-agent string
    
    return True, "Token is valid."

## PERSONAL ACCESS TOKEN TEST BLOCK
#--------------------------------------------------------------------------------

def _decision_tree() -> int:
    menus.clear_terminal()
    
    print("1) User Search")
    print("2) Organization Search")
    print("3) Pivot Engine")
    print("4) PLACEHOLDER") # Development placeholder for additional, unknown functions
    
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

def _user_search(token) -> tuple[list[dict], str, str]:
    '''
    Broadens target analysis by fetching followership, Organizations, and account metadata. Also returns noteworthy followers:
    1. Exact: Returns info on the input User(s) and their followership and stargazing relationships
    2. Partial: Returns info on all Users returned by the partial search query. User info includes followership and stargazing relationships. (This may return a large number of users, depending on the search term.)
    '''
    search_method = "User"
    
    search_mode_options = [
        "User Search - Exact Match",
        "User Search - Partial Match",
        "User Search - Email Reverse Search"
        ]
    search_mode = menus.selection_menu(search_mode_options) # User Search Mode Selection
    menus.clear_terminal()
    
    if search_mode == "1": # User Search Exact
        targets = menus.multiple_input_prompt("User login") # user input menu
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        user_data, target = search.user_search_exact(token, targets)
    
    elif search_mode == "2": # User Search Partial
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
        targets = menus.multiple_input_prompt("Email") # email input menu
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        logins, committer_data = search.email_reverse_search(token, targets)
        
        user_data, target = search.user_search_exact(token, logins)
        
        # check if target email addresses are not associated with fetched user dicts; add if missing
        if isinstance(committer_data, dict):
            for user in user_data:
                if not isinstance(user, dict):
                    continue
                
                login = user.get("login")
                email = committer_data.get(login)
                if email is None:
                    continue
                
                if email not in user["emails"]:
                    user["emails"].add(email)
        # --
    
    # pause the timer while waiting on user input, then resume by shifting start_time forward
    prompt_start = time.perf_counter()
    choice = menus.selection_menu(enrichment_options)
    start_time += time.perf_counter() - prompt_start
    # --
    
    if choice == "1": # enrich current results data, takes significantly longer
        enriched = "_Enriched" # leading underscore included to match outfile naming convention
        user_data = transform.user_commit_history(token, user_data)
    
    else: # skip enrichment
        enriched = ""
    
    # score results
    user_data = transform.scoring_battery(user_data)
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    state.outfile_title = f"{search_method}_{target}{enriched}"
    return user_data

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
    
    state.outfile_title = f"{search_method}_{target}{enriched}"
    return results # returns target user for inclusion in file naming convention

def _pivot_engine(token):
    '''
    Broadens target analysis by fetching followership, Organizations, and account metadata. Also returns noteworthy followers:
    1. Email Pseudonyms: Returns all unique Login, Fullname pairs associated with each input email
    2. Fullname Pseudonyms: Returns all unique Login, Email pairs associated with each input fullname (This may return a large number of users, depending on the search term.)
    '''
    search_mode_options = [
        "Pseudonym Search - Emails",
        "Pseudonym Search - Fullnames"
        ]
    search_mode = menus.selection_menu(search_mode_options) # Pseudonym Search Mode Selection
    menus.clear_terminal()
    
    search_method = "Pseudonyms"
    
    if search_mode == "1": # Email Pseudonyms Search
        target_type = "email"
        
        targets = menus.multiple_input_prompt("Email") # email input menu
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        committer_data, target = search.pseudonym_search(token, targets, target_type)
    
    elif search_mode == "2": # Fullname Pseudonyms Search
        target_type = "name"
        
        targets = menus.multiple_input_prompt("Fullname") # fullname input menu
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        committer_data, target = search.pseudonym_search(token, targets, target_type)
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    state.outfile_title = f"{search_method}_{target}"
    return committer_data # returns target user for inclusion in file naming convention

if __name__ == '__main__':
    is_valid, message = validate_personal_access_token(token)
    if not is_valid:
        print(message)
        menus.quit_program()
    
    choice = _decision_tree() # Begin program execution
    menus.clear_terminal()
    
    if choice == 1: # User Search
        results_data = _user_search(token) # Fetch user data and target username
    
    elif choice == 2: # Organization Search
        results_data = _organization_search(token)
    
    elif choice == 3: # Pivot Engine
        results_data = _pivot_engine(token)
    
    elif choice == 4:
        print("PLACEHOLDER for additional functionality.")
        menus.quit_program()
    
    if not results_data:
        print("\nNO RESULTS RETURNED")
        menus.quit_program()
    else:
        writeToFile.write_to_excel(results_data) # Write results data to an Excel file