import re
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from duckduckgo_search import DDGS

WEB_SEARCH_PREFIX = "web_search:"

_WEB_SEARCH_SIGNALS = (
    "benchmark",
    "industry average",
    "market average",
    "market trend",
    "market data",
    "exchange rate",
    "forex",
    "usd thb",
    "usd/thb",
    "interest rate",
    "inflation",
    " gdp",
    "macroeconomic",
    "macro economic",
    "stock index",
    "latest news",
    "current news",
    "competitor pricing",
    "external data",
    "outside data",
    "from the web",
    "from internet",
    "industry standard",
    "compared to market",
    "compare to market",
    "compare with market",
    "vs industry",
    "versus industry",
    "industry benchmark",
    "อัตราแลก",
    "ค่าเงินบาท",
    "เศรษฐกิจ",
    "ข่าวล่าสุด",
    "ข้อมูลภายนอก",
    "คู่แข่งในตลาด",
    "เทียบกับตลาด",
    "เปรียบเทียบกับตลาด",
    "เปรียบเทียบกับอุตสาหกรรม",
    "เทียบกับอุตสาหกรรม",
    "เงินเฟ้อ",
    "ดอกเบี้ย",
    "เรทวันนี้",
    "เรทล่าสุด",
    "ค่าเงินล่าสุด",
    "ค่าเงินวันนี้",
    "ราคาปัจจุบัน",
    "ข้อมูลล่าสุด",
    "ณ วันนี้",
    "as of today",
    "as of now",
    "current price",
    "latest rate",
    "weather today",
    "weather forecast",
    "current president",
    "current prime minister",
    "current ceo",
    "current law",
    "current regulation",
    "sports score",
    "match schedule",
    "อากาศวันนี้",
    "พยากรณ์อากาศ",
    "ประธานาธิบดีคนปัจจุบัน",
    "นายกรัฐมนตรีคนปัจจุบัน",
    "ซีอีโอปัจจุบัน",
    "กฎหมายปัจจุบัน",
    "กฎระเบียบล่าสุด",
    "ผลบอลล่าสุด",
    "ตารางแข่ง",
)

_CURRENCY_PAIR_RE = re.compile(
    r"(?<![A-Z])(?:USD|THB|EUR|GBP|JPY|CNY|RMB|AUD|CAD|CHF|SGD|HKD|KRW|INR)"
    r"\s*(?:/|[-–—]|TO|INTO|เป็น|เทียบ(?:กับ)?)\s*"
    r"(?:USD|THB|EUR|GBP|JPY|CNY|RMB|AUD|CAD|CHF|SGD|HKD|KRW|INR)(?![A-Z])",
    re.IGNORECASE,
)

_CURRENT_DATE_RE = re.compile(
    r"(?:\b(?:today|current|currently|latest|now|real[- ]?time|as of)\b"
    r"|วันนี้|ปัจจุบัน|ล่าสุด|ตอนนี้|ณ\s*วัน(?:ที่)?นี้)",
    re.IGNORECASE,
)

_EXTERNAL_TOPIC_RE = re.compile(
    r"(?:rate|price|currency|forex|exchange|market|benchmark|news|inflation|interest|gdp"
    r"|weather|forecast|president|minister|ceo|law|regulation|sports|score|schedule"
    r"|อัตรา|ราคา|ค่าเงิน|ตลาด|ข่าว|เงินเฟ้อ|ดอกเบี้ย|เศรษฐกิจ|อากาศ|พยากรณ์"
    r"|ประธานาธิบดี|นายกรัฐมนตรี|ซีอีโอ|กฎหมาย|กฎระเบียบ|ผลบอล|ตารางแข่ง)",
    re.IGNORECASE,
)
_COMPARE_SEARCH_RE = re.compile(
    r"\b(?:compare|comparison|versus|vs\.?|benchmark|against)\b"
    r"|เปรียบเทียบ|เทียบกับ|เทียบอุตสาหกรรม",
    re.IGNORECASE,
)


def web_search_enabled(user_tier: str) -> bool:
    return (user_tier or "free").lower() in ("plus", "pro")


def needs_web_search(question: str) -> bool:
    from app.services.anti_hallucination import needs_live_external_facts

    q = (question or "").strip().lower()
    if _CURRENCY_PAIR_RE.search(question or ""):
        return True
    if needs_live_external_facts(question or ""):
        return True
    if len(q) < 8:
        return False
    if any(sig in q for sig in _WEB_SEARCH_SIGNALS):
        return True
    return bool(_CURRENT_DATE_RE.search(question) and _EXTERNAL_TOPIC_RE.search(question))


def web_search_query_from_question(question: str) -> str:
    q = (question or "").strip()
    q = re.sub(r"\s+", " ", q)
    return q[:240]


def generate_web_search_queries(question: str, max_queries: int = 3) -> List[str]:
    """Generate focused, complementary searches without spending another LLM call."""
    base = web_search_query_from_question(question)
    if not base:
        return []
    # Drop clock/date-only clauses so combined asks don't pollute FX search.
    search_base = re.sub(
        r"(?i)(?:และ\s*)?(?:ตอนนี้|วันนี้)?\s*(?:วันที่|เวลา|กี่โมง).{0,24}(?:เท่าไหร่|กี่|อะไร)?",
        " ",
        base,
    )
    search_base = re.sub(r"\s+", " ", search_base).strip() or base
    queries: List[str] = []
    current_year = date.today().year
    if _CURRENCY_PAIR_RE.search(search_base) or _CURRENCY_PAIR_RE.search(base):
        pair = _CURRENCY_PAIR_RE.search(search_base) or _CURRENCY_PAIR_RE.search(base)
        if pair:
            normalized_pair = re.sub(
                r"\s*(?:/|[-–—]|TO|INTO|เป็น|เทียบ(?:กับ)?)\s*",
                " ",
                pair.group(0),
                flags=re.IGNORECASE,
            ).upper()
            queries.extend(
                [
                    f"{normalized_pair} exchange rate today",
                    f"{normalized_pair} official exchange rate {current_year}",
                    f"{normalized_pair} bot.or.th",
                ]
            )
    elif re.search(
        r"(?i)\b(?:USD|THB|EUR|GBP|JPY|CNY)\b|ค่าเงิน|อัตราแลก|exchange\s*rate|forex",
        search_base + " " + base,
    ):
        code_match = re.search(r"(?i)\b(USD|EUR|GBP|JPY|CNY)\b", search_base + " " + base)
        code = (code_match.group(1) if code_match else "USD").upper()
        if code == "THB":
            code = "USD"
        queries.extend(
            [
                f"{code} THB exchange rate today",
                f"{code} to THB exchange rate",
                f"{code} THB bot.or.th official",
            ]
        )
    elif _CURRENT_DATE_RE.search(base):
        queries.append(f"{search_base} {current_year} official source")
        queries.append(f"{search_base} latest report")
    elif _COMPARE_SEARCH_RE.search(base):
        queries.append(f"{search_base} industry benchmark {current_year}")
    else:
        queries.append(search_base)
        queries.append(f"{search_base} official data")
        queries.append(f"{search_base} report {current_year}")

    # Keep original only as a low-priority fallback when no focused queries exist.
    if not queries:
        queries = [base]
    elif search_base and search_base.lower() not in {q.lower() for q in queries}:
        if not re.search(
            r"(?i)\b(?:USD|THB|EUR|GBP|JPY|CNY)\b|ค่าเงิน|อัตราแลก|exchange\s*rate|forex",
            base,
        ):
            queries.append(search_base)

    deduped: List[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = re.sub(r"\s+", " ", query).strip()[:240]
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped[:max_queries]


_FX_TOPIC_RE = re.compile(
    r"(?i)\b(?:USD|THB|EUR|GBP|JPY|CNY|exchange|forex|currency|rate)\b|"
    r"ค่าเงิน|อัตราแลก|เรท|บาท",
)
_IRRELEVANT_SOURCE_RE = re.compile(
    r"(?i)whatsapp|facebook|instagram|tiktok|messenger|play\.google\.com/store/apps|"
    r"app\s*store|download\s+the\s+app|snapchat|telegram",
)
_FX_SIGNAL_RE = re.compile(
    r"(?i)\b(?:USD|THB|EUR|GBP|JPY|CNY|exchange|forex|currency|baht|rate)\b|"
    r"ค่าเงิน|อัตราแลก|เรท|บาท|ธนาคารแห่งประเทศไทย|bot\.or\.th",
)


def filter_web_sources_for_question(
    sources: List[Dict[str, Any]],
    question: str,
) -> List[Dict[str, Any]]:
    """Drop obviously irrelevant hits (e.g. WhatsApp apps for FX questions)."""
    text = question or ""
    if not sources:
        return []
    cleaned: List[Dict[str, Any]] = []
    fx_ask = bool(_FX_TOPIC_RE.search(text))
    for source in sources:
        blob = f"{source.get('title', '')} {source.get('snippet', '')} {source.get('url', '')}"
        if _IRRELEVANT_SOURCE_RE.search(blob):
            continue
        if fx_ask and not _FX_SIGNAL_RE.search(blob):
            continue
        cleaned.append(source)
    return cleaned


def build_web_search_step(question: str) -> str:
    return f"{WEB_SEARCH_PREFIX} {web_search_query_from_question(question)}"


def inject_web_search_steps(
    steps: List[str],
    question: str,
    user_tier: str,
) -> List[str]:
    """No longer keyword-forces web search — model planner owns tool choice.

    Kept for API compatibility; returns steps unchanged.
    """
    _ = (question, user_tier)
    return list(steps)


def merge_web_search_with_result(
    analytics_result: Optional[Dict[str, Any]],
    web_result: Dict[str, Any],
) -> Dict[str, Any]:
    web_block = (web_result.get("formatted") or "").strip()
    if not analytics_result:
        return {
            **web_result,
            "formatted": (
                f"=== External Web Context (pre-fetched by platform) ===\n{web_block}"
                if web_block
                else web_block
            ),
        }
    data_block = (analytics_result.get("formatted") or "").strip()
    combined = (
        f"=== External Web Context (pre-fetched by platform) ===\n{web_block}\n\n"
        f"=== Dataset Analysis (computed on full dataset) ===\n{data_block}"
    )
    sources = dedupe_web_sources(
        list(analytics_result.get("web_sources") or [])
        + list(web_result.get("web_sources") or [])
    )
    merged = {**analytics_result, "formatted": combined.strip()}
    if sources:
        merged["web_sources"] = sources
    return merged


def is_web_search_step(step: str) -> bool:
    return (step or "").strip().startswith(WEB_SEARCH_PREFIX)


def normalize_web_search_query(step: str) -> str:
    query = step.split(WEB_SEARCH_PREFIX, 1)[1].strip()
    return re.sub(r" \(User context: .*\)$", "", query)


def dedupe_web_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for source in sources:
        url = (source.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(
            {
                "title": (source.get("title") or url).strip(),
                "url": url,
                "snippet": (source.get("snippet") or "").strip(),
                **({"query": source["query"]} if source.get("query") else {}),
                **({"score": source["score"]} if source.get("score") is not None else {}),
            }
        )
    return deduped


_TRUSTED_DOMAIN_SUFFIXES = (
    ".go.th",
    ".gov",
    ".gov.uk",
    ".europa.eu",
    ".org",
)
_TRUSTED_DOMAINS = {
    "bot.or.th",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "ecb.europa.eu",
    "federalreserve.gov",
    "reuters.com",
}


def _source_score(source: Dict[str, Any], question: str) -> float:
    url = source.get("url") or ""
    host = (urlparse(url).hostname or "").lower()
    score = 0.35
    if host in _TRUSTED_DOMAINS or any(host.endswith(s) for s in _TRUSTED_DOMAIN_SUFFIXES):
        score += 0.35
    q_tokens = set(re.findall(r"[\w\u0e00-\u0e7f]+", question.lower()))
    text_tokens = set(
        re.findall(
            r"[\w\u0e00-\u0e7f]+",
            f"{source.get('title', '')} {source.get('snippet', '')}".lower(),
        )
    )
    if q_tokens:
        score += min(0.25, len(q_tokens & text_tokens) / len(q_tokens))
    if str(date.today().year) in f"{source.get('title', '')} {source.get('snippet', '')}":
        score += 0.05
    return round(min(1.0, score), 3)


def rank_web_sources(
    sources: List[Dict[str, Any]],
    question: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    ranked = []
    for source in dedupe_web_sources(sources):
        ranked.append({**source, "score": _source_score(source, question)})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def run_web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Executes a web search using duckduckgo_search and formats the results for the agent.
    Returns a dictionary compatible with the expected agent step results.
    """
    base = {
        "question": f"{WEB_SEARCH_PREFIX} {query}",
        "rows_analyzed": 0,
        "code": f"duckduckgo_search('{query}')",
        "engine": "web_search",
        "web_sources": [],
        "attempts": 1,
    }
    try:
        raw_results: List[Dict[str, str]] = []
        with DDGS() as ddgs:
            for row in ddgs.text(query, max_results=max_results):
                raw_results.append(
                    {
                        "title": row.get("title", ""),
                        "href": row.get("href", ""),
                        "body": row.get("body", ""),
                    }
                )

        web_sources = dedupe_web_sources(
            [
                {
                    "title": row["title"],
                    "url": row["href"],
                    "snippet": row["body"],
                    "query": query,
                }
                for row in raw_results
                if row.get("href")
            ]
        )

        if not web_sources:
            formatted = f"No web search results found for query: {query}"
            success = True
        else:
            parts = [f"Web Search Results for '{query}':"]
            for index, source in enumerate(web_sources, 1):
                parts.append(
                    f"{index}. {source['title']}\n"
                    f"   URL: {source['url']}\n"
                    f"   Snippet: {source['snippet']}"
                )
            formatted = "\n\n".join(parts)
            success = True

        return {
            **base,
            "formatted": formatted,
            "web_sources": web_sources,
            "success": success,
        }
    except Exception as exc:
        error_msg = f"Web search failed: {str(exc)}\n{traceback.format_exc()}"
        return {
            **base,
            "formatted": error_msg,
            "success": False,
        }


def run_multi_web_search(
    question: str,
    *,
    max_queries: int = 3,
    max_results_per_query: int = 4,
    max_sources: int = 8,
) -> Dict[str, Any]:
    """Search complementary queries concurrently, dedupe, and rank evidence."""
    queries = generate_web_search_queries(question, max_queries=max_queries)
    if not queries:
        return run_web_search(question, max_results=max_sources)

    results: List[Dict[str, Any]] = []
    worker_count = min(3, len(queries))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(run_web_search, query, max_results_per_query): query
            for query in queries
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "success": False,
                        "formatted": f"Web search failed: {exc}",
                        "web_sources": [],
                    }
                )

    sources = rank_web_sources(
        [
            source
            for result in results
            for source in (result.get("web_sources") or [])
        ],
        question,
        limit=max_sources * 2,
    )
    sources = filter_web_sources_for_question(sources, question)[:max_sources]
    formatted_parts = [f"Multi-query Web Search for '{question}':"]
    for index, source in enumerate(sources, 1):
        formatted_parts.append(
            f"{index}. {source['title']}\n"
            f"   URL: {source['url']}\n"
            f"   Query: {source.get('query', '')}\n"
            f"   Relevance: {source.get('score', 0):.2f}\n"
            f"   Snippet: {source['snippet']}"
        )
    if not sources:
        formatted_parts.append("No relevant web search results found.")
    return {
        "question": question,
        "queries": queries,
        "rows_analyzed": 0,
        "code": "duckduckgo_multi_search",
        "engine": "web_search",
        "web_sources": sources,
        "formatted": "\n\n".join(formatted_parts),
        "success": any(result.get("success") for result in results),
        "attempts": len(queries),
    }
