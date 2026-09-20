from typing import Iterable
import Modules.client as client
import Modules.graphql_fetchers as graphql_fetchers
import Modules.queries as queries

def user_search_exact(token: str, login: str | Iterable[str], recursions: int = 1, _visited: set[str] | None = None) -> tuple[list[dict], str]: # Add user selection before return prompting for enrichment.
    """
    Inputs: GitHub Personal Access Token, one or more GitHub User logins, and an optional followership expansion depth
    Outputs: List of target User profile dicts with followership relationships added
    Method: GitHub GraphQL API with pagination. Recursion used to fetch follower relationship data
    Information (per User): Login, createdAt, updatedAt, Name, Email, Bio, Location, Company, socialAccounts URLs
    """
    if isinstance(login, str):
        logins = [login]
    else:
        logins = sorted({value.casefold(): value for value in login if value}.values()) # dedupe case-insensitively, keep last-seen casing
    
    if recursions < 0:
        raise ValueError("recursions must be zero or greater.")
    
    if _visited is None:
        _visited = set() # tracks logins already fetched across recursion depths to avoid redundant re-fetching
    
    target_rows: list[dict] = []
    followership_by_login: dict[str, dict] = {}
    
    # Iterate through each user-supplied login and fetch their data and followership relationships
    for user_login in logins:
        _visited.add(user_login.casefold())
        query = queries.graphql_user_exact_query(user_login) # Construct the GraphQL query string for current target user
        
        # error handling for input users with invalid logins (no corresponding account exists)
        try:
            target_user, followership_by_login = graphql_fetchers.fetch_user_exact(
                token,
                query,
                user_login,
                followership_by_login
            )
        except ValueError:
            print(f"{user_login} skipped: Invalid Login")
            continue
        
        target_rows.append(target_user) # Append completed iteration target user to the list of target user dicts
        print(f"{user_login} processed. Followership records fetched: {len(followership_by_login)}")
    
    # recurse into the newly discovered followership, treating them as the next depth's targets
    if recursions > 0 and followership_by_login:
        next_logins = {
            related_login for related_login in followership_by_login
            if related_login.casefold() not in _visited
        }
        
        if next_logins:
            nested_rows, _ = user_search_exact(token, next_logins, recursions - 1, _visited)
            
            for nested_user in nested_rows:
                nested_login = nested_user.get("login")
                if not nested_login:
                    continue
                
                # merge the nested fetch back into the followership record already tracking this user (rather than treating it as a new target)
                existing_user = followership_by_login.get(nested_login)
                if existing_user is not None:
                    existing_relationships = existing_user.get("relationships", {})
                    existing_user.update(nested_user)
                    existing_user["relationships"] = existing_relationships | nested_user["relationships"]
                else:
                    followership_by_login[nested_login] = nested_user
    
    # drop followership records that duplicate a target user (can happen when targets follow/are followed by each other)
    target_logins = {user_login.casefold() for user_login in logins}
    followership_rows = [
        user for login, user in followership_by_login.items()
        if login.casefold() not in target_logins
    ]
    
    # alphabetizes key order for the 'relationships' dict for each target and followership record (followers and following)
    for user in target_rows + followership_rows:
        relationship_value = user.get("relationships")
        if isinstance(relationship_value, dict):
            user["relationships"] = {
                related_login: relationship_value[related_login]
                for related_login in sorted(relationship_value)
            }
    
    target = logins[0] if len(logins) == 1 else f"{len(logins)}-Users"
    
    return target_rows + followership_rows, target # Concatenate target user dicts with deduplicated followership list of dicts

def user_search_partial(token: str, login_substring: str) -> tuple[list[dict], str]:
    """
    Inputs: GitHub Personal Access Token and a GitHub User login substring
    Outputs: List of target User profile dicts matching the login substring
    Method: GitHub GraphQL API with pagination
    Information (per User): Login, createdAt, updatedAt, Name, Email, Bio, Location, Company, socialAccounts URLs
    """
    query = queries.graphql_user_partial_query(login_substring) # Construct the GraphQL query string for current target user
    results = graphql_fetchers.fetch_user_partial(token, query)
    
    #print(results)
    return results, login_substring

def email_reverse_search(token: str, targets: str | Iterable[str]) -> tuple[set[str], dict[str, str | None]]:
    """
    Inputs: GitHub Personal Access Token and target email addresses
    Outputs: Dict containing logins (keys) and their corresponding emails (values)
    Method: GitHub Search API for commits with pagination
    Information (per User): Login, Email
    """
    base_url = "https://api.github.com/search/commits"
    results: dict[str, str | None] = {}
    logins: set[str] = set()
    seen: set[tuple[str | None, str | None]] = set()
    
    # handles len(targets) = 1 by converting a single string target into a list to avoid character indexing
    if isinstance(targets, str):
        targets = [targets]
        
    for i, target in enumerate(targets):
        
        params = {
            "q": f"committer-email:{target}",
            "per_page": 100,
            "page": 1,
            "sort": "committer-date",
            "order": "desc"
        }
        
        response = client.rest_request(token, base_url, params)
        
        commits = response.get("items", [])
        if not commits:
            print(f"{i + 1} of {len(targets)} emails processed") # progress update message
            continue
        
        for item in commits:
            login = (item.get("committer") or {}).get("login")
            email = ((item.get("commit") or {}).get("committer") or {}).get("email")
            
            # normalize email to lowercase for consistent comparison
            email = email.casefold() if isinstance(email, str) else email
            
            pair = (login, email)
            if pair in seen:
                continue
            
            else:
                seen.add(pair)
            
            if login is not None or email is not None:
                results[f"{login}"] = email
                logins.add(login)
        
        # progress update message
        if login:
            print(f"\nLogin identified for {target}: {i + 1} of {len(targets)} emails processed")
    
    return logins, results

#============================================================================================

def pseudonym_search(token: str, targets: str | Iterable[str], target_type: str) -> tuple[list[dict], str]:
    """
    Inputs: GitHub Personal Access Token and target email addresses
    Outputs: List of pseudonymous User dicts associated with the target emails
    Method: GitHub Search API for commits with pagination
    Information (per User): Login, Name, Email
    """
    base_url = "https://api.github.com/search/commits"
    results: list[dict] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    
    for target in targets:
        prev_email_length = len(results)
        order = "asc"
        query_descending = False # Used to capture newest commits for users with totalCommits > 1000 (improves volume of considered data)
        descending_remainder: int | None = None
        j = 1 # Define accumulator used in ascending and descending searches
        
        while True:
            i = 1 # Define accumulator used in searches (value not carried over to descending searches)
            totalCount: int | None = descending_remainder if order == "desc" else None
            if totalCount is None:
                total_pages = 1
            else:
                capped_total = min(totalCount, 1000)
                total_pages = (capped_total // 100) + (1 if capped_total % 100 else 0)
            
            while i <= total_pages:
                per_page = 100 if totalCount is None or totalCount >= 100 else totalCount
                params = {
                    "q": f"committer-{target_type}:{target}",
                    "per_page": per_page,
                    "page": i,
                    "sort": "committer-date",
                    "order": order
                }
                
                response = client.rest_request(token, base_url, params)
                
                if totalCount is None:
                    totalCount = response.get("total_count", 0)
                    
                    total_pages = (min(totalCount, 1000) // 100) + (1 if min(totalCount, 1000) % 100 else 0) # Determines how many requests are required (up to 10)
                    
                    # checks if second loop is necessary to capture commits beyond the oldest 1000 results
                    if order == "asc" and totalCount > 1000:
                        query_descending = True
                        descending_remainder = totalCount - 1000
                
                commits = response.get("items", [])
                
                if not commits:
                    break
                
                for item in commits:
                    login = (item.get("committer") or {}).get("login")
                    committer = (item.get("commit") or {}).get("committer") or {}
                    name = committer.get("name")
                    email = committer.get("email")
                    
                    # normalize email to lowercase for consistent comparison
                    email = email.casefold() if isinstance(email, str) else email
                    
                    pair = (login, name, email)
                    if pair in seen:
                        continue
                    
                    else:
                        seen.add(pair)
                    
                    if login is not None or name is not None or email is not None:
                        results.append({
                            "login": login,
                            "name": name,
                            "email": email,
                        })
                
                # progress update block
                if j == 1:
                    print(f"\nHarvesting earliest commit data for: {target}")
                if j == 11:
                    print(f"\nHarvesting latest commit data for: {target}")
                print(f"    Page {j}: {len(commits)} commit records processed. Total unique pseudonym combinations harvested: {len(results) - prev_email_length}")
                
                if totalCount >= 100:
                    totalCount -= 100
                else:
                    totalCount = 0
                
                i, j = i + 1, j + 1 # increment to update request params and print statement
            
            # Set conditions to begin collecting data from "head" of commit history
            if order == "asc" and query_descending:
                order = "desc"
                i = 1
                totalCount = None
                query_descending = False
                continue
            
            break
    
    target = next(iter(targets)) if len(targets) == 1 else f"{len(targets)}-{target_type}"
    
    print(f"\n{len(targets)} {target_type} processed: {len(results)} unique pseudonym combinations harvested.")
    
    return results, target


#============================================================================================

def organization_search(
    token: str,
    login: str | Iterable[str],
) -> tuple[list[dict], str]:
    """
    Inputs: GitHub Personal Access Token and GitHub Organization login(s)
    Outputs: Organization profile dicts plus deduplicated Member dicts, and target label
    Method: GitHub GraphQL API with pagination
    Information (per Organization): Login, createdAt, updatedAt, Name, Email, Location, isVerified, twitterUsername, websiteUrl, Description
    """
    if isinstance(login, str):
        logins = [login]
    else:
        logins = [value for value in login if value]
    
    org_rows: list[dict] = []
    members_by_login: dict[str, dict] = {}
    
    for org_login in logins:
        prior_member_count = len(members_by_login)
        query = queries.graphql_organizations_exact_query(org_login)
        
        # error handling for input organizations with invalid logins (no corresponding account exists)
        try:
            target_org, members_by_login = graphql_fetchers.fetch_organization_exact(
                token,
                query,
                org_login,
                members_by_login,
            )
        except ValueError:
            print(f"{org_login} skipped: Invalid Login")
            continue
        
        org_rows.extend(target_org)
        fetched_this_org = len(members_by_login) - prior_member_count
        print(f"{org_login} processed. Member records fetched: {fetched_this_org}. Total records fetched: {len(members_by_login)}")
    
    members = list(members_by_login.values())
    for member in members:
        membership_value = member.get("membership")
        if isinstance(membership_value, set):
            member["membership"] = sorted(membership_value)
            member["membership_count"] = len(member["membership"])
    
    target = logins[0] if len(logins) == 1 else f"{len(logins)}-Orgs"
    
    return org_rows, members, target