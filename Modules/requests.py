import requests
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlsplit, urlunsplit
from Utils.dataTransformations import compare_user_relations

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

def _normalize_url(raw: str) -> str:
    """
    Inputs: Raw URL string.
    Outputs: Normalized URL string.
    Method: Cleans URL of whitespace and trailing punctuation, converts http to https, removes 'www.' if present.
    """
    if not raw:
        return ""
    cleaned = raw.replace('\xa0', '').rstrip(".,;:<>\"'[]{}-=+!?@#$%^&*()|\\/`~ \n\r") # Clean URL of whitespace and trailing punctuation
    parts = urlsplit(cleaned)
    
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]  # Remove 'www.'
    
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))

def _normalize_user(node: Dict) -> Dict:
    """
    Inputs: User dict from GraphQL response.
    Outputs: Normalized user dict.
    Method: Normalizing URLs to eliminate erroneous duplicates in later steps, reduce dimensionality of objects by discarding less relevant information, and reorganizes dict value ordering based on significance for the written output form.
    Information (per User): Convert GraphQL user node to a flat dict including socialAccounts URLs.
    """
    # Normalize socialAccounts URLs to eliminate erroneous duplicates
    social_nodes = (node.get("socialAccounts") or {}).get("nodes") or []
    social_accounts = {
        _normalize_url(n.get("url"))
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
        "name": node.get("name"),
        "emails": emails,
        "socialAccounts": social_accounts,
        "company": node.get("company"),
        "location": node.get("location"),
        "organizations": organizations,
        "bio": node.get("bio"),
    }

def user_exact_request(
    token: str,
    query: str,
    login: str,
    max_following: int = 250,
    max_followers: int = 250,
    page_size: int = 100,
    social_size: int = 10,
) -> Tuple[Dict, List[Dict]]:
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Target user profile dict, followership list.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
    
    following: List[Dict] = []
    followers: List[Dict] = []
    following_cursor: Optional[str] = None
    followers_cursor: Optional[str] = None
    more_following = True
    more_followers = True
    normalized_target: Optional[Dict] = None
    
    while (more_following or more_followers) and (len(following) < max_following or len(followers) < max_followers):
        variables = {
            "page_size": min(page_size, 100),
            "social_size": min(social_size, 100),
            "following_cursor": following_cursor,
            "followers_cursor": followers_cursor,
        }
        
        response = requests.post(GITHUB_GRAPHQL_URL, json={"query": query, "variables": variables}, headers=headers)
        response.raise_for_status()
        payload = response.json()
        
        if payload.get("errors"):
            raise RuntimeError(f"GraphQL error: {payload['errors']}")
        
        user = payload.get("data", {}).get("user")
        #print(f"Fetched user payload: {user}")
        
        if not user:
            if normalized_target is None:
                raise ValueError(f"Target user '{login}' not found or no data returned from GitHub API.")
            break
        
        # Normalize target_user and perform some data transformations
        if normalized_target is None:
            normalized_target = _normalize_user(user)
        
        # Following
        following_conn = user["following"]
        following_nodes_raw = following_conn.get("nodes") or []
        following_nodes = [_normalize_user(n) for n in following_nodes_raw]
        remaining_following = max_following - len(following)
        if remaining_following > 0:
            following.extend(following_nodes[:remaining_following])
        following_cursor = following_conn["pageInfo"]["endCursor"]
        more_following = following_conn["pageInfo"]["hasNextPage"] and len(following) < max_following
        
        # Followers
        followers_conn = user["followers"]
        followers_nodes_raw = followers_conn.get("nodes") or []
        followers_nodes = [_normalize_user(n) for n in followers_nodes_raw]
        remaining_followers = max_followers - len(followers)
        if remaining_followers > 0:
            followers.extend(followers_nodes[:remaining_followers])
        followers_cursor = followers_conn["pageInfo"]["endCursor"]
        more_followers = followers_conn["pageInfo"]["hasNextPage"] and len(followers) < max_followers
        
        # If no more to fetch, break
        if not (more_following or more_followers):
            break
    
    # Sets user['relation'] value for each user based on followership (mutual, following, follower)
    followership = compare_user_relations(following, followers)
    
    return normalized_target, followership

def user_partial_request(
    token: str,
    query: str,
    page_size: int = 100,
    social_size: int = 10,
) -> Tuple[Dict, List[Dict], List[Dict]]:
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Matched user profile dicts.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
    
    variables = {
            "page_size": min(page_size, 100),
            "social_size": social_size,
        }
    
    response = requests.post(GITHUB_GRAPHQL_URL, json={"query": query, "variables": variables}, headers=headers)
    response.raise_for_status()
    payload = response.json()
    
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL error: {payload['errors']}")
    
    raw_users = list(payload["data"].values())
    
    normalized_users = [
        _normalize_user(user)
        for user in raw_users
        if user
    ]
    
    print(f"Fetched user payload: {normalized_users}")
    
    return normalized_users

#============================================================================================

def initial_rest_request(token: str, url: str) -> List[Dict]:
    """
    Inputs: GitHub Personal Access Token and complete REST API Query URL.
    Outputs: Response.json data (Results)
    Method: REST API request with token authorization
    Information: All records 
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    results = response.json()
    
    return results