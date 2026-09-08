from urllib.parse import urlsplit, urlunsplit
from typing import Dict
import Modules.client as client

def normalize_url(raw: str) -> str:
    """
    Inputs: Raw URL string.
    Outputs: Normalized URL string.
    Method: Cleans URL of whitespace and trailing punctuation, converts http to https, removes 'www.' if present.
    """
    if not raw:
        return ""
    cleaned = raw.replace('\xa0', '').rstrip(".,;:<>\"'[]{}-=+!?@#$%^&*()|\\/`~ \n\r") # Clean URL of whitespace and trailing punctuation
    
    try:
        parts = urlsplit(cleaned)
    except ValueError as error:
        print(f"URL normalization failed: {error}")
        return ""
    
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]  # Remove 'www.'
    
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))

def normalize_user(node: Dict) -> Dict:
    """
    Inputs: User dict from GraphQL response.
    Outputs: Normalized user dict.
    Method: Normalizing URLs to eliminate erroneous duplicates in later steps and flattening dicts to reduce dimensionality of objects.
    Information (per User): login, createdAt, name, emails, socialAccounts, company, location, organizations, bio.
    """
    # Normalize socialAccounts URLs to eliminate erroneous duplicates
    social_nodes = (node.get("socialAccounts") or {}).get("nodes") or []
    social_accounts = {
        normalize_url(n.get("url"))
        for n in social_nodes
        if n and n.get("url")
    }
    social_accounts.discard("")
    
    # Extract organizations (list of org logins)
    organization_nodes = (node.get("organizations") or {}).get("nodes") or []
    organizations = [org.get("login") for org in organization_nodes if org and org.get("login")]
    
    # Always return emails as a set (if present, else empty set)
    email_val = node.get("email")
    emails = set() # Convert to set to support future scraping/querying to harvest additional emails
    
    if email_val:
        emails.add(email_val)
    
    return {
        "login": node.get("login"),
        "createdAt": node.get("createdAt"),
        "updatedAt": node.get("updatedAt"),
        "name": node.get("name"),
        "emails": emails,
        "socialAccounts": social_accounts,
        "company": node.get("company"),
        "location": node.get("location"),
        "organizations": organizations,
        "org_count": len(organizations),
        "bio": node.get("bio"),
    }

def normalize_org(node: Dict) -> Dict:
    """
    Inputs: Organization or member dict from GraphQL response.
    Outputs: Normalized organization / member dict with shared key schema.
    Method: Normalizing URLs to eliminate erroneous duplicates in later steps and flattening dicts to reduce dimensionality of objects.
    Information (per Organization and member): login, createdAt, name, emails, (socialAccounts or websiteUrl), company (if applicable), location, (description or bio).
    """
    # Normalize social account URLs
    website_url = node.get("websiteUrl")
    social_nodes = (node.get("socialAccounts") or {}).get("nodes") or []
    if website_url:
        social_nodes = social_nodes + [{"url": website_url}]
    social_accounts = {
        normalize_url(n.get("url"))
        for n in social_nodes
        if n and n.get("url")
    }
    social_accounts.discard("")
    
    # Normalize org email(s) to set for consistency with user normalization
    email_val = node.get("email")
    emails = {email_val} if email_val else set()
    
    return {
        "login": node.get("login"),
        "createdAt": node.get("createdAt"),
        "updatedAt": node.get("updatedAt"),
        "name": node.get("name"),
        "emails": emails,
        "socialAccounts": social_accounts if social_accounts else [],
        "company": node.get("company"),
        "location": node.get("location"),
        "bio": node.get("description") if node.get("description") else node.get("bio"),
    }

def compare_user_relations(following: list, followers: list) -> list:
    """
    Inputs: Two lists of user dicts: (1) following and (2) followers.
    Outputs: List of user dicts annotated with their relationship to the target user.
    Method: Membership testing and dictionary merging.
    Information (per User): Relation to target user ('mutual', 'following', or 'follower').
    """
    following_dict = {user['login']: user for user in following if user.get('login')}
    followers_dict = {user['login']: user for user in followers if user.get('login')}
    all_logins = set(following_dict.keys()) | set(followers_dict.keys())
    relations = []
    
    # user followership comparisons
    for login in all_logins:
        if login in following_dict and login in followers_dict:
            user = following_dict[login].copy()
            user['_relation'] = 'mutual'
            relations.append(user)
            
        elif login in following_dict:
            user = following_dict[login].copy()
            user['_relation'] = 'following'
            relations.append(user)
            
        elif login in followers_dict:
            user = followers_dict[login].copy()
            user['_relation'] = 'follower'
            relations.append(user)
    # --
    
    return relations

def user_commit_history(token: str, results: list[dict]) -> list[dict]: # enrichment function
    """
    Inputs: List of user dicts and personal access token
    Outputs: List of user dicts with head and tail commit history enrichment
    Method: GitHub REST API search endpoint
    Information (per User): Email, Timestomped commits? (bool)
    """
    base_url = "https://api.github.com/search/commits"
    order = ["asc", "desc"]
    
    print("Beginning results enrichment from commit history data")
    i = 0
    for user in results:
        i += 1
        
        user["timestompedCommits"] = False # initialize "timestompedCommits" key
        login = user.get("login")
        if not login:
            continue
        
        total_count: int | None = None
        
        # Ensure emails are stored as a set for consistent processing
        emails = user.get("emails")
        if isinstance(emails, set):
            pass
        elif isinstance(emails, str):
            emails = {emails}
        else:
            emails = set(emails or [])
        user["emails"] = emails
        # --
        
        for sort_order in order: # iterate over first and last 100 commits (head/tail sampling to reduce total API calls)
            if sort_order == "desc" and total_count is not None and total_count <= 100: # prevent unnecessary API calls for small result sets
                break
            
            per_page = 100 if total_count is None or total_count > 200 else total_count - 100
            params={
                "q": f"author:{login}",
                "per_page": per_page,
                "page": 1,
                "sort": "committer-date",
                "order": sort_order,
            }
            
            # REST API rate limit handling (prevents exceeding 30 requests per minute)
            response = client.rest_request(token, base_url, params=params)
            # --
            
            if total_count is None:
                total_count = response.get("total_count", 0)
                
            commits = [item for item in response.get("items", []) if isinstance(item, dict)]
            
            if not commits:
                break
            
            # commit data processing
            if sort_order == "asc":
                first_committer = ((commits[0].get("commit") or {}).get("committer") or {}).get("date")
                
                if first_committer and user.get("createdAt") and first_committer < user.get("createdAt"): # first commit is older than account
                    user["timestompedCommits"] = True
            
            for item in commits:
                email = (item.get("commit", {}).get("committer") or {}).get("email")
                committed_date = (item.get("commit", {}).get("committer") or {}).get("date")
                authored_date = (item.get("commit", {}).get("author") or {}).get("date")
                
                if committed_date and authored_date and committed_date < authored_date: # code pushed before it was created
                    user["timestompedCommits"] = True
                
                if email and "noreply" not in email:
                    user["emails"].add(email)
            # -- end of commit data processing
            
            if total_count <= 100: # protects against unnecessary pagination for small result sets
                break
            
        print(f"Commit history data retrieved for login {login}: {i} of {len(results)} user records")
    
    return results