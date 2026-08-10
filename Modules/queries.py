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
    query getAllUserInformation($pageSize: Int = 100, $socialSize: Int = 10, $followingCursor: String, $followersCursor: String) {{
        user(login: {login_literal}) {{
            login createdAt name email company location bio
            socialAccounts(first: $socialSize) {{
                nodes {{ url }}
            }}
            organizations(first: $pageSize) {{
                totalCount
                nodes {{ login }}
            }}
            following(first: $pageSize, after: $followingCursor) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                    login createdAt name email company location bio
                    socialAccounts(first: $socialSize) {{
                        nodes {{ url }}
                    }}
                    organizations(first: $pageSize) {{
                        nodes {{ login }}
                    }}
                }}
            }}
            followers(first: $pageSize, after: $followersCursor) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                    login createdAt name email company location bio
                    socialAccounts(first: $socialSize) {{
                        nodes {{ url }}
                    }}
                    organizations(first: $pageSize) {{
                        nodes {{ login }}
                    }}
                }}
            }}
        }}
    }}
"""

def graphQL_build_partial_user_query(user_logins):
    """
    Inputs: Target User login.
    Outputs: GraphQL User query string.
    Method: Variable insertion format string, iterative query development.
    """
    query = f"""query partialUserQuery {{
"""

    for i, user in enumerate(user_logins):
        userIndex = str(i)
        query += f"""   user{userIndex}: user(login: "{user}") {{
            login createdAt name email company location bio
            socialAccounts(first: 10) {{
                nodes {{ url }}
                }}
            }}"""
    
        query = query.replace('{{', '{').replace('}}', '}') # Escape braces for f-string
        query += "}"
    
    return query