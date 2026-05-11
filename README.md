# Multi-Agent Research Assistant

A Jupyter notebook that builds a multi-agent research assistant with the OpenAI Agents SDK and Olostep.

The workflow uses a manager agent to orchestrate a judge agent, source research agent, and analyst agent. It tries Olostep Answer API first, escalates to search-with-scrape when needed, and returns a polished Markdown research report with sources.

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
    |        +--> Good enough --> Analyst agent --> Markdown report
    |        |
    |        +--> Needs more evidence
    |                 |
    |                 v
    |          Source research agent
    |                 |
    |                 +--> Search with Scrape
    |                 +--> Targeted Search
    |                 +--> Scrape selected URLs
    |                 |
    |                 v
    |          Analyst agent
    |                 |
    |                 v
    +----------> Markdown research report + sources
```
![image.png](image.png)

## Setup

Create a `.env` file:

```bash
OPENAI_API_KEY=your_openai_api_key
OLOSTEP_API_KEY=your_olostep_api_key
RUN_LIVE_EXAMPLE=false
```

Open and run:

```text
multi_agent_research_assistant_openai_agents_olostep.ipynb
```

Set `RUN_LIVE_EXAMPLE=true` to run the live example. The notebook prints an OpenAI trace URL for inspecting the agent workflow.
