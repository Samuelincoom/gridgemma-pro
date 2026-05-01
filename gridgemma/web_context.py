"""Permissioned DuckDuckGo future scenario snippet search."""

from __future__ import annotations

from .schemas import WebSnippet


def get_future_scenario_context(country: str, year: int, max_snippets: int = 5) -> list[WebSnippet]:
    """Return up to five public search snippets without scraping full pages."""

    from duckduckgo_search import DDGS

    queries = [
        f"planned electricity projects infrastructure {country} {year}",
        f"new power plants grid expansion renewable projects {country} {year}",
        f"energy crisis drought heatwave fuel shortage electricity demand {country} {year}",
    ]
    snippets: list[WebSnippet] = []
    seen_urls: set[str] = set()

    with DDGS(timeout=8) as ddgs:
        for query in queries:
            if len(snippets) >= max_snippets:
                break
            results = ddgs.text(query, max_results=max_snippets)
            for result in results:
                if len(snippets) >= max_snippets:
                    break
                title = str(result.get("title") or "").strip()
                body = str(result.get("body") or result.get("snippet") or "").strip()
                url = str(result.get("href") or result.get("url") or "").strip()
                if not body and not title:
                    continue
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                snippets.append(WebSnippet(title=title[:180], body=body[:500], url=url[:300]))

    return snippets
