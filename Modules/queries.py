import json
"""
Central location for GraphQL and REST API query strings used in in requests.
"""
# Query for GitHub user information, including followership and social accounts
## DESIGN_NOTE: Potential Optimization - Omit Organization Info for follower/following in the initial user query, then build a batched user org query from the merged followership set.

def graphQL_user_exact_query(login) -> str:
    """
    Inputs: Target User login.
    Outputs: GraphQL User query string.
    Method: Variable insertion format string.
    """
    login_literal = json.dumps(login) # Ensure login is properly escaped for GraphQL query
    return f"""
    query userExactSearch($page_size: Int = 100, $social_size: Int = 10, $following_cursor: String, $followers_cursor: String) {{
        user(login: {login_literal}) {{
            login createdAt updatedAt name email company location bio
            socialAccounts(first: $social_size) {{
                nodes {{ url }}
            }}
            organizations(first: $page_size) {{
                totalCount
                nodes {{ login }}
            }}
            following(first: $page_size, after: $following_cursor) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                    login createdAt updatedAt name email company location bio
                    socialAccounts(first: $social_size) {{
                        nodes {{ url }}
                    }}
                    organizations(first: $page_size) {{
                        nodes {{ login }}
                    }}
                }}
            }}
            followers(first: $page_size, after: $followers_cursor) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                    login createdAt updatedAt name email company location bio
                    socialAccounts(first: $social_size) {{
                        nodes {{ url }}
                    }}
                    organizations(first: $page_size) {{
                        nodes {{ login }}
                    }}
                }}
            }}
        }}
    }}
"""

def graphQL_user_partial_query(login) -> str:
    """
    Inputs: Target user search string.
    Outputs: GraphQL user search query string.
    Method: Variable insertion format string.
    """
    search_literal = json.dumps(login) # Ensure login is properly escaped for GraphQL query
    return f"""
    query userPartialSearch($page_size: Int = 100, $social_size: Int = 10, $cursor: String) {{
        search(query: {search_literal}, type: USER, first: $page_size, after: $cursor) {{
            pageInfo {{ hasNextPage endCursor }}
            nodes {{
                ... on User {{
                    login createdAt updatedAt name email company location bio
                    socialAccounts(first: $social_size) {{
                        nodes {{ url }}
                    }}
                    organizations(first: $page_size) {{
                        nodes {{ login }}
                    }}
                }}
            }}
        }}
    }}
"""

#============================================================================================

def graphQL_organizations_exact_query(orgLogin: str) -> str:
    """
    Inputs: Target Organization login.
    Outputs: GraphQL Organization query string.
    Method: Variable insertion format string.
    """
    orgLogin_literal = json.dumps(orgLogin) # Ensure orgLogin is properly escaped for GraphQL query
    return f"""
    query organizationExactSearch($page_size: Int = 100, $members_cursor: String) {{
        organization(login: {orgLogin_literal}) {{
            login createdAt updatedAt name email location isVerified twitterUsername websiteUrl description
            membersWithRole(first: $page_size, after: $members_cursor) {{
                nodes {{
                    login createdAt updatedAt name email company location bio
                    socialAccounts(first: 10) {{
                        nodes {{ url }}
                    }}
                }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}
    }}
"""

#============================================================================================

def graphQL_commit_enrichment_query_1(batch_logins: list[str], repo_count: int) -> str:
    """
    Inputs: One or more User logins and the number of head and tail repositories to fetch per user
    Outputs: GraphQL User query string
    Method: Variable insertion format string, iterative query development
    """
    query = f"""query FindCommitHeadAndTail {{
        """
    
    for i, login in enumerate(batch_logins):
        
        # Error handling for records that do not have an email value
        if not isinstance(login, str) or not login:
            continue
        
        login_literal = json.dumps(login)
        
        i = str(i)
        query += f"""oldestRepos{i}: user(login: {login_literal}) {{
            repositories(
                first: {repo_count}
                orderBy: {{ field: CREATED_AT, direction: ASC }}
                ownerAffiliations: OWNER
                isFork: false
            ) {{
                nodes {{
                    name
                    nameWithOwner
                    defaultBranchRef {{
                        target {{
                            ... on Commit {{ oid }}
                        }}
                    }}
                }}
            }}
        }}
        newestRepos{i}: user(login: {login_literal}) {{
            repositories(
                first: {repo_count}
                orderBy: {{ field: CREATED_AT, direction: DESC }}
                ownerAffiliations: OWNER
                isFork: false
            ) {{
                nodes {{
                    nameWithOwner
                    defaultBranchRef {{
                        target {{
                            ... on Commit {{ oid }}
                        }}
                    }}
                }}
            }}
        }}
    """
    
    query += f"}}"
    return query

def graphQL_commit_enrichment_query_2(repo_commit_pairs_by_user: list[tuple[str, dict[str, str]]]) -> str:
    """
    Inputs: One or more user tuples containing information needed to fetch commit information
    Outputs: GraphQL User query string
    Method: Variable insertion format string, iterative query development
    """
    query = f"""query FetchSpecifiedCommits {{
        """
    
    # enumerates owners and accesses repositories data
    for i, (owner, repositories) in enumerate(repo_commit_pairs_by_user):
        owner_literal = json.dumps(owner)
        
        # enumerates repositories and accesses repo:commit (oid) pairs
        for j, (repo, oid) in enumerate(repositories.items()):
            repo_literal = json.dumps(repo)
            oid_literal = json.dumps(oid)
            
            i, j = str(i), str(j)
            query += f"""owner{i}repo{j}: repository(owner: {owner_literal}, name: {repo_literal}) {{
                object(oid: {oid_literal}) {{
                    ... on Commit {{
                        authoredDate
                        committedDate
                        committer {{
                            user {{ login }}
                            name email
                        }}
                    }}
                }}
            }}
        """
    
    query += f"}}"
    return query