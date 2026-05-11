from __future__ import annotations

import asyncio
import contextvars
import importlib.metadata
import json
import os
import warnings
from collections.abc import Awaitable, Callable
from typing import Any

from agents import Agent, Runner, custom_span, flush_traces, function_tool, gen_trace_id, trace
from dotenv import load_dotenv
from olostep import Olostep
from pydantic import BaseModel, Field

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLOSTEP_API_KEY = os.getenv("OLOSTEP_API_KEY")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

warnings.filterwarnings("ignore", message=".*extra field.*SDK model.*")

ProgressCallback = Callable[[str], Awaitable[None]]
_progress_callback: contextvars.ContextVar[ProgressCallback | None] = contextvars.ContextVar(
    "progress_callback",
    default=None,
)


class OlostepError(RuntimeError):
    """Raised when an Olostep SDK request fails."""


class Judgment(BaseModel):
    is_good_enough: bool = Field(description="Whether the answer is sufficient for the user query.")
    score: float = Field(ge=0, le=1, description="Quality score from 0 to 1.")
    reason: str = Field(description="Short explanation of the decision.")
    missing_information: list[str] = Field(default_factory=list, description="Important gaps to fix.")


class SourceResearchReport(BaseModel):
    key_findings: list[str] = Field(description="Concise findings from gathered sources.")
    important_urls: list[str] = Field(description="Only the most important URLs used for synthesis.")
    source_notes: list[str] = Field(description="Brief notes connecting sources to findings.")
    remaining_gaps: list[str] = Field(default_factory=list, description="Gaps that could not be resolved.")


class MarkdownResearchReport(BaseModel):
    title: str = Field(description="Research report title.")
    executive_summary: str = Field(description="Short answer-first summary.")
    key_findings: list[str] = Field(description="Most important findings.")
    markdown_report: str = Field(
        description="Complete Markdown report with polished headings, clear analysis, reader-friendly structure, and citations."
    )
    citations: list[str] = Field(default_factory=list, description="Source URLs used in the report.")
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
        raise OlostepError("OLOSTEP_API_KEY is not set. Add it to .env and restart the app.")
    return OLOSTEP_API_KEY


def get_olostep_client() -> Olostep:
    return Olostep(api_key=require_olostep_key())


def sdk_result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "__dict__"):
        return {key: value for key, value in vars(result).items() if not key.startswith("_")}
    return {"value": str(result)}


def compact_json(data: Any, max_chars: int = 8000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def normalize_search_links(links: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
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
    with custom_span("olostep.search_with_scrape", {"query": query, "limit": limit, "scrape_options": scrape_options}):
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
        return compact_json({"url": url, "scrape": sdk_result_to_dict(scrape)}, max_chars=10000)


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


judge_agent = Agent(
    name="Judge agent",
    model=MODEL,
    instructions=(
        "You judge whether the provided answer is good enough for the original research question. "
        "Reward direct, specific, source-backed answers. Reject vague, stale, or unsupported answers. "
        "Return only the structured judgment."
    ),
    output_type=Judgment,
)

def _build_source_research_agent():
    from datetime import datetime
    now = datetime.now().strftime("%B %d, %Y %I:%M %p")
    return Agent(
        name="Source research agent",
        model=MODEL,
        instructions=(
            f"Current date and time: {now}. "
            "You gather evidence for a research report using only the provided Olostep tools. "
            "Always include the current year in your search queries to get the most recent results. "
            "Prefer recent, official, primary, and reputable sources. "
            "First try search_with_scrape for the original query. If the scraped search result is weak, "
            "run two or three targeted search_web calls, select only the most important URLs, scrape those URLs, "
            "and summarize the evidence. "
            "Return only the structured source research report."
        ),
        tools=[search_web, search_with_scrape, scrape_url],
        output_type=SourceResearchReport,
    )

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
        "Use short paragraphs, bullets where helpful, and citations as Markdown links or URL bullets. "
        "Add enough context that a non-expert reader understands the issue, why it matters, and what evidence supports it. "
        "Return only the structured report."
    ),
    output_type=MarkdownResearchReport,
)

judge_tool = judge_agent.as_tool(
    tool_name="judge_answer_quality",
    tool_description="Judge whether an answer or evidence is good enough for the original research question.",
)

source_research_tool = _build_source_research_agent().as_tool(
    tool_name="run_source_research",
    tool_description="Run Olostep search-with-scrape, targeted searches, URL selection, and URL scraping to gather source evidence.",
)

analyst_tool = analyst_agent.as_tool(
    tool_name="write_markdown_research_report",
    tool_description="Write the final structured Markdown research report from the gathered evidence.",
)

manager_agent = Agent(
    name="Manager research agent",
    model=MODEL,
    instructions=(
        "You are the orchestrator for a multi-agent research assistant. Follow this exact policy:\n"
        "1. Always call answer_query first for the user's question.\n"
        "2. Call judge_answer_quality on that Answer API result.\n"
        "3. If the judge says the answer is good enough, call write_markdown_research_report using the answer result.\n"
        "4. If the judge says the answer is not good enough, call run_source_research. The source researcher must use search_with_scrape first, then targeted searches and scrape_url if needed.\n"
        "5. Call write_markdown_research_report using all evidence.\n"
        "6. Return a complete MarkdownResearchReport. Do not return a casual chat answer."
    ),
    tools=[answer_query, judge_tool, source_research_tool, analyst_tool],
    output_type=MarkdownResearchReport,
)


async def run_research_assistant(query: str, progress: ProgressCallback | None = None) -> tuple[MarkdownResearchReport, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to .env and restart the app.")
    require_olostep_key()

    token = _progress_callback.set(progress)
    trace_id = gen_trace_id()
    trace_url = openai_trace_url(trace_id)

    try:
        await emit_progress("Starting manager research agent.")
        prompt = f"""
Research question:
{query}

Return a polished, reader-friendly Markdown research report with substantial detail for the user's specific question. Follow the required workflow exactly:
- Answer API first.
- Judge agent second.
- If weak, source research agent with search_with_scrape, targeted search_web calls, URL selection, and scrape_url.
- Analyst agent writes the final Markdown report. Do not include Limitations or Next Steps sections.
"""
        with trace(
            workflow_name="multi_agent_research_assistant_olostep",
            trace_id=trace_id,
            metadata={"query": query, "app": "reflex_research_assistant"},
        ):
            with custom_span("manager.run", {"query": query}):
                result = await Runner.run(manager_agent, prompt, max_turns=20)

        await emit_progress("Manager run completed. Flushing OpenAI traces.")
        flush_traces()
        await emit_progress("Trace flushed. Rendering Markdown report.")
        return result.final_output, trace_url
    finally:
        _progress_callback.reset(token)
