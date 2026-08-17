from urllib.parse import urlsplit, urlunsplit
from typing import Dict

def normalize_url(raw: str) -> str:
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
    
    for login in all_logins:
        if login in following_dict and login in followers_dict:
            user = following_dict[login].copy()
            user['relation'] = 'mutual'
            relations.append(user)
            
        elif login in following_dict:
            user = following_dict[login].copy()
            user['relation'] = 'following'
            relations.append(user)
            
        elif login in followers_dict:
            user = followers_dict[login].copy()
            user['relation'] = 'follower'
            relations.append(user)
    
    return relations