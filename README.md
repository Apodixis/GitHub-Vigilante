# **GitHub-Vigilante**

This project is a work in progress. Uses a suite of search functions to enable threat researchers, network defenders, and human resources teams to identify malicious GitHub accounts and associated activity based on suspicious behaviors, content, and customizable lists of indicators.
__________________________________________________________________

## To-dos

1) Mature database operations and checks to fix the following:
    a. Add a 'lastFetched' key to each record that stores the time the record was last added/updated (facilitates prompted or automated pulls to update stale records)
    b. Build report functions that perform analytic tasks when invoked (ie: identifying longest strings in common for a count(threshold) number of users—surfaces frequently reused naming conventions) "partially completed"
2) Extract reusable code to ./Utils and helper functions
3) Refine proportional scoring criterion weights (requires optimization
4) Add logic to modify scoring of users due to inbound/outbound relationships from/to Follow-bot user accounts

__________________________________________________________________

## Scoring configuration
Relationship scoring uses only `graph_pagerank_alpha` in [config.py](./config.py).
Use `score_users()` in the database management interface to recompute stored scores
after changing this value, and `validate_users()` to evaluate them.
Existing database is normalized automatically on initialization or the next write,
removing obsolete per-alpha columns while preserving the remaining user data.

## Search Modes

### User Search

**1) Exact Match**
Retrieves information on the input user, their followers, the users they follow, and the organizations they are member to.

**2) Partial Match**
Retrieves information on users whose login, fullname, public email address, or biography include the supplied substring.

**3) Email Reverse Search**
First identifies logins from supplied email addresses, then passes logins to the User Exact Match search method

### Organization Search

**1) Full Info**
Retrieves information on the input organization(s), org members, and org repositories.


### Repository Search

Available as option **3** in the main menu. Full Information is implemented.
Similar Repositories and Code Proliferation remain placeholders and exit without
running a search.

**1) Full Information**
<ul>
Accepts one or more `owner/name` pairs. Collects unique user-owner and contributor
logins, then fetches and enriches their user records. Organization owners and
anonymous contributors without logins are excluded.

The Excel output contains scored user records. Its searched-logins summary counts
returned users matching the discovered owner/contributor logins. No searched
emails are supplied because the inputs are repositories, not email addresses.
Fork enumeration is not implemented.
</ul>

**2) Similar Repositories**
<span style="color:#FFA500;">*(Planned, development not yet started)*</span>
<ul>
Searches based on name similarity and various README attributes to identify similar repositories.
</ul>

**3) Code Proliferation** *(Placeholder)*
<span style="color:#FFA500;">*(Planned, development not yet started)*</span>
<ul>
Performs a full info search on all repositories forked from the input repositories.
</ul>

### Pivots Search

**1) Committer Email Search**
Retrieves all unique (login, fullname) pairs for all commits pushed by any of the input email addresses (or aliased email addresses) or fullnames. *Fullname searches are tokenized, making them less precise and more likely to include additional noise if the fullname includes punctuation (most commonly '-').*