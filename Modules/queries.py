import json
"""
Central location for GraphQL query strings used in the project.
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
    query getAllUserInformation($page_size: Int = 100, $social_size: Int = 10, $following_cursor: String, $followers_cursor: String) {{
        user(login: {login_literal}) {{
            login createdAt name email company location bio
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
                    login createdAt name email company location bio
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
                    login createdAt name email company location bio
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

def graphQL_build_partial_user_query(user_logins) -> str:
    """
    Inputs: Target User login.
    Outputs: GraphQL User query string.
    Method: Variable insertion format string, iterative query development.
    """
    query = f"""query partialUserQuery {{
"""

    for i, login in enumerate(user_logins):
        userIndex = str(i)
        login_literal = json.dumps(login) # Ensure login is properly escaped for GraphQL query
        query += f"""   user{userIndex}: user(login: {login_literal}) {{
            login createdAt name email company location bio
            socialAccounts(first: 10) {{
                nodes {{ url }}
                }}
            }}"""
    query += f"}}"
    
    return query

#============================================================================================

def graphQL_organizations_query(orgLogin: str) -> str:
    """
    Inputs: Target Organization login.
    Outputs: GraphQL Organization query string.
    Method: Variable insertion format string.
    """
    orgLogin_literal = json.dumps(orgLogin) # Ensure orgLogin is properly escaped for GraphQL query
    return f"""
    query getOrganizationInformation($page_size: Int = 100, $members_cursor: String) {{
        organization(login: {orgLogin_literal}) {{
            login createdAt name email location isVerified twitterUsername websiteUrl description
            membersWithRole(first: $page_size, after: $members_cursor) {{
                nodes {{
                    login createdAt name email company location bio
                    socialAccounts(first: 10) {{
                        nodes {{ url }}
                    }}
                }}
                pageInfo {{ hasNextPage endCursor }}
            }}
        }}
    }}
"""