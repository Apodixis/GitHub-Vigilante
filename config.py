# Used in score calculation for identifying malicious and likely malicious accounts for triage

# SCORE WEIGHTING VARIABLES
bad_match = 100
suspicious_match_weight = 20

bad_following_weight = 5
bad_follower_weight = 10
bad_mutual_weight = 20
bad_degree_weight = 10

relationship_scores = {
    "following": bad_following_weight,
    "follower": bad_follower_weight,
    "mutual": bad_mutual_weight
}

# personalized PageRank ("guilt-by-association") settings for relationship graph scoring
graph_pagerank_alpha = 0.85 # standard / default damping factor for PageRank
graph_pagerank_weight = bad_match ** 2  # ties the 0-1 PageRank score to the same ceiling as a direct blacklist match
# --

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