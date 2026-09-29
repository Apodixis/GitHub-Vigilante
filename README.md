# **GitHub-Vigilante**

This project is a work in progress. Uses a suite of search functions to enable threat researchers, network defenders, and human resources teams to identify malicious GitHub accounts and associated activity based on suspicious behaviors, content, and customizable lists of indicators.
__________________________________________________________________

## To-dos

1) Refine social network analysis methodology (requires experimentation)
2) Extract reusable code to ./Utils and helper functions
3) Refine thresholds and formulas used as scoring criterion
4) Refine proportional scoring criterion weights
5) Add logic to modify scoring of users due to inbound/outbound relationships from/to Follow-bot user accounts
6) Implement outbound stargazing activity as a social metric *(requires search modifications and additional user['relationships'] values)*

__________________________________________________________________

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

### Pivots Search

**1) Committer Email Search**
Retrieves all unique (login, fullname) pairs for all commits pushed by any of the input email addresses (or aliased email addresses) or fullnames. *Fullname searches are tokenized, making them less precise and more likely to include additional noise if the fullname includes punctuation (most commonly '-').*

### Repository Search *(Planned)*

**1) Full Info**
<span style="color:#FFA500;">*(Planned, development not yet started)*</span>
<ul>
Retrieves information on the input repository, network of forks, and contributor information of all repositories in network.
</ul>

**2) Similar Repositories**
<span style="color:#FFA500;">*(Planned, development not yet started)*</span>
<ul>
Searches based on name similarity and various README attributes to identify similar repositories.
</ul>