from Modules.queries import graphQL_user_exact_query
from Modules.requests import user_exact_request

def user_search_exact(token: str, target_user: str) -> list[dict]: # Add user selection before return prompting for enrichment.
    """
    Inputs: GitHub username (login) and personal access token.
    Outputs: Target user profile dict w/ followership relationships added.
    Method: GitHub GraphQL API with pagination.
    Information (per User): Login, Name, Email, Bio, Location, Company, socialAccounts URLs.
    """
    query = graphQL_user_exact_query(target_user) # Fetch the GraphQL query string
    
    target_user, followership = user_exact_request(token, query, target_user)
    return [target_user] + followership # Concatenate user dict with followership list of dicts and return as a single list of dicts