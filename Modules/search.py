from Modules.queries import graphQL_user_exact_query, graphQL_build_partial_user_query
from Modules.requests import user_exact_request, user_partial_request, initial_rest_request

def user_search_exact(token: str, target: str) -> tuple[list[dict], str]: # Add user selection before return prompting for enrichment.
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Target user profile dict w/ followership relationships added.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    query = graphQL_user_exact_query(target) # Fetch the GraphQL query string
    
    target_user, followership = user_exact_request(token, query, target)
    return [target_user] + followership, target # Concatenate user dict with followership list of dicts and return as a single list of dicts

def user_search_partial(token: str, login_substring: str):
    """
    Inputs: GitHub username and personal access token.
    Outputs: Target user profile dict w/ followership relationships added.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    url = f"https://api.github.com/search/users?q={login_substring}+in:login&per_page=100"
    users = initial_rest_request(token, url)
    
    logins = []
    for user in users.get("items", []):
        if user.get("type") == "User":
            logins.append(user["login"])
        else:
            continue
    #print(f"users: {logins}")
    
    query = graphQL_build_partial_user_query(logins)
    #print(query)
    
    results = user_partial_request(token, query)
    #print(results)
    return results, login_substring
