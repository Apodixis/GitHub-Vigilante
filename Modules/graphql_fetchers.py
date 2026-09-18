from typing import Any, List, Dict, Tuple, Optional

import Modules.client as client
import Utils.dataTransformations as transform

"""
Paginates GraphQL connections and normalizes/merges the resulting records; sits between search.py (search orchestration) and client.py (HTTP transport)
"""

def _fetch_page(
    token: str,
    query: str,
    variables: Dict,
    not_found_path: Optional[List[str]] = None,
    not_found_target: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inputs: GitHub Personal Access Token, GraphQL query/variables, and the response 'path' that signals a missing target
    Outputs: The 'data' portion of the decoded GraphQL payload
    Method: Sends the request via client.graphql_request(), raising ValueError for a missing target or RuntimeError for any other GraphQL error
    """
    payload = client.graphql_request(token, query, variables)
    
    if payload.get("errors"):
        if not_found_path is not None and any(
            error.get("type") == "NOT_FOUND" and error.get("path") == not_found_path
            for error in payload["errors"]
        ):
            raise ValueError(f"Target '{not_found_target}' not found or no data returned from GitHub API.")
        raise RuntimeError(f"GraphQL error: {payload['errors']}")
    
    return payload.get("data", {})

def fetch_user_exact(
    token: str,
    query: str,
    login: str,
    followership: Optional[Dict[str, Dict]] = None,
    max_following: int = 250,
    max_followers: int = 250,
    page_size: int = 100,
    social_size: int = 100,
) -> Tuple[Dict, Dict[str, Dict]]:
    """
    Inputs: GitHub Personal Access Token, GraphQL query, GitHub username (login), and pagination limits
    Outputs: Target user profile dict, followership dict (keyed by related login)
    Method: Paginates the GraphQL followers/following connections via client.graphql_request(), normalizing and merging results
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs
    """
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
        
        payload = _fetch_page(token, query, variables, not_found_path=["user"], not_found_target=login)
        user = payload.get("user")
        #print(f"Fetched user payload: {user}")
        
        if not user:
            if normalized_target is None:
                raise ValueError(f"Target user '{login}' not found or no data returned from GitHub API.")
            break
        
        # Normalize target_user and perform some data transformations
        if normalized_target is None:
            normalized_target = transform.normalize_user(user)
            normalized_target["relationships"] = {}
        
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
    
    # Store each user's relationship types as {other_login: relation_type}, keyed by the related login on each side.
    relation_rows = transform.compare_user_relations(following, followers)
    for related_user in relation_rows:
        related_login = related_user.get("login")
        if not related_login:
            continue
        
        incoming_relationship = related_user.pop("_relation", None)
        related_user["relationships"] = {login: incoming_relationship} if incoming_relationship else {}
        
        # mirror the relationship onto the target's own relationships dict (target's followership, not just related_user's)
        if incoming_relationship and normalized_target is not None:
            normalized_target["relationships"][related_login] = incoming_relationship
        
        existing_user = followership.get(related_login)
        if existing_user is None:
            followership[related_login] = related_user
            continue
        
        existing_user["relationships"].update(related_user["relationships"])
    
    return normalized_target, followership

def fetch_user_partial(
    token: str,
    query: str,
    page_size: int = 100,
    social_size: int = 100,
) -> List[Dict]:
    """
    Inputs: GitHub Personal Access Token, GraphQL query, and pagination limits
    Outputs: List of normalized user dicts matching the login substring
    Method: Paginates the GraphQL search connection via _fetch_page(), normalizing results
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs
    """
    cursor: Optional[str] = None
    normalized_users: List[Dict] = []
    page_number = 1
    
    while True:
        variables = {
            "page_size": min(page_size, 100),
            "social_size": min(social_size, 10),
            "cursor": cursor
        }
        
        data = _fetch_page(token, query, variables)
        
        search = data.get("search")
        if not search:
            break
        
        raw_users = search.get("nodes") or []
        
        normalized_users.extend(
            transform.normalize_user(user)
            for user in raw_users
            if user
        )
        
        page_info = search.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        
        next_cursor = page_info.get("endCursor")
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError(
                "GraphQL pagination error: next cursor is missing or is unchanged."
            )
        
        print(f"Page {page_number}: {len(raw_users)} user records retrieved. Total users: {len(normalized_users)}")
        cursor = next_cursor
        page_number += 1
    
    return normalized_users

def fetch_organization_exact(
    token: str,
    query: str,
    login: str,
    members_by_login: Optional[Dict[str, Dict]] = None,
    max_members: int = 1000,
    page_size: int = 100,
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """
    Inputs: GitHub Personal Access Token, GraphQL query, GitHub organization login, and pagination limits
    Outputs: List containing the normalized organization dict, and a deduplicated members dict (keyed by member login)
    Method: Paginates the GraphQL membersWithRole connection via client.graphql_request(), normalizing and merging results
    Information (per Organization/member): Login, createdAt, Name, Email, social accounts, Company, Location, membership, Bio
    """
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
        
        payload = _fetch_page(token, query, variables, not_found_path=["organization"], not_found_target=login)
        org = payload.get("organization")
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
    normalized_target["membership_count"] = "N/A"
    
    return [normalized_target], members_by_login
