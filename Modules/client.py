import requests, time, re
from collections import deque
from typing import Dict, Optional, Any

import Modules.state as state # access global state variables like authorized_login

"""
Central location for sending HTTP requests and handling response contents
"""

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

def _user_agent() -> Dict[str, str]:
    # built per-request (not at import time) so it reflects state.authorized_login once it's set after token validation
    return {"user-agent": f"GitHub-Vigilante (user: {state.authorized_login})"}

# Variable declarations for rate limit safeguards
max_requests_per_minute = 20 # conservative request limit to avoid GitHub's unpredictable secondary rate limits
rate_limit_window = 60.0
request_delay = rate_limit_window / max_requests_per_minute
_request_times: deque[float] = deque(maxlen=max_requests_per_minute)
# --

def _wait_for_rest_window() -> None: # helper function
    '''
    Safety measure that prevents exceeding the REST API rate limit by enforcing a sliding request window.
    '''
    # REST API rate limit handling (prevents exceeding 30 requests per minute)
    now = time.monotonic()
    
    while _request_times and (now - _request_times[0] >= rate_limit_window):
        _request_times.popleft()
    
    if len(_request_times) >= max_requests_per_minute:
        delay = rate_limit_window - (now - _request_times[0])
        time.sleep(max(delay, 0))
        
        now = time.monotonic()
        
        while _request_times and (now - _request_times[0] >= rate_limit_window):
            _request_times.popleft()
    
    if _request_times:
        delay = request_delay - (now - _request_times[-1])
        if delay > 0:
            time.sleep(delay)
            now = time.monotonic()
    
    _request_times.append(now)

def graphql_request(token: str, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Inputs: GitHub Personal Access Token, GraphQL query, and optional query variables
    Outputs: Decoded JSON response payload (data and/or errors)
    Method: GraphQL API POST request with the shared rate-limit throttle and retry-on-failure handling
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} | _user_agent()
    body: Dict[str, Any] = {"query": query}
    if variables is not None:
        body["variables"] = variables
    
    # up to three requests (initial + 2 retries) for resiliency
    for attempt in range(3):
        # Apply the shared sliding-window throttle before each request attempt.
        _wait_for_rest_window()
        try:
            response = requests.post(GITHUB_GRAPHQL_URL, json=body, headers=headers, timeout=(20, 60))
        except requests.exceptions.RequestException as error:
            if attempt < 2:
                print(f"GraphQL request failed: {error}. Retrying.")
                continue
            
            print(f"GraphQL request failed after 3 attempts: {error}")
            raise
        
        if response.status_code not in (403, 429):
            response.raise_for_status()
            return response.json()
        
        reset_value = response.headers.get("X-RateLimit-Reset")
        retry_after = response.headers.get("Retry-After")
        
        if retry_after:
            try:
                delay = max(float(retry_after), 0)
            except ValueError:
                delay = rate_limit_window
        else:
            if not reset_value:
                reset_match = re.search(
                    r"Rate limit resets at Unix timestamp:\s*(\d+(?:\.\d+)?)",
                    response.text,
                    flags=re.IGNORECASE,
                )
                reset_value = reset_match.group(1) if reset_match else None
            
            if reset_value:
                try:
                    delay = max((float(reset_value) + request_delay) - time.time(), 0) # waits 2 more seconds past the reset time
                except ValueError:
                    delay = rate_limit_window
            else:
                delay = rate_limit_window
        
        if attempt == 2:
            print(f"GitHub rate-limited the GraphQL request with status {response.status_code}.")
            print(f"Response: {response.text}")
            response.raise_for_status()
        
        print(f"GitHub rate-limited the GraphQL request. Retrying in {delay:.1f} seconds.")
        time.sleep(delay)
    
    raise RuntimeError("GraphQL request failed after rate-limit retries.")

#============================================================================================

def rest_request(token: str, url: str, params: Optional[Dict] = None) -> Any:
    """
    Inputs: GitHub Personal Access Token, base REST API URL, and query parameters
    Outputs: Decoded JSON response body (Results)
    Method: REST API request with token authorization
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"} | _user_agent()
    
    # up to three requests (initial + 2 retries) for resiliency
    for attempt in range(3):
        # Apply the shared sliding-window throttle before each request attempt.
        _wait_for_rest_window()
        try:
            response = requests.get(url, headers=headers, params=params, timeout=(20, 20))
        except requests.exceptions.RequestException as error:
            if attempt < 2:
                print(f"Request failed for {url}: {error}. Retrying.")
                continue
            
            print(f"Request failed after 3 attempts for {url}: {error}")
            return {
                "total_count": 0,
                "items": [],
            }
        
        if response.status_code == 422: # catches queries for users with no public commits
            print(f"GitHub rejected the commit search: {response.url}")
            return {
                "total_count": 0,
                "items": []
            }
        
        if response.status_code not in (403, 429):
            response.raise_for_status()
            return response.json()
        
        reset_value = response.headers.get("X-RateLimit-Reset")
        retry_after = response.headers.get("Retry-After")
        
        if retry_after:
            try:
                delay = max(float(retry_after), 0)
            except ValueError:
                delay = rate_limit_window
        else:
            if not reset_value:
                reset_match = re.search(
                    r"Rate limit resets at Unix timestamp:\s*(\d+(?:\.\d+)?)",
                    response.text,
                    flags=re.IGNORECASE,
                )
                reset_value = reset_match.group(1) if reset_match else None
            
            if reset_value:
                try:
                    delay = max((float(reset_value) + request_delay) - time.time(), 0) # waits 2 more seconds past the reset time
                except ValueError:
                    delay = rate_limit_window
            else:
                delay = rate_limit_window
        
        if attempt == 2:
            print(f"GitHub rate-limited the request with status {response.status_code}.")
            print(f"Response: {response.text}")
            response.raise_for_status()
        
        print(f"GitHub rate-limited the request. Retrying in {delay:.1f} seconds.")
        time.sleep(delay)
    
    raise RuntimeError("REST request failed after rate-limit retries.")