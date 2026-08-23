import requests
from typing import List, Dict, Tuple, Optional
import Utils.dataTransformations as transform

"""
Central location for sending HTTP requests and handling response contents
"""

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

def user_exact(
    token: str,
    query: str,
    login: str,
    followership: Optional[Dict[str, Dict]] = None,
    max_following: int = 250,
    max_followers: int = 250,
    page_size: int = 100,
    social_size: int = 10,
) -> Tuple[Dict, Dict[str, Dict]]:
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Target user profile dict, followership list.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
    
    if followership is None:
        followership = {}
    
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
            normalized_target = transform.normalize_user(user)
        
        # Following
        following_conn = user["following"]
        following_nodes_raw = following_conn.get("nodes") or []
        following_nodes = [transform.normalize_user(n) for n in following_nodes_raw]
        remaining_following = max_following - len(following)
        if remaining_following > 0:
            following.extend(following_nodes[:remaining_following])
        following_cursor = following_conn["pageInfo"]["endCursor"]
        more_following = following_conn["pageInfo"]["hasNextPage"] and len(following) < max_following
        
        # Followers
        followers_conn = user["followers"]
        followers_nodes_raw = followers_conn.get("nodes") or []
        followers_nodes = [transform.normalize_user(n) for n in followers_nodes_raw]
        remaining_followers = max_followers - len(followers)
        if remaining_followers > 0:
            followers.extend(followers_nodes[:remaining_followers])
        followers_cursor = followers_conn["pageInfo"]["endCursor"]
        more_followers = followers_conn["pageInfo"]["hasNextPage"] and len(followers) < max_followers
        
        # If no more to fetch, break
        if not (more_following or more_followers):
            break
    
    # Store per-target relationship type as {target_login: relation_type} and merge by related login.
    relation_rows = transform.compare_user_relations(following, followers)
    for related_user in relation_rows:
        related_login = related_user.get("login")
        if not related_login:
            continue
        
        incoming_relationship = related_user.get("relation")
        related_user["relationships"] = {login: incoming_relationship} if incoming_relationship else {}
        
        existing_user = followership.get(related_login)
        if existing_user is None:
            followership[related_login] = related_user
            continue
        
        existing_relationships = existing_user.get("relationships")
        
        if isinstance(existing_relationships, dict):
            existing_relationships.update(related_user["relationships"])
            
        elif isinstance(existing_relationships, str):
            existing_user["relationships"] = {login: existing_relationships, **related_user["relationships"]}
            
        elif isinstance(existing_relationships, set):
            
            # handles data in incompatible data structs from earlier design and merges it into a dict
            existing_user["relationships"] = {login: ",".join(sorted(existing_relationships))}
            existing_user["relationships"].update(related_user["relationships"])
            
        else:
            existing_user["relationships"] = related_user["relationships"]
    
    return normalized_target, followership

def user_partial(
    token: str,
    query: str,
    page_size: int = 100,
    social_size: int = 10,
) -> List[Dict]:
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
        transform.normalize_user(user)
        for user in raw_users
        if user
    ]
    
    #print(f"Fetched user payload: {normalized_users}")
    
    return normalized_users

#============================================================================================

def initial_rest(token: str, url: str, params: Optional[Dict] = None) -> Dict:
    """
    Inputs: GitHub Personal Access Token and complete REST API Query URL.
    Outputs: Response.json data (Results)
    Method: REST API request with token authorization
    Information: All records 
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(url, headers=headers, params=params, timeout=(10,10)) # 10s connect, 10s read timeout
    
    # http response error notification
    if not response.ok:
        print(f"GitHub REST API error ({response.status_code}): {response.text}")
        print(f"Rate limit remaining: {response.headers.get('X-RateLimit-Remaining')}")
        print(f"Rate limit reset: {response.headers.get('X-RateLimit-Reset')}")
    
    response.raise_for_status()
    results = response.json()
    
    return results

#============================================================================================

def organization_exact(
    token: str,
    query: str,
    login: str,
    members_by_login: Optional[Dict[str, Dict]] = None,
    max_members: int = 1000,
    page_size: int = 100,
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """
    Inputs: GitHub personal access token, graphQL Organizations query, and a GitHub organization login
    Outputs: List of Organization dicts, and a deduplicated members dict (keyed by member login).
    Method: GitHub GraphQL API with pagination.
    Information (per Organization/member): Login, createdAt, Name, Email, social accounts, Company, Location, membership, Bio.
    """
    headers = {"Authorization": f"bearer {token}", "Content-Type": "application/json"}
    
    if members_by_login is None:
        members_by_login = {}
    
    members_cursor: Optional[str] = None
    more_members = True
    normalized_target: Optional[Dict] = None
    org: Optional[Dict] = None
    new_members = 0
    
    while more_members:
        variables = {
            "page_size": min(page_size, 100),
            "members_cursor": members_cursor,
        }
            
        response = requests.post(GITHUB_GRAPHQL_URL, json={"query": query, "variables": variables}, headers=headers)
        response.raise_for_status()
        payload = response.json()
            
        if payload.get("errors"):
            raise RuntimeError(f"GraphQL error: {payload['errors']}")
        
        org = payload.get("data", {}).get("organization")
        #print(f"Fetched organization payload: {org}")
        
        if not org:
            if normalized_target is None:
                raise ValueError(f"Target organization '{login}' not found or no data returned from GitHub API.")
            break
        
        # Members
        members_conn = org["membersWithRole"]
        members_nodes_raw = members_conn.get("nodes") or []
        members_nodes = [transform.normalize_org(n) for n in members_nodes_raw]
        for member in members_nodes:
            member_login = member.get("login")
            if not member_login:
                continue
            
            existing_member = members_by_login.get(member_login)
            if existing_member is not None:
                existing_membership = existing_member.get("membership", set())
                if isinstance(existing_membership, str):
                    existing_membership = {existing_membership}
                elif isinstance(existing_membership, list):
                    existing_membership = set(existing_membership)
                
                existing_membership.add(login)
                existing_member["membership"] = existing_membership
                continue
            
            if new_members >= max_members:
                continue
            
            member["membership"] = {login}
            members_by_login[member_login] = member
            new_members += 1
        
        members_cursor = members_conn["pageInfo"]["endCursor"]
        more_members = (
            members_conn["pageInfo"]["hasNextPage"]
            and new_members < max_members
        )
        
        # If no more to fetch, break
        if not more_members:
            break
    
    if org is None:
        raise ValueError(f"Target organization '{login}' not found or no data returned from GitHub API.")
    
    normalized_target = transform.normalize_org(org)
    normalized_target["membership"] = "N/A"
    
    return [normalized_target], members_by_login