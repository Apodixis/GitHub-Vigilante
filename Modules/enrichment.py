"""Enrich records based on retrieved user data field values."""

import config


def follow_bot_identification(followers: set[str], following: set[str], starred: set[str]) -> dict[str, bool]:
    """Return positive follow-bot labels based on relationship counts and ratio."""
    all_relationships = len(followers) + len(following) + len(starred)
    outbound_relationships = len(following) + len(starred)
    
    if not all_relationships or outbound_relationships < config.FOLLOW_BOT_THRESHOLD:
        return False
    
    proportional_outbound = outbound_relationships / all_relationships
    
    return(
    outbound_relationships > config.FOLLOW_BOT_AUTOLABEL or # total outbound relationships exceeds threshold
    proportional_outbound > config.FOLLOW_BOT_RATIO # proportion of outbound relationships exceeds threshold
    )
