import requests, time, re
from collections import deque
from typing import Dict, Optional, Any

import Modules.state as state # access global state variables

"""
Central location for sending HTTP requests and handling response contents
"""

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

def _user_agent() -> Dict[str, str]:
    # built per-request (not at import time) so it reflects state.authorized_login once it's set after token validation
    return {"user-agent": f"GitHub-Vigilante (user: {state.authorized_login})"}

# variable declarations for rate limit safeguards
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

def _rate_limit_delay(response) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0)
        except ValueError:
            return rate_limit_window
    
    reset_value = response.headers.get("X-RateLimit-Reset")
    if not reset_value:
        reset_match = re.search(
            r"Rate limit resets at Unix timestamp:\s*(\d+(?:\.\d+)?)",
            response.text,
            flags=re.IGNORECASE,
        )
        reset_value = reset_match.group(1) if reset_match else None
    
    if reset_value:
        try:
            return max((float(reset_value) + request_delay) - time.time(), 0)
        except ValueError:
            return rate_limit_window
    
    return rate_limit_window

def _is_graphql_rate_limited(payload: Dict[str, Any]) -> bool:
    return any(
        (error.get("type") or "").upper() in {"RATE_LIMITED", "RATE_LIMIT_EXCEEDED"}
        or "rate limit" in (error.get("message") or "").casefold()
        for error in payload.get("errors", [])
        if isinstance(error, dict)
    )

def _request_with_backoff(request_fn, url: str, service_name: str, **kwargs):
    retry_number = 0
    transient_statuses = {500, 502, 503, 504}
    
    while True:
        _wait_for_rest_window()
        try:
            response = request_fn(url, **kwargs)
        except requests.exceptions.SSLError:
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
            retry_number += 1
            delay = min(20.0 * (2 ** min(retry_number - 1, 7)), 120.0)
            print(f"{service_name} request failed: {error}. Retrying in {delay:.1f} seconds.")
            time.sleep(delay)
            continue
        
        if response.status_code in (403, 429):
            delay = _rate_limit_delay(response)
            print(
                f"{service_name} endpoint rate-limited with status {response.status_code}. "
                f"Retrying in {delay:.1f} seconds."
            )
            response.close()
            time.sleep(delay)
            continue
        
        if response.status_code in transient_statuses:
            retry_number += 1
            delay = min(20.0 * (1.5 ** min(retry_number - 1, 7)), 120.0)
            print(
                f"{service_name} endpoint returned {response.status_code}. "
                f"Retrying in {delay:.1f} seconds."
            )
            response.close()
            time.sleep(delay)
            continue
        
        return response

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
    
    retry_attempt = 0
    while True:
        try:
            response = _request_with_backoff(
                requests.post,
                GITHUB_GRAPHQL_URL,
                "GraphQL",
                json=body,
                headers=headers,
                timeout=(20, 60),
            )
        except requests.exceptions.RequestException as error:
            retry_attempt += 1
            if retry_attempt < 3:
                print(f"GraphQL request failed: {error}. Retrying.")
                continue
            
            print(f"GraphQL request failed after 3 attempts: {error}")
            raise
        
        response.raise_for_status()
        
        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError as error:
            retry_attempt += 1
            if retry_attempt >= 3:
                print(f"GraphQL response body could not be decoded after 3 attempts: {error}")
                raise
            
            delay = request_delay * retry_attempt # brief backoff for a malformed/empty response body
            print(f"GraphQL response body was empty or malformed. Retrying in {delay:.1f} seconds.")
            time.sleep(delay)
            continue
        
        if _is_graphql_rate_limited(payload):
            delay = _rate_limit_delay(response)
            print(f"GraphQL response reported a rate limit. Retrying in {delay:.1f} seconds.")
            response.close()
            time.sleep(delay)
            continue
        
        return payload

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
        try:
            response = _request_with_backoff(
                requests.get,
                url,
                "REST",
                headers=headers,
                params=params,
                timeout=(20, 20),
            )
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
        
        response.raise_for_status()
        return response.json()
    
    raise RuntimeError("REST request failed after rate-limit retries.")