# standard library packages (Python-native)
import math
from typing import Dict, Iterable
from urllib.parse import urlsplit, urlunsplit

# local imports
from Modules import client, queries
import config

# third-party packages
import networkx as nx
from sklearn.metrics import average_precision_score # python module name for scikit-learn data science library


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

def normalize_record(node: Dict, *, is_user: bool = True) -> Dict:
    """
    Inputs: User or Organization record (dict) from GraphQL response
    Outputs: Normalized record
    Method: Normalizing URLs to eliminate erroneous duplicates in later steps and flattening dicts to reduce object dimensionality
    Information (per Profile): Login, CreatedAt, Name, Emails, socialAccounts, Company, Location, Organizations, Bio
    """
    # Normalize socialAccounts URLs to eliminate erroneous duplicates
    website_url = node.get("websiteUrl")
    social_nodes = (node.get("socialAccounts") or {}).get("nodes") or []
    if website_url:
        social_nodes = [{"url": website_url}] + social_nodes
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
        # unique identifier and suspiciousness score (triage order)
        "login": node.get("login"),
        "graph_score": 0,
        "substring_score": 0,
        "composite_score": 0,
        
        # pivot attributes
        "emails": emails,
        "name": node.get("name"),
        "socialAccounts": social_accounts,
        
        # Relationship/network evidence
        "relationships": {},
        "organizations": organizations,
        "org_count": len(organizations),
        
        # Additional profile information
        "company": node.get("company"),
        "location": node.get("location"),
        "bio": node.get("description") or node.get("bio"),
        
        # Timestamps and insights for temporal analysis
        "createdAt": node.get("createdAt"),
        "updatedAt": node.get("updatedAt"),
        "timestompedCommits": False,
        **({"isFollowBotter": False} if is_user else {}),
        
        # intermediary data (included for additional context and debugging purposes)
        "substring_matches": 0,
    }

def compare_user_relations(following: Iterable[str], followers: Iterable[str], starred: Iterable[str]) -> Dict[str, str]:
    """
    Inputs: Three lists of user logins: (1) following and (2) follower and (3) logins the target has starred.
    Outputs: Related-user dict uniquely keyed by login with relationship annotations.
    Method: Membership testing and dictionary merging.
    Information (per User): Relation to the Target User ('mutual', 'following', or 'follower').
    """
    following_logins = {login.casefold() for login in following if isinstance(login, str) and login}
    follower_logins = {login.casefold() for login in followers if isinstance(login, str) and login}
    starred_logins = {login.casefold() for login in starred if isinstance(login, str) and login}
    
    # creates a set of all unique logins from following, followers, and starred users to compare against each relationship type sets
    all_logins = following_logins | follower_logins | starred_logins
    
    relations = {}
    
    # membership testing (relationship comparisons)
    for login in all_logins:
        if login in following_logins and login in follower_logins:
            relationship = "mutual"
            
        elif login in following_logins:
            relationship = "following"
            
        elif login in follower_logins:
            relationship = "follower"
            
        else:
            relationship = "starred"
        
        if login in starred_logins and relationship != "starred":
            relationship += " and starred"
        
        # add login:relationship pair to relations dictionary
        relations[login] = relationship
    
    return relations

def user_commit_history(token: str, results: list[dict]) -> list[dict]: # enrichment function
    """
    Inputs: GitHub Personal Access Token and a list of User dicts
    Outputs: List of User dicts with head and tail commit history enrichment
    Method: GitHub REST API search endpoint
    Information (per User): Email, Timestomped Commits? (bool)
    """
    # calculate batch sizes for use in queries
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
        
        # fetch repository-commit pairs for each user in the batch using a GraphQL query
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
            
            # extract owner login and repository names, and branch names
            for repository in v["repositories"]["nodes"]:
                user, repo = repository["nameWithOwner"].split("/", 1)
                default_branch = repository.get("defaultBranchRef") or {}
                
                if not default_branch: # empty repositories can return None for defaultBranchRef
                    continue
                
                # extract the commit OID
                commit_oid = default_branch["target"]["oid"]
                
                # checks to see if the user already exists.
                for existing_user, repositories in repo_commit_pairs_by_user:
                    if existing_user == user:
                        repositories[repo] = commit_oid
                        break
                
                else:
                    repo_commit_pairs_by_user.append((user, {repo: commit_oid}))
        # --
        
        total_enriched_records += len(repo_commit_pairs_by_user)
        
        # provide batch progress updates only when multiple users are processed together.
        if len(logins) > 1 and repo_commit_pairs_by_user:
            print(f"Batch {i // user_count + 1}: {len(repo_commit_pairs_by_user)} user records harvested. Total enriched records: {total_enriched_records}")
        
        # provide batch progress updates when no repository-commit pairs are identified
        elif not repo_commit_pairs_by_user:
            if len(logins) > 1:
                print(f"Batch {i // user_count + 1}: No repository-commit pairs found, skipping.")
            continue
        # --
        
        # perform a second GraphQL query to retrieve commit metadata for each repository-commit pair
        committer_query = queries.graphql_commit_enrichment_query_2(repo_commit_pairs_by_user)
        committer_results = client.graphql_request(token, committer_query)
        
        if committer_results.get("errors"):
            raise RuntimeError(f"GraphQL error: {committer_results['errors']}")
        
        # extract the commit metadata from the GraphQL response
        committer_results = committer_results.get("data", {})
        
        # enumerates owners and accesses their repository data
        for i, (owner, repositories) in enumerate(repo_commit_pairs_by_user):
            result_user = results_by_login.get(owner.casefold())
            
            if result_user is None:
                continue
            
            # retrieves and normalizes the user's email addresses, ensuring they are stored as a set
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
                
                # skip commits where the committer login does not match the owner login
                if not committer_login or committer_login.casefold() != owner.casefold():
                    continue
                
                # checks to exclude invalid or ignored email addresses
                email = committer.get("email")
                normalized_email = email.casefold() if email else ""
                
                # adds normalized email to the user's email set if it is valid and not in the ignore list
                if email and not any(
                    substring in normalized_email
                    for substring in ignore_email_substrings
                ):
                    emails.add(normalized_email)
                
                # retrieves commit timestamps to facilitate timestomped commit detection
                authored_date = commit.get("authoredDate")
                committed_date = commit.get("committedDate")
                created_at = result_user.get("createdAt")
                
                # check for commits with forged commit timestamps
                if (
                    (committed_date and created_at and committed_date < created_at)
                    or (authored_date and committed_date and committed_date < authored_date)
                ):
                    result_user["timestompedCommits"] = True
    
    return results

def build_relationship_graph(results: list[dict]) -> nx.DiGraph:
    """
    Inputs: List of User dicts (targets and related users)
    Outputs: Directed graph where each edge represents an outbound relationship (follow or starred repository) from source to target
    Method: Converts each user's relationship labels into correctly directed, weighted edges
    """
    relationship_scores = config.relationship_scores
    graph = nx.DiGraph()
    
    # precompute a set of all recorded logins to facilitate relationship inference for users with no direct record in the results
    recorded_logins = {
        login.casefold()
        for user in results
        if isinstance((login := user.get("login")), str) and login.strip()
    }
    
    # iterate over each user in the results to build a directed graph user relationships
    for user in results:
        login = (user.get("login") or "").casefold()
        if not login:
            continue
        
        graph.add_node(login)
        
        starred_users = user.get("starred_users") or {}
        relationships = user.get("relationships") or {}
        for related_login, relation in relationships.items():
            related_login = related_login.casefold()
            
            # account for starred relationships and degree of interaction
            starred_degree = starred_users.get(related_login, 0)
            if starred_degree:
                starred_weight = relationship_scores.get("starred", 0) * math.log1p(starred_degree)
            else:
                starred_weight = 0
            # --
            
            # converts relationships values into correctly directed edges
            if "following" in relation:
                base_weight = relationship_scores.get("following", 1)
                edge_updates = [(login, related_login, base_weight + starred_weight)]
            
            elif "follower" in relation:
                # If the follower has no record, infer their following relationship from this user's record.
                inferred_relationship = (
                    "following" if related_login not in recorded_logins else "follower"
                )
                base_weight = relationship_scores.get(inferred_relationship, 1)
                edge_updates = [(related_login, login, base_weight)]
                if starred_degree:
                    # creates an outbound edge if the related user has starred this user's repositories
                    edge_updates.append((login, related_login, base_weight + starred_weight))
            
            elif "mutual" in relation:
                base_weight = relationship_scores.get("mutual", 1)
                edge_updates = [
                    (login, related_login, base_weight + starred_weight), # outbound edge
                    (related_login, login, base_weight), # inbound edge
                ]
            
            elif relation == "starred":
                edge_updates = [(login, related_login, starred_weight)]
            
            else:
                continue
            # --
            
            # add edges to the graph, updating weights if the new weight is greater than the existing weight
            for source, target, weight in edge_updates:
                existing_weight = graph.get_edge_data(source, target, {}).get("weight", 0)
                if weight > existing_weight:
                    graph.add_edge(source, target, weight=weight)
    
    return graph

def guilt_by_association_scores(
    graph: nx.DiGraph,
    bad_logins: set,
    alpha: float = config.graph_pagerank_alpha,
) -> dict:
    """
    Inputs: Relationship graph and set of blacklisted logins
    Outputs: Dict of login -> reverse personalized PageRank score (proximity to accounts following blacklisted accounts across n-hop paths)
    Method: Reverse Personalized PageRank (RPPR) seeded on blacklisted logins present in the reversed relationship graph
    Information (per User): Guilt-by-association score (likelihood of being clustered with blacklisted users)
    """
    seed_nodes = [login for login in bad_logins if login in graph]
    if not seed_nodes: # no blacklisted accounts reachable in this graph, nothing to propagate
        return {}
    
    # creates a personalization dictionary for the PageRank algorithm
    personalization = {login: 1 for login in seed_nodes}
    
    # reverses the graph to compute guilt-by-association scores based on proximity to blacklisted accounts
    reverse_graph = graph.reverse(copy=False)
    
    return nx.pagerank(reverse_graph, alpha=alpha, personalization=personalization, weight="weight")

def scoring_battery(results: list[dict]) -> list[dict]:
    """
    Inputs: List of User dicts
    Outputs: List of User dicts with score (likelihood of being clustered with the activity set selectors in .config) added
    Method: Inclusion testing against blacklisted and suspicious indicators and link analysis.. 
    Information (per User): Scores
    """
    # retrieve scoring weights and blacklists from config.py
    bad_match = config.bad_match
    bad_logins = {login.casefold() for login in config.BAD_LOGINS}
    
    # retrieve validation emails from config.py
    validation_emails = {
        email.strip().casefold()
        for email in config.VALIDATION_SET_EMAILS
        if isinstance(email, str) and email.strip()
    }
    
    # retrieve blacklisted emails from config.py and exclude intersection with validation emails
    bad_emails = {
        email.casefold() for email in config.BAD_EMAILS
    } - validation_emails
    
    # retrieve suspicious patterns from config.py
    suspicious_patterns = config.SUSPICIOUS_PATTERNS
    
    # build the full relationship graph once and compute guilt-by-association scores for every reachable login
    graph = build_relationship_graph(results)
    pagerank_alphas = sorted(set(config.graph_pagerank_alphas) | {config.graph_pagerank_alpha})
    graph_scores_by_alpha = {
        alpha: guilt_by_association_scores(graph, bad_logins, alpha)
        for alpha in pagerank_alphas
    }
    
    scoring_graph_scores = graph_scores_by_alpha[config.graph_pagerank_alpha]
    page_rank_values = list(scoring_graph_scores.values())
    page_rank_minimum = min(page_rank_values, default=0)
    page_rank_maximum = max(page_rank_values, default=0)
    page_rank_range = page_rank_maximum - page_rank_minimum
    
    # precount pattern matches for login, full name, and non-validation emails (for eventual scoreY assignment).
    substring_match_counts = []
    
    for user in results:
        login = user.get("login").casefold() if isinstance(user.get("login"), str) else ""
        fullname = user.get("name").casefold() if isinstance(user.get("name"), str) else ""
        
        # retrieve and normalize the user's email addresses, excluding validation emails
        raw_emails = user.get("emails") or []
        if isinstance(raw_emails, str):
            raw_emails = [raw_emails]
        
        emails = [
            email.casefold()
            for email in raw_emails
            if isinstance(email, str) and email.strip().casefold() not in validation_emails
        ]
        
        searchable_values = [login, fullname, *emails]
        
        # count each suspicious pattern at most once per searchable value
        match_count = sum(
            pattern.search(value) is not None
            for pattern in suspicious_patterns
            for value in searchable_values
        )
        substring_match_counts.append(match_count)
    
    # determine the maximum number of suspicious substring matches across all users (used for linear scaling of match counts)
    max_substring_matches = max(substring_match_counts, default=0)
    
    # check user values and score based on matches and corresponding weights
    for i, user in enumerate(results):
        login = (user.get("login") or "").casefold()
        
        # build the list of emails for the user, excluding validation emails
        emails = [
            email.casefold()
            for email in user.get("emails", set())
            if isinstance(email, str) and email.casefold() not in validation_emails
        ]
        
        print(f"Scoring user {i + 1} of {len(results)}: {login}")
        
        # retrieve the number of suspicious pattern matches for this user
        substring_matches = substring_match_counts[i]
        
        # assign linearly scaled substring match count score to each user based on their count relative to the max substring match count
        scaled_substring_matches = (
            bad_match * (substring_matches / max_substring_matches) # omits floor values because floor = 0
            if max_substring_matches
            else 0
        )
        
        # assign substring match values
        user["substring_matches"] = substring_matches
        user["substring_score"] = scaled_substring_matches # y-axis component of composite score
        
        for alpha, graph_scores in graph_scores_by_alpha.items():
            user[f"pagerank_alpha_{alpha:g}"] = graph_scores.get(login, 0)
        
        normalized_graph_score = 0 # initialize normalized graph score to 0 (edge case handling)
        
        # assigns guilt-by-association score based on PageRank within the relationship graph relative to the maximum and minimum PageRank values
        ## guilt-by-association score: proximity to blacklisted accounts across the n-hop relationship graph
        if page_rank_range > 0:
            graph_score = scoring_graph_scores.get(login, page_rank_minimum)
            
            # social network analysis component of user scoring (x-axis)
            normalized_graph_score = bad_match * (graph_score - page_rank_minimum) / page_rank_range
            # print(f"User {login} guilt-by-association PageRank score: {graph_score:.6f}")
        
        # assign max score for known malicious login/email matches
        if login in bad_logins or any(email in bad_emails for email in emails):
            print(f"User {login} matched blacklisted login or email")
            normalized_graph_score = bad_match # assign maximum score for known malicious matches (override any previous score)
        
        # assign linearly scaled graph (guilt-by-association) score to each user based on their proportional raw graph scores
        user["graph_score"] = normalized_graph_score # x-axis component of composite score
        
        # eigenvector-like composite score based on x and y components
        composite_score = math.sqrt(normalized_graph_score**2 + user["substring_score"]**2)
        
        # scaled composite score (optional normalization or further scaling can be applied here if needed)
        scaled_composite_score = bad_match * (composite_score / math.sqrt(bad_match**2 + bad_match**2))
        ## as long as bad_match = 100, formula can be represented as composite_score / math.sqrt(2)
        
        user["composite_score"] = scaled_composite_score
    
    return results

def validation_email_metrics(results: list[dict]) -> dict[str, int | float | None]:
    """
    Inputs: List of User dicts (results)
    Outputs: Dictionary containing validation coverage, ranking, precision, and recall metrics
    Method: Compare ranked user records against held-out validation logins and emails
    Information (per User): Whether the user's login or emails match held-out validation labels
    Ranking metrics exclude blacklisted accounts from their candidate lists.
    """
    # validation logins and emails for comparison against the results
    validation_logins = {
        login.strip().casefold()
        for login in config.VALIDATION_SET_LOGINS
        if isinstance(login, str) and login.strip()
    }
    
    # blacklist logins for exclusion from validation metrics
    blacklist_logins = {
        login.strip().casefold()
        for login in config.BAD_LOGINS
        if isinstance(login, str) and login.strip()
    }
    
    # blacklist logins and emails for exclusion from validation metrics
    blacklist_emails = {
        email.strip().casefold()
        for email in config.BAD_EMAILS
        if isinstance(email, str) and email.strip()
    }
    
    # subtract blacklisted emails from validation emails to ensure overlaps count only as blacklist records
    validation_emails = {
        email.strip().casefold()
        for email in config.VALIDATION_SET_EMAILS
        if isinstance(email, str) and email.strip()
    } - blacklist_emails
    
    # checks whether any validation labels remain after excluding blacklisted emails
    validation_labels_exist = bool(validation_logins or validation_emails)
    
    # if there are no validation labels, return early with default metrics
    if not validation_labels_exist:
        return {
            "validation_emails_total": 0,
            "validation_emails_found": 0,
            "validation_email_coverage": None,
            "validation_logins_total": 0,
            "validation_logins_found": 0,
            "validation_positive_accounts_found": 0,
            "validation_average_precision": None,
            "validation_recall_k": 0,
            "validation_recall_at_k": None,
            "validation_mean_reciprocal_rank": None,
        }
    
    # organize users by their login for quick lookup
    users_by_login = {}
    for user in results:
        login = user.get("login")
        
        if isinstance(login, str) and login.strip():
            users_by_login[login.casefold()] = user
    
    # prepare eligible ranking candidates and track validation labels represented in the records
    candidates = []
    found_emails = set()
    found_logins = set()
    
    # iterate over users and collect matched validation emails and their scores
    for login, user in users_by_login.items():
        raw_emails = user.get("emails") or []
        
        if isinstance(raw_emails, str):
            raw_emails = [raw_emails]
        
        # normalize and clean user emails for comparison with validation set
        user_emails = {
            email.strip().casefold()
            for email in raw_emails
            if isinstance(email, str) and email.strip()
        }
        
        # determine which of the user's emails match the validation set
        matched_emails = user_emails & validation_emails
        found_emails.update(matched_emails)
        
        # determine if the user's login matches any held-out validation logins
        if login in validation_logins:
            found_logins.add(login)
        
        # retrieve the user's composite score, defaulting to 0.0 if not present or invalid
        score = user.get("composite_score", 0.0)
        if not isinstance(score, (int, float)):
            score = 0.0
        
        # append the account label along with each candidate's login, score, and matched emails
        is_validation_account = login in validation_logins or bool(matched_emails)
        graph_score = user.get("graph_score", 0.0)

        # exclude known bad accounts from every ranking metric
        if login in blacklist_logins or user_emails.intersection(blacklist_emails):
            continue

        # exclude isolated validation users to avoid distorting evaluation metrics
        if is_validation_account and graph_score == 0:
            continue

        candidate = (login, float(score), matched_emails, is_validation_account)
        candidates.append(candidate)
    
    # compute labels and scores for evaluation metrics
    labels = [is_validation_account for _, _, _, is_validation_account in candidates]
    scores = [score for _, score, _, _ in candidates]
    
    # compute the average precision score if there are both positive and negative labels
    average_precision = (
        average_precision_score(labels, scores)
        if any(labels) and not all(labels)
        else None
    )
    
    # rank candidates by composite score, using login as a deterministic tie-breaker
    ranked_candidates = sorted(candidates, key=lambda item: (-item[1], item[0]))
    relevant_account_count = sum(labels)
    top_k = ranked_candidates[:relevant_account_count]

    # A-MRR uses the same blacklist-filtered candidate pool as the other ranking metrics
    mrr_relevant_account_count = relevant_account_count

    # calculate reciprocal rank for each eligible validation account record
    reciprocal_rank_total = sum(
        1 / rank
        for rank, candidate in enumerate(ranked_candidates, start=1)
        if candidate[3]
    )
    mean_reciprocal_rank = (
        reciprocal_rank_total / mrr_relevant_account_count
        if mrr_relevant_account_count
        else None
    )
    
    return {
        "validation_emails_total": len(validation_emails),
        "validation_emails_found": len(found_emails),
        "validation_email_coverage": (
            len(found_emails) / len(validation_emails)
            if validation_emails
            else None
        ),
        "validation_logins_total": len(validation_logins),
        "validation_logins_found": len(found_logins),
        "validation_positive_accounts_found": relevant_account_count,
        "validation_average_precision": average_precision,
        "validation_recall_k": relevant_account_count,
        "validation_recall_at_k": (
            sum(candidate[3] for candidate in top_k) / relevant_account_count
            if relevant_account_count
            else None
        ),
        "validation_mean_reciprocal_rank": mean_reciprocal_rank,
    }

def validation_metrics_by_alpha(results: list[dict]) -> dict[float, dict[str, int | float | None]]:
    """Calculate validation metrics using a composite score generated for each PageRank alpha."""
    pagerank_alphas = sorted(set(config.graph_pagerank_alphas) | {config.graph_pagerank_alpha})
    bad_match = config.bad_match
    bad_logins = {login.casefold() for login in config.BAD_LOGINS}
    validation_emails = {
        email.strip().casefold()
        for email in config.VALIDATION_SET_EMAILS
        if isinstance(email, str) and email.strip()
    }
    
    # subtract blacklisted emails from validation emails to ensure overlaps count only as blacklist records
    bad_emails = {email.casefold() for email in config.BAD_EMAILS} - validation_emails
    
    # build the relationship graph once and compute guilt-by-association scores for every reachable login
    graph = build_relationship_graph(results)
    metrics_by_alpha = {}
    
    # iterate over each PageRank alpha value to compute guilt-by-association scores and validation metrics
    for alpha in pagerank_alphas:
        graph_scores = guilt_by_association_scores(graph, bad_logins, alpha)
        graph_values = list(graph_scores.values())
        graph_minimum = min(graph_values, default=0)
        graph_range = max(graph_values, default=0) - graph_minimum
        alpha_results = []
        
        # iterate over each user in the results to compute their graph score, substring score, and composite score
        for user in results:
            login = user.get("login")
            normalized_login = login.casefold() if isinstance(login, str) else ""
            
            # linearly scale the graph score based on the user's PageRank score relative to the minimum and maximum scores
            graph_score = (
                bad_match
                * (graph_scores.get(normalized_login, graph_minimum) - graph_minimum)
                / graph_range
                if graph_range > 0
                else 0
            )
            
            # retrieve the user's email address(es)
            raw_emails = user.get("emails") or []
            
            if isinstance(raw_emails, str):
                raw_emails = [raw_emails]
            
            # normalize and clean user emails for comparison with validation set, excluding validation emails
            user_emails = {
                email.casefold()
                for email in raw_emails
                if isinstance(email, str) and email.casefold() not in validation_emails
            }
            
            # assign the maximum score for known malicious login/email matches, overriding any previous graph score
            if normalized_login in bad_logins or user_emails & bad_emails:
                graph_score = bad_match
            
            # compute the composite score based on the graph score and substring score, ensuring both are numeric
            substring_score = user.get("substring_score")
            
            if not isinstance(substring_score, (int, float)):
                raise ValueError(
                    "Stored user records must have numeric substring_score values; "
                    "run score_users() before validating."
                )
            
            # compute the composite score as the Euclidean distance for axes (x: graph_score, y: substring_score)
            composite_score = math.sqrt(graph_score**2 + substring_score**2)
            
            # compute the final, scored user record
            scored_user = user.copy()
            scored_user["graph_score"] = graph_score
            scored_user["composite_score"] = bad_match * (
                composite_score / math.sqrt(bad_match**2 + bad_match**2)
            )
            
            # append the scored user record to the list for this alpha value
            alpha_results.append(scored_user)
        
        # compute validation metrics for the scored user records at this alpha value
        metrics_by_alpha[alpha] = validation_email_metrics(alpha_results)
    
    return metrics_by_alpha

def score_and_validate_user_results(
    search_results: list[dict],
    stored_records: Iterable[dict],
) -> tuple[list[dict], dict[str, int | float | None]]:
    """
    Inputs: List of User dicts obtained from the search and User dicts retrieved from the database (users table)
    Outputs: Tuple containing the scored search results and a dictionary of validation metrics
    Method: Score the union of search results and stored records using the scoring battery, then compute validation metrics based on held-out validation emails.
    Information (per User): Whether the user's emails match any held-out validation emails
    """
    candidates_by_login = {} # dictionary to store candidates keyed by their login (case-insensitive)
    
    # populate the candidates_by_login dictionary with stored records first, then with search results (overwrites existing records on match)
    for record in stored_records:
        login = record.get("login")
        
        if isinstance(login, str) and login.strip():
            candidates_by_login[login.casefold()] = record
    
    for record in search_results:
        login = record.get("login")
        if isinstance(login, str) and login.strip():
            candidates_by_login[login.casefold()] = record
    
    # score the combined candidates using the scoring battery and compute validation metrics
    scored_candidates = scoring_battery(list(candidates_by_login.values()))
    validation_metrics = validation_email_metrics(scored_candidates)
    
    # create a dictionary of scored candidates keyed by their login for easy lookup
    scored_by_login = {
        record["login"].casefold(): record
        for record in scored_candidates
        if isinstance(record.get("login"), str)
    }
    
    # map the scored candidates back to the original search results to maintain order and include any missing fields
    scored_search_results = [
        scored_by_login.get(record["login"].casefold(), record)
        if isinstance(record.get("login"), str)
        else record
        for record in search_results
    ]
    
    return scored_search_results, validation_metrics