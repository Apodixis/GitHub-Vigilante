import json
"""
Central location for GraphQL query strings used in the project.
"""
# Query for GitHub user information, including followership and social accounts
## DESIGN_NOTE: Query omits organization information for followers and following because they will be used to create a list from their union.
## DESIGN_NOTE: Querying this data later prevents duplicate queries

def graphQL_user_exact_query(login):
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
                }}
            }}
            followers(first: $pageSize, after: $followersCursor) {{
                pageInfo {{ hasNextPage endCursor }}
                nodes {{
                    login createdAt name email company location bio
                    socialAccounts(first: $socialSize) {{
                        nodes {{ url }}
                    }}
                }}
            }}
        }}
    }}
    """