import time
from typing import Iterable
import Modules.client as client
import Modules.queries as queries

def user_search_exact(token: str, login: str | Iterable[str]) -> tuple[list[dict], str]: # Add user selection before return prompting for enrichment.
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Target user profile dict w/ followership relationships added.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, createdAt, updatedAt, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    if isinstance(login, str):
        logins = [login]
    else:
        logins = sorted({value for value in login if value})
    
    target_rows: list[dict] = []
    followership_by_login: dict[str, dict] = {}
    
    # Iterate through each user-supplied login and fetch their data and followership relationships
    for user_login in logins:
        query = queries.graphQL_user_exact(user_login) # Construct the GraphQL query string for current target user
        target_user, followership_by_login = client.user_exact(
            token,
            query,
            user_login,
            followership_by_login
        )
        
        target_rows.append(target_user) # Append completed iteration target user to the list of target user dicts
        print(f"{user_login} processed. Followership records fetched: {len(followership_by_login)}")
    
    followership_rows = list(followership_by_login.values())
    
    # alphabetizes key order for the 'relationships' dict for each followership record (followers and following)
    for user in followership_rows:
        relationship_value = user.get("relationships")
        if isinstance(relationship_value, dict):
            user["relationships"] = {
                target_login: relationship_value[target_login]
                for target_login in sorted(relationship_value)
            }
    
    target = logins[0] if len(logins) == 1 else f"{len(logins)}-Users"
    
    return target_rows + followership_rows, target # Concatenate target user dicts with deduplicated followership list of dicts

def user_search_partial(token: str, login_substring: str) -> tuple[list[dict], str]:
    """
    Inputs: GitHub username and personal access token.
    Outputs: Target user profile dict w/ followership relationships added.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, createdAt, updatedAt, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    i = 1
    results: list[dict] = []
    while i <= 10: # GitHub Search API is capped to 1000 results (10 pages at per_page=100).
        base_url = "https://api.github.com/search/users"
        params = {
            "q": f"{login_substring} in:login",
            "per_page": 100,
            "page": i
        }
        users = client.initial_rest(token, base_url, params=params)
        page_users = users.get("items", [])
        
        if not page_users:
            break
        
        page_logins = []
        for user in page_users:
            if user.get("type") == "User":
                page_logins.append(user["login"])
        
        if page_logins:
            query = queries.graphQL_build_partial_user(page_logins)
            page_results = client.user_partial(token, query)
            results.extend(page_results)
            print(f"{len(page_results)} user records fetched from page {i}. Total records fetched: {len(results)}")
        
        i += 1
    
    #print(results)
    return results, login_substring

#============================================================================================

def email_pseudonyms(token: str, target_emails: str | Iterable[str]) -> tuple[list[dict], str]:
    """
    Inputs: GitHub personal access token and target email addresses.
    Outputs: List of pseudonymous user profiles associated with the target emails.
    Method: GitHub Search API for commits with pagination.
    Information (per User): Login, Name, Email.
    """
    base_url = "https://api.github.com/search/commits"
    results: list[dict] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    # Variable declarations for rate limit safeguards
    request_times: list[float] = []
    max_requests_per_minute = 30
    rate_limit_window = 60.0
    # --
    
    for target in target_emails:
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
                    "q": f"author-email:{target}",
                    "per_page": per_page,
                    "page": i,
                    "sort": "author-date",
                    "order": order
                }
                
                # REST API rate limit handling (prevents exceeding 30 requests per minute)
                now = time.monotonic()
                request_times[:] = [
                    request_time
                    for request_time in request_times
                    if now - request_time < rate_limit_window
                ]
                if len(request_times) >= max_requests_per_minute:
                    delay = rate_limit_window - (now - request_times[0])
                    #print(f"Search API limit reached; waiting {delay:.1f} seconds before the next request.")
                    time.sleep(max(delay, 0))
                    now = time.monotonic()
                    request_times[:] = [
                        request_time
                        for request_time in request_times
                        if now - request_time < rate_limit_window
                    ]
                
                request_times.append(now)
                response = client.initial_rest(token, base_url, params)
                # --
                
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
                    login = (item.get("author") or {}).get("login")
                    name = (item.get("commit", {}).get("author") or {}).get("name")
                    email = (item.get("commit", {}).get("author") or {}).get("email")
                    
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
    
    target = next(iter(target_emails)) if len(target_emails) == 1 else f"{len(target_emails)}-Emails"
    
    print(f"\n{len(target_emails)} emails processed: {len(results)} unique pseudonym combinations harvested.")
    
    return results, target


#============================================================================================

def organization_search(
    token: str,
    login: str | Iterable[str],
) -> tuple[list[dict], str]:
    """
    Inputs: GitHub organization name(s) (login) and personal access token.
    Outputs: Organization profile dicts plus deduplicated member dicts, and target label.
    Method: GitHub GraphQL API with pagination.
    Information (per Organization): Login, createdAt, updatedAt, Name, Email, Location, isVerified, twitterUsername, websiteUrl, Description.
    """
    if isinstance(login, str):
        logins = [login]
    else:
        logins = [value for value in login if value]
    
    org_rows: list[dict] = []
    members_by_login: dict[str, dict] = {}
    
    for org_login in logins:
        prior_member_count = len(members_by_login)
        query = queries.graphQL_organizations(org_login)
        target_org, members_by_login = client.organization_exact(
            token,
            query,
            org_login,
            members_by_login,
        )
        
        org_rows.extend(target_org)
        fetched_this_org = len(members_by_login) - prior_member_count
        print(f"{org_login} processed. Member records fetched: {fetched_this_org}. Total records fetched: {len(members_by_login)}")
    
    members = list(members_by_login.values())
    for member in members:
        membership_value = member.get("membership")
        if isinstance(membership_value, set):
            member["membership"] = sorted(membership_value)
    
    target = logins[0] if len(logins) == 1 else f"{len(logins)}-Orgs"
    
    return org_rows + members, target