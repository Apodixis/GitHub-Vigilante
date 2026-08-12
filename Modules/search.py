from typing import Optional
from Modules.queries import graphQL_user_exact_query, graphQL_build_partial_user_query, graphQL_organizations_query
from Modules.requests import user_exact_request, user_partial_request, initial_rest_request, organization_exact_request

def user_search_exact(token: str, login: str) -> tuple[list[dict], str]: # Add user selection before return prompting for enrichment.
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Target user profile dict w/ followership relationships added.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    query = graphQL_user_exact_query(login) # Fetch the GraphQL query string
    target_user, followership = user_exact_request(token, query, login)
    
    return [target_user] + followership, login # Concatenate user dict with followership list of dicts and return as a single list of dicts

def user_search_partial(token: str, login_substring: str) -> tuple[list[dict], str]:
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

#============================================================================================

def organization_search(
    token: str,
    login: str,
    members_by_login: Optional[dict[str, dict]] = None,
) -> tuple[list[dict], dict[str, dict]]:
    """
    Inputs: GitHub organization name (login) and personal access token.
    Outputs: Organization profile dict, dict of members keyed by member login.
    Method: GitHub GraphQL API with pagination.
    Information (per Organization): Login, createdAt, Name, Email, Location, isVerified, twitterUsername, websiteUrl, Description.
    """
    query = graphQL_organizations_query(login)
    target_org, members_by_login = organization_exact_request(
        token,
        query,
        login,
        members_by_login=members_by_login,
    )
    
    return target_org, members_by_login