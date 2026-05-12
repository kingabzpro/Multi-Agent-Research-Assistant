# Multi-Agent Research Assistant

A multi-agent research assistant built with the OpenAI Agents SDK, Olostep, and Reflex.

https://github.com/user-attachments/assets/9aee7d1e-7d3d-4c11-b286-a6b11fef2d8d

Enter a research question and the manager agent coordinates judges, retrieval tools, and an analyst agent to produce a polished, source-backed Markdown research report. The Reflex app renders the report in the browser and exports a formatted PDF.

## Flow

```text
User question
    |
    v
Manager agent
    |
    +--> Olostep Answer API
    |        |
    |        v
    |    Judge agent
    |        |
    |        +--> Good enough
    |        |        |
    |        |        v
    |        |   Analyst agent --> Markdown report + sources
    |        |
    |        +--> Needs more evidence
    |                 |
    |                 v
    |          Search with Scrape
    |                 |
    |                 v
    |          Judge agent
    |                 |
    |                 +--> Good enough --> Analyst agent --> Markdown report + sources
    |                 |
    |                 +--> Still weak
    |                         |
    |                         v
    |                  Multiple targeted searches
    |                         |
    |                         v
    |                  Pick top 3 relevant URLs
    |                         |
    |                         v
    |                  Scrape selected pages
    |                         |
    |                         v
    +----------------> Analyst agent --> Markdown report + sources
```

![Trace Multi-Agent Research Assistant](research/image_1.png)

## Agents

| Agent | Role |
|---|---|
| **Manager** | Orchestrates the workflow and directly calls Olostep answer, search, and scrape tools. |
| **Judge** | Evaluates the simple answer and search-with-scrape evidence before deciding whether to continue. |
| **Analyst** | Writes the final Markdown research report from the gathered evidence. |

## Retrieval Policy

The manager follows a staged retrieval policy:

1. Call the Olostep Answer API for a simple first answer.
2. Ask the Judge whether that answer is sufficient (`score >= 0.85`).
3. If weak, run Olostep Search with Scrape and ask the Judge again using the same `0.85` threshold.
4. If still weak, run multiple targeted Olostep Search calls, select at least the top 3 relevant URLs, and scrape those pages.
5. Send all answer, judge, search, and scrape evidence to the Analyst for the final report.

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file from `.env.template`:

```bash
OPENAI_API_KEY=your_openai_api_key
OLOSTEP_API_KEY=your_olostep_api_key
OPENAI_MODEL=gpt-5.4-mini
```

## Run the Reflex app

```bash
reflex run
```

Then open the local URL printed by Reflex, usually:

```text
http://localhost:3000
```

## App Structure

The app files live in `app/`:

| File | Purpose |
|---|---|
| `app/app.py` | Reflex UI components and page registration only. |
| `app/state.py` | Reflex state, event handlers, progress logging, stop/reset behavior, and downloads. |
| `app/research_assistant.py` | OpenAI Agents SDK workflow with Manager, Judge, Analyst, and Olostep tools. |
| `app/report_formatting.py` | Markdown cleanup, browser HTML rendering, link behavior, and report CSS. |
| `app/pdf_export.py` | ReportLab-based PDF generation with headings, bullets, links, and Markdown table support. |

## Features

- **Multi-agent workflow**: Manager, Judge, and Analyst agents collaborate while the manager directly controls Olostep retrieval tools.
- **Live progress logs**: Watch each agent step in real time.
- **Styled Markdown report**: Headings, bullets, tables, code blocks, and more render properly in the browser.
- **Download report**: Export the full report as a formatted PDF using ReportLab.
- **Deep retrieval path**: If early evidence is weak, the manager runs targeted searches and scrapes at least the top 3 relevant pages.
