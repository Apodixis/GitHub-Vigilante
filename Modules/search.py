from typing import Optional, Iterable
from Modules.queries import graphQL_user_exact_query, graphQL_build_partial_user_query, graphQL_organizations_query
from Modules.requests import user_exact_request, user_partial_request, initial_rest_request, organization_exact_request

def user_search_exact(token: str, login: str | Iterable[str]) -> tuple[list[dict], str]: # Add user selection before return prompting for enrichment.
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Target user profile dict w/ followership relationships added.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    if isinstance(login, str):
        logins = [login]
    else:
        logins = sorted({value for value in login if value})
    
    target_rows: list[dict] = []
    followership_by_login: dict[str, dict] = {}
    
    # Iterate through each user-supplied login and fetch their data and followership relationships
    for user_login in logins:
        query = graphQL_user_exact_query(user_login) # Construct the GraphQL query string for current target user
        target_user, followership_by_login = user_exact_request(
            token,
            query,
            user_login,
            followership_by_login
        )
        
        target_rows.append(target_user) # Append completed iteration target user to the list of target user dicts
        print(f"{user_login} processed. Followership records fetched: {len(followership_by_login)}")
    
    followership_rows = list(followership_by_login.values())
    
    #alphabetizes key order for the 'relation' dict for each followership record (followers and following)
    for user in followership_rows:
        relation_value = user.get("relation")
        if isinstance(relation_value, dict):
            user["relation"] = {
                target_login: relation_value[target_login]
                for target_login in sorted(relation_value)
            }
    
    target = logins[0] if len(logins) == 1 else f"{len(logins)}-Users"
    
    return target_rows + followership_rows, target # Concatenate target user dicts with deduplicated followership list of dicts

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
        members_by_login
    )
    
    return target_org, members_by_login