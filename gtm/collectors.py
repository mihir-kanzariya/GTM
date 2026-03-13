"""Signal collectors -- parse platform API responses into structured signals.

These parsers convert raw JSON from Reddit, HN, Dev.to APIs into the standard
signal format for storage in content_signals table. The actual API calls are
made by the AI agent using WebFetch/WebSearch tools -- these functions just
parse the responses.
"""

from gtm.niche import get_niche


def parse_reddit_response(data, platform="reddit"):
    """Parse Reddit JSON API response into signals."""
    signals = []
    children = data.get("data", {}).get("children", [])
    for child in children:
        post = child.get("data", {})
        signals.append({
            "platform": platform,
            "title": post.get("title", ""),
            "text_snippet": (post.get("selftext", "") or "")[:500],
            "author": post.get("author", ""),
            "engagement": post.get("score", 0),
            "source_url": "https://reddit.com" + post.get("permalink", ""),
        })
    return signals


def parse_hn_stories(stories):
    """Parse Hacker News story objects into signals."""
    signals = []
    for story in stories:
        signals.append({
            "platform": "hackernews",
            "title": story.get("title", ""),
            "text_snippet": story.get("title", ""),
            "author": story.get("by", ""),
            "engagement": story.get("score", 0),
            "source_url": story.get("url") or f"https://news.ycombinator.com/item?id={story.get('id', '')}",
            "author_followers": 0,
        })
    return signals


def parse_devto_response(articles):
    """Parse Dev.to API response into signals."""
    signals = []
    for article in articles:
        user = article.get("user", {})
        signals.append({
            "platform": "devto",
            "title": article.get("title", ""),
            "text_snippet": (article.get("description", "") or "")[:500],
            "author": user.get("username", ""),
            "engagement": article.get("positive_reactions_count", 0),
            "source_url": article.get("url", ""),
        })
    return signals


def parse_github_trending(html_text):
    """Extract basic repo info from GitHub trending page HTML."""
    signals = []
    lines = html_text.split("\n")
    for line in lines:
        if '/trending"' in line or 'class="h3' in line:
            continue
        if 'href="/' in line and '" class=' in line:
            start = line.find('href="/') + 7
            end = line.find('"', start)
            if start > 7 and end > start:
                repo_path = line[start:end]
                if "/" in repo_path and not repo_path.startswith("trending"):
                    signals.append({
                        "platform": "github",
                        "title": repo_path,
                        "text_snippet": "",
                        "author": repo_path.split("/")[0] if "/" in repo_path else "",
                        "engagement": 0,
                        "source_url": f"https://github.com/{repo_path}",
                        "author_followers": 5,
                    })
    return signals


def build_search_queries(db_path):
    """Build WebSearch queries based on niche profile."""
    niche = get_niche(db_path)
    industries = niche.get("industries", [])
    audiences = niche.get("audiences", [])

    queries = []

    if industries:
        terms = " OR ".join(f'"{ind}"' for ind in industries[:3])
        queries.append(f"site:x.com ({terms}) developer tools trending today")
        queries.append(f"({terms}) new tools launches this week")

    if audiences:
        for aud in audiences[:2]:
            queries.append(f'"{aud}" what are people talking about this week')

    if not queries:
        queries.append("developer tools trending this week")
        queries.append("saas tools new launch 2026")

    return queries


# Subreddit suggestions based on niche
NICHE_SUBREDDITS = {
    "ai": ["artificial", "MachineLearning", "LocalLLaMA", "ChatGPT"],
    "saas": ["SaaS", "microsaas", "EntrepreneurRideAlong"],
    "developer-tools": ["webdev", "programming", "devtools", "selfhosted"],
    "productivity": ["productivity", "Notion", "ObsidianMD"],
    "devops": ["devops", "kubernetes", "docker"],
    "open-source": ["opensource", "github", "linux"],
    "startups": ["startups", "Entrepreneur", "smallbusiness"],
}


def get_niche_subreddits(db_path, max_subs=8):
    """Return list of subreddits matching the niche profile."""
    niche = get_niche(db_path)
    industries = niche.get("industries", [])
    subs = set()
    for ind in industries:
        subs.update(NICHE_SUBREDDITS.get(ind, []))
    subs.update(["webdev", "SaaS", "indiehackers", "startups"])
    return list(subs)[:max_subs]
