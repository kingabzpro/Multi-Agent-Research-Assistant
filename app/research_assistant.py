from __future__ import annotations

import asyncio
import contextvars
import importlib.metadata
import json
import os
import warnings
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from agents import (
    Agent,
    Runner,
    custom_span,
    flush_traces,
    function_tool,
    gen_trace_id,
    trace,
)
from dotenv import load_dotenv
from olostep import Olostep
from pydantic import BaseModel, Field

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLOSTEP_API_KEY = os.getenv("OLOSTEP_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

warnings.filterwarnings("ignore", message=".*extra field.*SDK model.*")

ProgressCallback = Callable[[str], Awaitable[None]]
_progress_callback: contextvars.ContextVar[ProgressCallback | None] = (
    contextvars.ContextVar(
        "progress_callback",
        default=None,
    )
)


class OlostepError(RuntimeError):
    """Raised when an Olostep SDK request fails."""


class Judgment(BaseModel):
    is_good_enough: bool = Field(
        description="Whether the answer is sufficient for the user query, meaning score >= 0.85."
    )
    score: float = Field(ge=0, le=1, description="Quality score from 0 to 1.")
    reason: str = Field(description="Short explanation of the decision.")
    missing_information: list[str] = Field(
        default_factory=list, description="Important gaps to fix."
    )


class MarkdownResearchReport(BaseModel):
    title: str = Field(description="Research report title.")
    executive_summary: str = Field(description="Short answer-first summary.")
    key_findings: list[str] = Field(description="Most important findings.")
    markdown_report: str = Field(
        description="Complete Markdown report with polished headings, clear analysis, reader-friendly structure, and citations."
    )
    citations: list[str] = Field(
        default_factory=list, description="Source URLs used in the report."
    )
    confidence: str = Field(description="Low, medium, or high confidence.")
    method_used: str = Field(description="Retrieval path used by the manager agent.")


async def emit_progress(message: str) -> None:
    callback = _progress_callback.get()
    if callback is not None:
        await callback(message)


def openai_trace_url(trace_id: str) -> str:
    return f"https://platform.openai.com/logs/trace?trace_id={trace_id}"


def environment_status() -> tuple[bool, list[str], str, str]:
    missing = [
        name
        for name, value in {
            "OPENAI_API_KEY": OPENAI_API_KEY,
            "OLOSTEP_API_KEY": OLOSTEP_API_KEY,
        }.items()
        if not value
    ]
    try:
        olostep_version = importlib.metadata.version("olostep")
    except importlib.metadata.PackageNotFoundError:
        olostep_version = "not installed"
    try:
        openai_version = importlib.metadata.version("openai-agents")
    except importlib.metadata.PackageNotFoundError:
        openai_version = "not installed"
    return not missing, missing, olostep_version, openai_version


def require_olostep_key() -> str:
    if not OLOSTEP_API_KEY:
        raise OlostepError(
            "OLOSTEP_API_KEY is not set. Add it to .env and restart the app."
        )
    return OLOSTEP_API_KEY


def get_olostep_client() -> Olostep:
    return Olostep(api_key=require_olostep_key())


def sdk_result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "__dict__"):
        return {
            key: value for key, value in vars(result).items() if not key.startswith("_")
        }
    return {"value": str(result)}


def compact_json(data: Any, max_chars: int = 8000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def current_date_context() -> str:
    return datetime.now().strftime("%B %d, %Y")


def current_year_context() -> str:
    return str(datetime.now().year)


def normalize_search_links(
    links: list[dict[str, Any]], limit: int = 8
) -> list[dict[str, Any]]:
    rows = []
    for link in links[:limit]:
        markdown = link.get("markdown_content") or ""
        rows.append(
            {
                "title": link.get("title") or "Untitled",
                "url": link.get("url") or "",
                "description": link.get("description") or "",
                "markdown_chars": len(markdown),
                "markdown_preview": markdown[:1500] if markdown else "",
            }
        )
    return rows


def _answer_query_impl(query: str) -> str:
    with custom_span("olostep.answer_query", {"query": query}):
        result = get_olostep_client().answers.create(task=query)
        return compact_json(sdk_result_to_dict(result))


def _search_web_impl(query: str, limit: int = 8) -> str:
    with custom_span("olostep.search_web", {"query": query, "limit": limit}):
        search = get_olostep_client().searches.create(query=query, limit=limit)
        data = sdk_result_to_dict(search)
        return compact_json(
            {
                "query": query,
                "results": normalize_search_links(data.get("links", []), limit=limit),
                "raw": data,
            }
        )


def _search_with_scrape_impl(query: str, limit: int = 5) -> str:
    scrape_options = {"formats": ["markdown"], "timeout": 25}
    with custom_span(
        "olostep.search_with_scrape",
        {"query": query, "limit": limit, "scrape_options": scrape_options},
    ):
        search = get_olostep_client().searches.create(
            query=query,
            limit=limit,
            scrape_options=scrape_options,
        )
        data = sdk_result_to_dict(search)
        return compact_json(
            {
                "query": query,
                "results": normalize_search_links(data.get("links", []), limit=limit),
                "raw": data,
            },
            max_chars=12000,
        )


def _scrape_url_impl(url: str) -> str:
    with custom_span("olostep.scrape_url", {"url": url, "formats": ["markdown"]}):
        scrape = get_olostep_client().scrapes.create(url=url, formats=["markdown"])
        return compact_json(
            {"url": url, "scrape": sdk_result_to_dict(scrape)}, max_chars=10000
        )


@function_tool
async def answer_query(query: str) -> str:
    """Answer a natural-language research query using Olostep Answer API."""
    await emit_progress("Calling Olostep Answer API.")
    try:
        result = await asyncio.to_thread(_answer_query_impl, query)
    except Exception as exc:
        raise OlostepError(f"Olostep Answer API failed: {exc}") from exc
    await emit_progress("Olostep Answer API returned evidence.")
    return result


@function_tool
async def search_web(query: str, limit: int = 8) -> str:
    """Search the web using Olostep Search and return normalized results."""
    await emit_progress(f"Searching the web with Olostep: {query}")
    try:
        result = await asyncio.to_thread(_search_web_impl, query, limit)
    except Exception as exc:
        raise OlostepError(f"Olostep Search API failed: {exc}") from exc
    await emit_progress("Olostep Search returned results.")
    return result


@function_tool
async def search_with_scrape(query: str, limit: int = 5) -> str:
    """Search the web and scrape each returned link using Olostep Search with Scrape."""
    await emit_progress(f"Running Olostep search with scrape: {query}")
    try:
        result = await asyncio.to_thread(_search_with_scrape_impl, query, limit)
    except Exception as exc:
        raise OlostepError(f"Olostep Search with Scrape failed: {exc}") from exc
    await emit_progress("Search with scrape returned source content.")
    return result


@function_tool
async def scrape_url(url: str) -> str:
    """Scrape one URL with Olostep and return compact page content."""
    await emit_progress(f"Scraping selected source: {url}")
    try:
        result = await asyncio.to_thread(_scrape_url_impl, url)
    except Exception as exc:
        raise OlostepError(f"Olostep Scrape API failed: {exc}") from exc
    await emit_progress("Selected source scrape completed.")
    return result


def _format_missing_information(missing_information: list[str]) -> str:
    if not missing_information:
        return "none"
    return "; ".join(missing_information[:3])


judge_agent = Agent(
    name="Judge agent",
    model=MODEL,
    instructions=(
        "You judge whether the provided answer is good enough for the original research question. "
        "Reward direct, specific, source-backed answers. Reject vague, stale, or unsupported answers. "
        "Be strict: is_good_enough must be true only when score >= 0.85 and the evidence directly answers "
        "the question with concrete source content, topic-specific detail, and appropriate recency. "
        "For current events, product status, policies, pricing, or factual claims that may change, require recent "
        "primary or highly reputable sources. Do not mark evidence sufficient if any critical gap remains. "
        "Calibrate scores this way: 0.85-1.0 means sufficient to stop with strong source support and no critical gaps; "
        "0.75-0.84 means strong but still missing one important source, detail, recency check, or coverage area; "
        "0.50-0.74 means relevant partial evidence that needs more research; 0.25-0.49 means thin, vague, stale, "
        "or weakly related evidence; below 0.25 is only for empty, unusable, or mostly unrelated evidence. "
        "Do not mark evidence sufficient just because it is plausible or directionally correct. "
        "Return only the structured judgment."
    ),
    output_type=Judgment,
)


@function_tool
async def judge_answer_quality(
    original_question: str, evidence: str, stage: str = "current evidence"
) -> str:
    """Judge whether evidence is sufficient for the original question and emit the score."""
    await emit_progress(f"Judge evaluating {stage}.")
    prompt = f"""
Original research question:
{original_question}

Evidence stage:
{stage}

Evidence to judge:
{evidence}

Return a structured judgment for whether this evidence is sufficient to answer the original question.
"""
    with custom_span("judge.answer_quality", {"stage": stage}):
        result = await Runner.run(judge_agent, prompt, max_turns=3)
    judgment = result.final_output
    await emit_progress(
        f"Judge score: {judgment.score:.2f} "
        f"({'sufficient' if judgment.is_good_enough else 'needs more evidence'}). "
        f"{judgment.reason}"
    )
    if judgment.missing_information:
        await emit_progress(
            f"Judge missing information: {_format_missing_information(judgment.missing_information)}"
        )
    return judgment.model_dump_json()


analyst_agent = Agent(
    name="Analyst agent",
    model=MODEL,
    instructions=(
        "You write a proper Markdown research report from the evidence. "
        "Write for a professional reader who wants a clear, polished research brief on any topic. "
        "Adapt the report to the user's question. The markdown_report must be substantial, easy to scan, and use these general sections only: "
        "Executive Summary, Key Findings, Context, Evidence Review, Detailed Analysis, Implications, Source Notes, and References. "
        "If the topic is event-driven, include timeline details inside Context or Detailed Analysis instead of adding a separate Timeline section. "
        "If the topic is comparative, include a compact comparison table inside Detailed Analysis. "
        "Do not include sections titled Limitations, Next Steps, Recommendations, or Action Items. "
        "Avoid bare caveats like 'I relied on...'. Instead, integrate source quality naturally in Source Notes. "
        "Use short paragraphs, bullets where helpful, and citations as Markdown links. Add enough context that a "
        "non-expert reader understands the issue, why it matters, and what evidence supports it. "
        "Do not use emoji, return-arrow symbols, backlink icons, or decorative icons anywhere in the report. "
        "In References, list only plain Markdown bullets or numbered items with the source name and URL. "
        "Return only the structured report."
    ),
    output_type=MarkdownResearchReport,
)

analyst_tool = analyst_agent.as_tool(
    tool_name="write_markdown_research_report",
    tool_description="Write the final structured Markdown research report from the gathered evidence.",
)

manager_agent = Agent(
    name="Manager research agent",
    model=MODEL,
    instructions=(
        f"Current date: {current_date_context()}\n"
        f"Current year: {current_year_context()}\n\n"
        "You are the orchestrator for a multi-agent research assistant. You must manage the workflow, "
        "not answer from your own memory. Follow this policy exactly:\n"
        "1. Always call answer_query first to get a simple initial answer for the user's question.\n"
        "2. Immediately call judge_answer_quality on the original question plus the answer_query result. "
        "If the judge returns is_good_enough=true and score >= 0.85, stop researching and call "
        "write_markdown_research_report with the question, answer result, and judgment.\n"
        "3. If the first judgment is weak, call search_with_scrape for the original question. "
        "Immediately call judge_answer_quality again on the original question plus the answer_query result, "
        "first judgment, and search_with_scrape result. If this second judge returns is_good_enough=true "
        "and score >= 0.85, stop researching and call write_markdown_research_report with all evidence.\n"
        "4. If the second judgment is still weak, do not call the judge again. Run multiple targeted "
        "search_web calls first, using the judge's missing_information to form the searches. Inspect the "
        "search results, choose at least the top 3 relevant source URLs most likely to answer the missing "
        "points, then call scrape_url on each of those top 3 pages. Scrape more than 3 only if clearly needed.\n"
        "5. Call write_markdown_research_report exactly once at the end, using every answer, judgment, "
        "search result, and scraped page. The analyst must produce the final MarkdownResearchReport.\n"
        "6. Return only the final MarkdownResearchReport. Do not return a casual chat answer, tool transcript, or plan."
    ),
    tools=[
        answer_query,
        judge_answer_quality,
        search_with_scrape,
        search_web,
        scrape_url,
        analyst_tool,
    ],
    output_type=MarkdownResearchReport,
)


async def run_research_assistant(
    query: str, progress: ProgressCallback | None = None
) -> tuple[MarkdownResearchReport, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to .env and restart the app."
        )
    require_olostep_key()

    token = _progress_callback.set(progress)
    trace_id = gen_trace_id()
    trace_url = openai_trace_url(trace_id)

    try:
        await emit_progress("Starting manager research agent.")
        current_date = current_date_context()
        current_year = current_year_context()
        prompt = f"""
Current date:
{current_date}

Current year:
{current_year}

Research question:
{query}

Return a polished, reader-friendly Markdown research report with substantial detail for the user's specific question. Follow the required workflow exactly:
- Use answer_query first for a simple initial answer.
- Use the judge agent immediately after the simple answer to decide whether to stop or continue.
- If the first judge says the answer is not sufficient, run search_with_scrape.
- Use the judge agent immediately after search_with_scrape to decide whether to stop or continue.
- If the second judge still says the evidence is weak, do not judge again. Run multiple targeted search_web calls, choose at least the top 3 relevant source URLs from the search results, and scrape those top 3 pages for context.
- Analyst agent writes the final Markdown report from all answer, judge, search, and scrape evidence. Do not include Limitations or Next Steps sections.
"""
        with trace(
            workflow_name="multi_agent_research_assistant_olostep",
            trace_id=trace_id,
            metadata={"query": query, "app": "reflex_research_assistant"},
        ):
            with custom_span("manager.run", {"query": query}):
                result = await Runner.run(manager_agent, prompt, max_turns=30)

        await emit_progress("Manager run completed. Flushing OpenAI traces.")
        flush_traces()
        await emit_progress("Trace flushed. Rendering Markdown report.")
        return result.final_output, trace_url
    finally:
        _progress_callback.reset(token)
