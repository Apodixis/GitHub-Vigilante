from urllib.parse import urlsplit, urlunsplit
from typing import Dict
import networkx as nx

import Modules.client as client
import Modules.queries as queries
import config

ignore_email_substrings = ["noreply", "github-actions", "[bot]"]

def normalize_url(raw: str) -> str:
    """
    Inputs: Raw URL string
    Outputs: Normalized URL string
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
    Inputs: User dict from GraphQL response
    Outputs: Normalized User dict
    Method: Normalizing URLs to eliminate erroneous duplicates in later steps and flattening dicts to reduce dimensionality of objects
    Information (per User): Login, CreatedAt, Name, Emails, socialAccounts, Company, Location, Organizations, Bio
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
    
    # checks to exclude invalid or ignored email addresses
    if email_val and not any(
        substring in email_val.casefold()
        for substring in ignore_email_substrings
    ):
        emails.add(email_val.casefold())
    
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
        "relationships": {},
        "score": 0,
        "timestompedCommits": False
    }

def normalize_org(node: Dict) -> Dict:
    """
    Inputs: Organization or member dict from GraphQL response
    Outputs: Normalized organization / member dict with shared key schema
    Method: Normalizing URLs to eliminate erroneous duplicates in later steps and flattening dicts to reduce dimensionality of objects
    Information (per Organization and member): Login, CreatedAt, Name, Emails, (socialAccounts or websiteUrl), Company (if applicable), Location, (Description or Bio).
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
    emails = {email_val.casefold()} if email_val else set()
    
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
    Inputs: Two lists of User dicts: (1) following and (2) followers.
    Outputs: List of User dicts annotated with their relationship to the Target User.
    Method: Membership testing and dictionary merging.
    Information (per User): Relation to the Target User ('mutual', 'following', or 'follower').
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
    Inputs: GitHub Personal Access Token and a list of User dicts
    Outputs: List of User dicts with head and tail commit history enrichment
    Method: GitHub REST API search endpoint
    Information (per User): Email, Timestomped Commits? (bool)
    """
    # calculate batch sizes for us in queries
    api_points_per_request = 400
    repo_count = 3
    nodes_per_repo = 3 
    user_count = api_points_per_request//(repo_count*2*nodes_per_repo) # multiplied by two to account for head and tail queries
    logins = [user["login"] for user in results if user.get("login")]
    
    # creates a lookup dictionary for results by login (case-insensitive)
    results_by_login = {
        user["login"].casefold(): user
        for user in results
        if user.get("login")
    }
    
    total_enriched_records = 0
    # process users in batches for token-efficient graphQL querying (1 token per request)
    for i in range(0,len(logins), user_count):
        batch_logins = logins[i:i+user_count]
        
        initial_query = queries.graphql_commit_enrichment_query_1(batch_logins, repo_count)
        initial_results = client.graphql_request(token, initial_query)
        if initial_results.get("errors"):
            raise RuntimeError(f"GraphQL error: {initial_results['errors']}")
        initial_results = initial_results.get("data", {})
        
        repo_commit_pairs_by_user: list[tuple[str, dict[str, str]]] = []
        
        # extract [user, {repo: commit_oid}] for each repoWithName and oid pair
        for k, v in initial_results.items():
            if not k.startswith(("oldestRepos", "newestRepos")):
                continue
            
            for repository in v["repositories"]["nodes"]:
                user, repo = repository["nameWithOwner"].split("/", 1)
                default_branch = repository.get("defaultBranchRef") or {}
                
                if not default_branch: # empty repositories can return None for defaultBranchRef
                    continue
                
                commit_oid = default_branch["target"]["oid"]
                
                for existing_user, repositories in repo_commit_pairs_by_user:
                    if existing_user == user:
                        repositories[repo] = commit_oid
                        break
                else:
                    repo_commit_pairs_by_user.append((user, {repo: commit_oid}))
        # --
        
        total_enriched_records += len(repo_commit_pairs_by_user)
        
        # provide progress updates and skip batches with no identified repository-commit pairs
        if repo_commit_pairs_by_user:
            print(f"Batch {i // user_count + 1}: {len(repo_commit_pairs_by_user)} user records harvested. Total enriched records: {total_enriched_records}")
        
        elif not repo_commit_pairs_by_user:
            print(f"Batch {i // user_count + 1}: No repository-commit pairs found, skipping.")
            continue
        # --
        
        committer_query = queries.graphql_commit_enrichment_query_2(repo_commit_pairs_by_user)
        committer_results = client.graphql_request(token, committer_query)
        if committer_results.get("errors"):
            raise RuntimeError(f"GraphQL error: {committer_results['errors']}")
        committer_results = committer_results.get("data", {})
        
        # enumerates owners and accesses their repository data
        for i, (owner, repositories) in enumerate(repo_commit_pairs_by_user):
            result_user = results_by_login.get(owner.casefold())
            if result_user is None:
                continue
            
            emails = result_user.get("emails")
            if not isinstance(emails, set):
                emails = set(emails or []) if not isinstance(emails, str) else {emails}
                result_user["emails"] = emails
            
            # enumerates commits and accesses their metadata
            for j in range(len(repositories)):
                repository = committer_results.get(f"owner{i}repo{j}") or {}
                commit = repository.get("object") or {}
                committer = commit.get("committer") or {}
                if not committer:
                    continue
                
                committer_user = committer.get("user") or {}
                committer_login = committer_user.get("login")
                if not committer_login or committer_login.casefold() != owner.casefold():
                    continue
                
                # checks to exclude invalid or ignored email addresses
                email = committer.get("email")
                normalized_email = email.casefold() if email else ""
                if email and not any(
                    substring in normalized_email
                    for substring in ignore_email_substrings
                ):
                    emails.add(normalized_email)
                
                authored_date = commit.get("authoredDate")
                committed_date = commit.get("committedDate")
                created_at = result_user.get("createdAt")
                
                # check for commits with forged commit timestamps
                if (
                    (committed_date and committed_date < created_at)
                    or (authored_date and committed_date and committed_date < authored_date)
                ):
                    result_user["timestompedCommits"] = True
    
    return results

def build_relationship_graph(results: list[dict]) -> nx.DiGraph:
    """
    Inputs: List of User dicts (targets and related users)
    Outputs: Directed graph connecting every login to the logins found in its 'relationships' dict
    Method: Adds a weighted edge (by relation type strength) for every user -> related_login pair
    """
    relationship_scores = config.relationship_scores
    graph = nx.DiGraph()
    
    for user in results:
        login = (user.get("login") or "").casefold()
        if not login:
            continue
        graph.add_node(login)
        
        relationships = user.get("relationships") or {}
        for related_login, relation in relationships.items():
            weight = relationship_scores.get(relation, 1)
            graph.add_edge(login, related_login.casefold(), weight=weight)
    
    return graph

def guilt_by_association_scores(graph: nx.DiGraph, bad_logins: set) -> dict:
    """
    Inputs: Relationship graph and set of blacklisted logins
    Outputs: Dict of login -> personalized PageRank score (proximity to blacklisted accounts across n-hop paths)
    Method: Personalized PageRank seeded on whichever blacklisted logins are present as nodes in the graph
    """
    seed_nodes = [login for login in bad_logins if login in graph]
    if not seed_nodes: # no blacklisted accounts reachable in this graph, nothing to propagate
        return {}
    
    personalization = {login: 1 for login in seed_nodes}
    return nx.pagerank(graph, alpha=config.graph_pagerank_alpha, personalization=personalization, weight="weight")

def scoring_battery(results: list[dict]) -> list[dict]:
    """
    Inputs: List of User dicts
    Outputs: List of User dicts with score (likelihood of being clustered with the activity set selectors in .config) added
    Method: Inclusion testing against blacklisted and suspicious indicators and link analysis.. 
    Information (per User): Score
    """
    # retrieve scoring weights and blacklists from config.py
    bad_match, suspicious_match = config.bad_match, config.suspicious_match_weight
    bad_logins = {login.casefold() for login in config.BAD_LOGINS}
    bad_emails = {email.casefold() for email in config.BAD_EMAILS}
    suspicious_substrings = config.SUSPICIOUS_SUBSTRINGS
    graph_score_weight = config.graph_pagerank_weight
    
    # build the full relationship graph once and compute guilt-by-association scores for every reachable login
    graph = build_relationship_graph(results)
    graph_scores = guilt_by_association_scores(graph, bad_logins)
    
    # check user values and score based on matches and corresponding weights
    for i, user in enumerate(results):
        score, login_match, email_match = 0, False, False # initialize variables needed for scoring
        login = user.get("login", "").casefold()
        emails = [email.casefold() for email in user.get("emails", set())]
        print(f"Scoring user {i + 1} of {len(results)}: {login}")
        
        # hard-stop immediately for known malicious login/email matches
        if login in bad_logins or any(email in bad_emails for email in emails):
            print(f"User {login} matched blacklisted login or email")
            user["score"] = bad_match # user almost certainly malicious (assuming blacklists are accurate)
            continue
        
        # check if any suspicious substrings in login or email
        login_match = any(substring in login for substring in suspicious_substrings)
        email_match = any(
            any(substring in email for substring in suspicious_substrings)
            for email in emails
        )
        
        if login_match:
            score += suspicious_match
        if email_match:
            score += suspicious_match
        
        # guilt-by-association score: proximity to blacklisted accounts across the n-hop relationship graph
        graph_score = graph_scores.get(login, 0)
        if graph_score:
            # print(f"User {login} guilt-by-association PageRank score: {graph_score:.6f}")
            score += graph_score * graph_score_weight
        
        # assign the final score to the user dictionary
        user["score"] = min(score, bad_match)
    
    return results