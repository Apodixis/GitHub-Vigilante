# **GitHub-Vigilante**

This project is a work in progress. Uses a suite of search functions to enable threat researchers, network defenders, and human resources teams to identify malicious GitHub accounts and associated activity based on suspicious behaviors, content, and customizable lists of indicators.
__________________________________________________________________

## Todos

1) Modify functions to handle multiple inputs
2) Build remaining functions
3) Extract reusable code to ./Utils
4) Configure initial scoring implementation (Config file, scoring functions, and sample indicators)
5) Refine thresholds and formulas used as scoring criterion

__________________________________________________________________

## Search Modes

### User Search

**1) Exact Match**
Retrieves information on the input user, their followers, the users they follow, repositories starred, and stargazers of owned repositories.

**2) Partial Match**
Retrieves information on users whose name includes the input substring.

**3) Email *(Commit)* Search**
<span style="color:#FFA500;">*(Planned, development not yet started)*</span>
Retrieves information for all commits pushed by a specific email address (or aliased email address) to identify relationships.

### Organization Search

**1) Full Info**
<ul>
Retrieves information on the input organization(s), org members, and org repositories.
</ul>

### Repository Search

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