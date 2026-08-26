import os, time, requests
from pathlib import Path
import Modules.search as search
import Utils.menus as menus
import Utils.writeToFile as writeToFile

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

## GITHUB PERSONAL ACCESS TOKEN DECLARATION
#--------------------------------------------------------------------------------
## PERSONAL ACCESS TOKEN TEST BLOCK

def validate_personal_access_token(token: str) -> tuple[bool, str]:
    """
    Validates the provided GitHub Personal Access Token by making a request to the GitHub REST API.
    Returns a tuple (is_valid, message) indicating whether the token is valid and an associated message.
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
    
    return True, "Token is valid."

## PERSONAL ACCESS TOKEN TEST BLOCK
#--------------------------------------------------------------------------------

def _decision_tree() -> int:
    menus.clear_terminal()
    
    print("1) User Search")
    print("2) Email Search")
    print("3) Organization Search")
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
    1. Exact: Returns info on the input user and their followership and stargazing relationships
    2. Partial: Returns info on all users returned by the partial search query. User info includes followership and stargazing relationships. (This may return a large number of users, depending on the search term.)
    3. PLACEHOLDER
    4. PLACEHOLDER
    '''
    search_mode = menus.user_search_mode() # User Search Mode Selection
    menus.clear_terminal()
    
    if search_mode == "1": # User Search Exact
        mode = "UserSearchExact"
        
        targets = menus.multiple_input_prompt("User") # user input menu
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        user_data, target = search.user_search_exact(token, targets)
    
    elif search_mode == "2": # User Search Partial
        mode = "UserSearchPartial"
        
        while True:
            target_substring = input("Enter the user login to analyze: ").strip()
            if not target_substring:
                print(f"At least one user login is required.")
                continue
            break
            
        menus.clear_terminal()
        
        start_time = time.perf_counter() # Start time measurement (Benchmarking)
        user_data, target = search.user_search_partial(token, target_substring)
    
    #print(user_data)
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    return user_data, target, mode # returns target user for inclusion in file naming convention

def _email_search(token):
    mode = "EmailPseudonymHistory"
            
    targets = menus.multiple_input_prompt("Email") # email input menu
    menus.clear_terminal()
    
    start_time = time.perf_counter() # Start time measurement (Benchmarking)
    user_data, target = search.email_pseudonyms(token, targets)
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    return user_data, target, mode # returns target user for inclusion in file naming convention

def _organization_search(token) -> tuple[list[dict], str, str]:
    '''
    Broadens target analysis by fetching Organization and members info. Intersect search mode can identify users holding significant membership to multiple suspicious organizations:
    1. Exact: Returns info on the input organizations and its members (useful for preliminary exploration of suspected malicious organizations).
    '''
    mode = "OrganizationSearch"
    
    targets = menus.multiple_input_prompt("Organization") # user input menu
    menus.clear_terminal()
    
    start_time = time.perf_counter() # Start time measurement (Benchmarking)
    org_data, target = search.organization_search(token, targets)
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    
    return org_data, target, mode # returns target user for inclusion in file naming convention

if __name__ == '__main__':
    is_valid, message = validate_personal_access_token(token)
    if not is_valid:
        print(message)
        menus.quit_program()
        
    choice = _decision_tree() # Begin program execution
    menus.clear_terminal()
    
    if choice == 1: # User Search
        user_data, target, mode = _user_search(token) # Fetch user data and target username
        writeToFile.write_to_excel(user_data, target, mode) # Write user data to Excel file
    
    elif choice == 2: # Email Search
        user_data, target, mode = _email_search(token)
        writeToFile.write_to_excel(user_data, target, mode) # Write user data to Excel file
    
    elif choice == 3: # Organization Search
        org_data, target, mode = _organization_search(token)
        writeToFile.write_to_excel(org_data, target, mode) # Write organization data to Excel file
    
    elif choice == 4:
        print("PLACEHOLDER for additional functionality.")
        menus.quit_program()