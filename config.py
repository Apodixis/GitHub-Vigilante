# Used in score calculation for identifying malicious and likely malicious accounts for triage

import regex

# SCORE WEIGHTING VARIABLES
bad_match = 100

# weights applied to upstream nodes based on relationship type
BAD_MUTUAL_WEIGHT = 1
BAD_FOLLOWING_WEIGHT = 0.5
BAD_STARRED_WEIGHT = 0.1

# personalized PageRank ("guilt-by-association") settings for relationship graph scoring
graph_pagerank_alpha = 0.85 # optimal damping factor (per case study) to fit matches tighter to blacklisted users
graph_pagerank_alphas = (0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)
# --

relationship_scores = {
    "following": BAD_FOLLOWING_WEIGHT,
    "mutual": BAD_MUTUAL_WEIGHT,
    "starred": BAD_STARRED_WEIGHT
}

FOLLOW_BOT_THRESHOLD = 500 # minimum outbound relationships to consider an user a potential follow bot
FOLLOW_BOT_RATIO = 0.8 # ratio of outbound relationships to consider a user a follow bot (80%)
FOLLOW_BOT_AUTOLABEL = 1000 # if user has more than 1,000 outbound relationships, automatically label as a follow botter

# insert known bad logins here (will flag matched user records as 100% malicious)
## matches are scored 1000/1000 (placeholder) to ensure they have the highest score value
BAD_LOGINS = {
    "login1",
    "login2",
    "login3"
}

# insert known bad emails here (will flag matched user records as 100% malicious)
## matches are scored 100/100
BAD_EMAILS = {
    "badguy@example.com",
    "hackermans@example.com",
    "cybercriminal@example.com"
}

# helper pattern fragments
_text = "pattern"
_suffix = "(@|$)"
_digits = r"(?:(?P<repeated_digit>\d)(?P=repeated_digit){1,2}|\d{3,8})"

# Patterns for use in SUSPICIOUS_LOGIN_PATTERNS
example_pattern1 = rf"{_text}{_digits}{_suffix}"
example_pattern2 = r"[a-zA-Z0-9-]*"

# naming conventions frequently observed in malicious account and email naming conventions
SUSPICIOUS_PATTERNS = tuple(
    regex.compile(pattern, regex.IGNORECASE)
    for pattern in (
        rf"{example_pattern1}",
        rf"{example_pattern2}"
    )
)

# substrings commonly observed in malicious account and email naming conventions
SUSPICIOUS_SUBSTRINGS = {
    "substring1",
    "substring2",
    "substring3"
}

# List of accounts that likely automated follow (or follow-back) interactions
## Association (especially outbound) with follow botters can indicate fraudulent legitimization activity
FOLLOW_BOTTERS = {
    "followBotter1",
    "followBotter2",
    "followBotter3"
}

# List of known malicious user attributes excluded from the blacklist with unknown association to the blacklisted users and emails.
## Used exclusively to validate the performance of the underlying scoring algorithms
VALIDATION_SET_LOGINS = {
    "user1",
    "user2",
    "user3"
}

# List of known malicious user attributes excluded from the blacklist with unknown association to the blacklisted users and emails.
VALIDATION_SET_EMAILS = {
    "test@example.com",
    "validation@example.com",
    "object@example.com"
}