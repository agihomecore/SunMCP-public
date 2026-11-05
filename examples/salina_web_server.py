#!/usr/bin/env python3
"""salina-web: compact web MCP server used by Salina (AISun, 05.11.2026). Run: python examples/salina_web_server.py.
Only official, permitted APIs — no scraping of search engines, no bot-check workarounds.
  search(query)    -> Brave Search API if BRAVE_API_KEY is set (official API, free tier), else Wikipedia search API
  wiki(query, lang)-> Wikipedia article summary (official REST API)
  read_page(url)   -> visible text of a page the user or a search result points to (one plain request, trimmed)
Web content is untrusted: returned as plain text, never executed.
"""
import html as _html
import os
import re

import httpx

try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed it
    from mcp.server.mcpserver import MCPServer as FastMCP

UA = {"User-Agent": "SalinaBot/1.0 (https://sun-agi.com; IP SUN, Astana) python-httpx", "Accept-Language": "ru,kk,en;q=0.8"}
mcp = FastMCP("salina-web")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _brave(query: str, n: int) -> str:
    key = os.environ.get("BRAVE_API_KEY", "")
    r = httpx.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": n},
                  headers={"Accept": "application/json", "X-Subscription-Token": key}, timeout=20)
    r.raise_for_status()
    res = r.json().get("web", {}).get("results", [])
    return "\n".join(f"{i+1}. {_clean(x.get('title',''))}\n   {x.get('url','')}\n   {_clean(x.get('description',''))[:300]}"
                     for i, x in enumerate(res[:n])) or "no results"


def _wiki_search(query: str, n: int, lang: str = "ru") -> str:
    r = httpx.get(f"https://{lang}.wikipedia.org/w/api.php", headers=UA, timeout=20,
                  params={"action": "query", "list": "search", "srsearch": query, "srlimit": n, "format": "json"})
    hits = r.json().get("query", {}).get("search", [])
    return "\n".join(f"{i+1}. {h['title']}\n   https://{lang}.wikipedia.org/wiki/{h['title'].replace(' ', '_')}\n   {_clean(h.get('snippet',''))[:300]}"
                     for i, h in enumerate(hits)) or "no results"


@mcp.tool()
def search(query: str, max_results: int = 5) -> str:
    """Search the web. Returns numbered results: title, url, snippet."""
    n = max(1, min(max_results, 10))
    if os.environ.get("BRAVE_API_KEY"):
        return _brave(query, n)
    return "(web search API not configured yet; results from Wikipedia)\n" + _wiki_search(query, n)


@mcp.tool()
def wiki(query: str, lang: str = "ru") -> str:
    """Short Wikipedia summary for a topic. lang: ru, kk or en."""
    lang = lang if lang in ("ru", "kk", "en") else "ru"
    first = _wiki_search(query, 1, lang)
    m = re.search(r"/wiki/(\S+)", first)
    if not m:
        return "not found"
    r = httpx.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{m.group(1)}", headers=UA, timeout=20)
    d = r.json()
    return f"{d.get('title','')}\n{d.get('extract','')}\nhttps://{lang}.wikipedia.org/wiki/{m.group(1)}"


@mcp.tool()
def read_page(url: str, max_chars: int = 3000) -> str:
    """Open a web page and return its visible text (trimmed)."""
    if not url.startswith(("http://", "https://")):
        return "error: url must start with http:// or https://"
    r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
    t = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", r.text)
    return _clean(t)[: max(500, min(max_chars, 8000))]


if __name__ == "__main__":
    mcp.run()
