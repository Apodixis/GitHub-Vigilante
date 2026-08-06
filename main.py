import os, time, requests
from pathlib import Path
from Modules.search import user_search_exact
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
    menus.quitProgram()

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
    menus.clearTerminal()
    
    print("1) User Search")
    print("2) Organization Search") # Development placeholder for planned function
    print("3) PLACEHOLDER") # Development placeholder for additional, unknown functions
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

def user_search(token):
    '''
    Broadens target analysis by fetching followership data and returning noteworthy followers:
    1. Exact: Returns info on the input user and their followership and stargazing relationships
    2. Partial: PLACEHOLDER
    3. PLACEHOLDER
    4. PLACEHOLDER
    '''
    target_user = input("Enter the GitHub username to analyze: ").strip()
    menus.clearTerminal()
    
    start_time = time.perf_counter() # Start time measurement (Benchmarking)
    
    user_data = user_search_exact(token, target_user)
    #print(user_data)
    
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution time: {elapsed_time:.4f} seconds") # Prints execution time (without user input delay)
    return user_data, target_user # returns target user for inclusion in file naming convention

if __name__ == '__main__':
    is_valid, message = validate_personal_access_token(token)
    if not is_valid:
        print(message)
        menus.quitProgram()
        
    choice = _decision_tree() # Begin program execution
    
    if choice == 1:
        user_data, target_user = user_search(token) # User Search Exact
        writeToFile.write_user_search_exact_to_excel(user_data, target_user) # Write user data to Excel file
    
    elif choice == 2:
        print("Organization Search PLACEHOLDER.")
        menus.quitProgram()
    
    elif choice == 3:
        print("PLACEHOLDER for additional functionality.")
        menus.quitProgram()
    
    elif choice == 4:
        print("PLACEHOLDER for additional functionality.")
        menus.quitProgram()
    
    