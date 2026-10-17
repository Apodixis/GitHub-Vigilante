from typing import Any, List, Dict, Tuple, Optional

import Modules.client as client
import Modules.enrichment as enrichment
import Utils.dataTransformations as transform

"""
Paginates GraphQL connections and normalizes/merges the resulting records; sits between search.py (search orchestration) and client.py (HTTP transport)
"""
# variable declarations for pagination and fetch limits
page_size: int = 100
max_following: int = 500
max_followers: int = 500
max_starred: int = 500
max_members: int = 1000
social_size: int = 4

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
        
        resource_limit_errors = [error for error in payload["errors"] if error.get("type") != "RESOURCE_LIMITS_EXCEEDED"]
        # GitHub nulled out individual over-budget fields rather than failing the whole request; carry on with partial data
        if resource_limit_errors:
            for i, error in enumerate(resource_limit_errors, start=1):
                path = error.get("path", "<path unavailable>")
                message = error.get("message", "<message unavailable>")
                locations = error.get("locations", "<locations unavailable>")
                print(f"  Resource-limit error {i}: path={path!r}; locations={locations!r}; message={message}")
            raise RuntimeError(f"GraphQL error: {resource_limit_errors}")
        
        print(f"GitHub GraphQL resource limits exceeded for {len(payload['errors'])} field(s); continuing with partial data.")
    
    return payload.get("data", {})

def fetch_user_exact(
    token: str,
    query: str,
    login: str,
) -> Tuple[Dict, set[str]]:
    """
    Inputs: GitHub Personal Access Token, GraphQL query, GitHub username (login), and pagination limits
    Outputs: Target user profile dict and related follower/following logins
    Method: Paginates the GraphQL followers/following connections via client.graphql_request(), normalizing and merging results
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs, starred repositories
    """
    following: set[str] = set()
    followers: set[str] = set()
    following_cursor: Optional[str] = None
    followers_cursor: Optional[str] = None
    starred_cursor: Optional[str] = None
    more_following = True
    more_followers = True
    more_starred = True
    starred_count = 0
    starred_users: Dict[str, int] = {}
    normalized_target: Optional[Dict] = None
    
    while (
        (more_following and len(following) < max_following)
        or (more_followers and len(followers) < max_followers)
        or (more_starred and starred_count < max_starred)
    ):
        fetch_following = more_following and len(following) < max_following
        fetch_followers = more_followers and len(followers) < max_followers
        fetch_starred = more_starred and starred_count < max_starred
        variables = {
            "following_cursor": following_cursor,
            "followers_cursor": followers_cursor,
            "starred_cursor": starred_cursor,
            "starred_page_size": max(1, min(page_size, max_starred - starred_count)),
            "fetch_following": fetch_following,
            "fetch_followers": fetch_followers,
            "fetch_starred": fetch_starred,
        }
        
        payload = _fetch_page(token, query, variables, not_found_path=["user"], not_found_target=login)
        user = payload.get("user")
        #print(f"Fetched user payload: {user}")
        
        # check if the user exists in the payload
        if not user:
            if normalized_target is None:
                raise ValueError(f"Target user '{login}' not found or no data returned from GitHub API.")
            break
        
        # normalize target_user and perform some data transformations
        if normalized_target is None:
            normalized_target = transform.normalize_record(user)
            normalized_target["relationships"] = {}
        
        # build outbound starred repository relationships and calculate degree of starred interactions per owner (user)
        if fetch_starred:
            starred_conn = user.get("starredRepositories") or {}
            starred_edges = starred_conn.get("edges") or []
            starred_count += len(starred_edges)
            
            for edge in starred_edges:
                if not edge:
                    continue
                repository = edge.get("node") or {}
                if not repository:
                    continue
                
                # extract owner login from the repository's nameWithOwner field
                name_with_owner = repository.get("nameWithOwner") or ""
                owner_login, separator, _ = name_with_owner.partition("/")
                
                # only consider the repository if it has a valid owner and the owner is not the same as the normalized target user
                if separator and owner_login and owner_login.casefold() != normalized_target["login"].casefold():
                    owner_login = owner_login.casefold()
                    starred_users[owner_login] = starred_users.get(owner_login, 0) + 1 # accumulates the degree of the outgoing starred relationship
            
            # extract pagination info for starred repositories connection
            starred_page_info = starred_conn.get("pageInfo") or {}
            starred_cursor = starred_page_info.get("endCursor")
            
            # set flag indicating if there are more starred repositories to fetch
            more_starred = (
                starred_page_info.get("hasNextPage", False)
                and starred_count < max_starred
            )
        
        # Following
        if fetch_following:
            following_conn = user.get("following") or {}
            following_nodes_raw = following_conn.get("nodes") or []
            
            # add following logins to the following set
            for node in following_nodes_raw:
                related_login = node.get("login") if node else None
                if related_login and len(following) < max_following:
                    following.add(related_login)
            
            # extract pagination info for following connection
            following_page_info = following_conn.get("pageInfo") or {}
            following_cursor = following_page_info.get("endCursor")
            
            # set flag indicating if there are more following users to fetch
            more_following = (
                following_page_info.get("hasNextPage", False)
                and len(following) < max_following
            )
        # -- END OF FOLLOWING SECTION
        
        # Followers
        if fetch_followers:
            followers_conn = user.get("followers") or {}
            followers_nodes_raw = followers_conn.get("nodes") or []
            
            # add follower logins to the followers set
            for node in followers_nodes_raw:
                related_login = node.get("login") if node else None
                if related_login and len(followers) < max_followers:
                    followers.add(related_login)
            
            # extract pagination info for followers connection
            followers_page_info = followers_conn.get("pageInfo") or {}
            followers_cursor = followers_page_info.get("endCursor")
            
            # set flag indicating if there are more followers to fetch
            more_followers = (
                followers_page_info.get("hasNextPage", False)
                and len(followers) < max_followers
            )
        # -- END OF FOLLOWERS SECTION
    
    # assign relationship values to the starred_users and relationships keys
    if normalized_target is not None:
        normalized_target["starred_users"] = starred_users
        
        # check if user should be classified as a follow botter (affects scoring)
        normalized_target["isFollowBotter"] = enrichment.follow_bot_identification(
            followers,
            following,
            set(starred_users),
        )
        
        # assign relationship values to the normalized target user
        normalized_target["relationships"] = transform.compare_user_relations(
			following,
			followers,
			set(starred_users),
		)
    
    # Include follower, following, and starred-owner logins in recursive expansion.
    followership_logins = following | followers | set(starred_users)
    
    return normalized_target, followership_logins

def fetch_user_partial(token: str, query: str) -> List[Dict]:
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
        variables = { "cursor": cursor }
        
        data = _fetch_page(token, query, variables)
        
        search = data.get("search")
        if not search:
            break
        
        raw_users = search.get("nodes") or []
        
        normalized_users.extend(
            transform.normalize_record(user)
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
    members_by_login: Optional[Dict[str, Dict]] = None
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
    
    # loop to fetch organization members with pagination
    while more_members:
        variables = { "members_cursor": members_cursor }
        
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
        members_nodes = [transform.normalize_record(n) for n in members_nodes_raw]
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
    
    # normalize the organization record and set membership fields to "N/A" since it's not applicable for organizations
    normalized_target = transform.normalize_record(org, is_user=False)
    normalized_target["membership"] = "N/A"
    normalized_target["membership_count"] = "N/A"
    
    return [normalized_target], members_by_login
