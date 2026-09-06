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