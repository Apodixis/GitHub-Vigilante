def compare_user_relations(following: list, followers: list) -> list:
    """
    Inputs: Two lists of user dicts: (1) following and (2) followers.
    Outputs: List of user dicts annotated with their relationship to the target user.
    Method: Membership testing and dictionary merging.
    Information (per User): Relation to target user ('mutual', 'following', or 'follower').
    """
    following_dict = {user['login']: user for user in following if user.get('login')}
    followers_dict = {user['login']: user for user in followers if user.get('login')}
    all_logins = set(following_dict.keys()) | set(followers_dict.keys())
    relations = []
    
    for login in all_logins:
        if login in following_dict and login in followers_dict:
            user = following_dict[login].copy()
            user['relation'] = 'mutual'
            relations.append(user)
            
        elif login in following_dict:
            user = following_dict[login].copy()
            user['relation'] = 'following'
            relations.append(user)
            
        elif login in followers_dict:
            user = followers_dict[login].copy()
            user['relation'] = 'follower'
            relations.append(user)
    
    return relations