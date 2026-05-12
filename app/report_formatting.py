from __future__ import annotations

import re

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor


MARKDOWN_CSS = """
<style>
  .md-report h1 { font-size: 1.65rem; font-weight: 700; margin: 1.4rem 0 0.6rem; color: #101828; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.35rem; }
  .md-report h2 { font-size: 1.35rem; font-weight: 600; margin: 1.2rem 0 0.5rem; color: #1e293b; border-bottom: 1px solid #f1f5f9; padding-bottom: 0.25rem; }
  .md-report h3 { font-size: 1.12rem; font-weight: 600; margin: 1rem 0 0.4rem; color: #334155; }
  .md-report h4 { font-size: 1rem; font-weight: 600; margin: 0.8rem 0 0.3rem; color: #475569; }
  .md-report p  { margin: 0.5rem 0; line-height: 1.7; color: #374151; }
  .md-report ul, .md-report ol { margin: 0.5rem 0 0.5rem 1.5rem; padding: 0; }
  .md-report ul { list-style-type: disc; }
  .md-report ol { list-style-type: decimal; }
  .md-report li { margin: 0.25rem 0; line-height: 1.65; color: #374151; }
  .md-report li > ul, .md-report li > ol { margin: 0.2rem 0 0.2rem 1.2rem; }
  .md-report strong { font-weight: 700; color: #111827; }
  .md-report em { font-style: italic; }
  .md-report blockquote { border-left: 4px solid #94a3b8; margin: 0.75rem 0; padding: 0.5rem 1rem; background: #f8fafc; color: #475569; border-radius: 0 4px 4px 0; }
  .md-report code { background: #f1f5f9; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.88em; color: #7c3aed; }
  .md-report pre { background: #1e293b; color: #e2e8f0; padding: 1rem; border-radius: 8px; overflow-x: auto; margin: 0.75rem 0; }
  .md-report pre code { background: none; color: inherit; padding: 0; font-size: 0.88em; }
  .md-report table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; }
  .md-report th, .md-report td { border: 1px solid #e5e7eb; padding: 0.5rem 0.75rem; text-align: left; }
  .md-report th { background: #f8fafc; font-weight: 600; color: #1e293b; }
  .md-report hr { border: none; border-top: 1px solid #e5e7eb; margin: 1.2rem 0; }
  .md-report a { color: #2563eb; text-decoration: underline; }
</style>
"""

_REFERENCE_RETURN_MARKERS = re.compile(r"(?:\s*(?:↩️|↩|🔙|↪️|↪)){1,}")


def plain_markdown(value) -> str:
    if isinstance(value, str):
        return clean_markdown(value)
    if isinstance(value, dict):
        nested = value.get("markdown_report")
        text = nested if isinstance(nested, str) else str(nested or value)
        return clean_markdown(text)
    nested = getattr(value, "markdown_report", None)
    text = nested if isinstance(nested, str) else str(value)
    return clean_markdown(text)


def clean_markdown(value: str) -> str:
    return _REFERENCE_RETURN_MARKERS.sub("", value)


def markdown_to_html(value: str) -> str:
    return markdown.markdown(
        value,
        extensions=["extra", "sane_lists", "tables", NewTabLinksExtension()],
        output_format="html5",
    )


class NewTabLinksTreeprocessor(Treeprocessor):
    def run(self, root):
        for element in root.iter("a"):
            element.set("target", "_blank")
            element.set("rel", "noopener noreferrer")
        return root


class NewTabLinksExtension(Extension):
    def extendMarkdown(self, md):
        md.treeprocessors.register(NewTabLinksTreeprocessor(md), "new_tab_links", 15)
