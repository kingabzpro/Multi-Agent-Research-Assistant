from __future__ import annotations

import asyncio
import re
import time

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
import reflex as rx

from .research_assistant import environment_status, run_research_assistant


PAGE_BG = "linear-gradient(135deg, #fbfdff 0%, #fffdf7 48%, #f8fff9 100%)"
PAGE_PADDING = {"initial": "1rem", "sm": "1.25rem", "lg": "2rem"}
PANEL_PADDING = {"initial": "1rem", "sm": "1.25rem"}
_RUNNING_TASKS: dict[str, asyncio.Task] = {}
_REFERENCE_RETURN_MARKERS = re.compile(r"(?:\s*(?:↩️|↩|🔙|↪️|↪)){1,}")


def _plain_markdown(value) -> str:
    if isinstance(value, str):
        return _clean_markdown(value)
    if isinstance(value, dict):
        nested = value.get("markdown_report")
        text = nested if isinstance(nested, str) else str(nested or value)
        return _clean_markdown(text)
    nested = getattr(value, "markdown_report", None)
    text = nested if isinstance(nested, str) else str(value)
    return _clean_markdown(text)


def _clean_markdown(value: str) -> str:
    return _REFERENCE_RETURN_MARKERS.sub("", value)


class NewTabLinksTreeprocessor(Treeprocessor):
    def run(self, root):
        for element in root.iter("a"):
            element.set("target", "_blank")
            element.set("rel", "noopener noreferrer")
        return root


class NewTabLinksExtension(Extension):
    def extendMarkdown(self, md):
        md.treeprocessors.register(NewTabLinksTreeprocessor(md), "new_tab_links", 15)


class State(rx.State):
    query: str = ""
    logs: list[str] = []
    report_markdown: str = ""
    report_html: str = ""
    trace_url: str = ""
    error: str = ""
    is_running: bool = False
    status: str = "Ready"
    active_run_id: int = 0
    step_started_at: float = 0.0

    def set_query(self, value: str) -> None:
        self.query = value

    def _client_token(self) -> str:
        return self.router.session.client_token or "default"

    def _cancel_active_task(self) -> bool:
        task = _RUNNING_TASKS.pop(self._client_token(), None)
        if task is not None and not task.done():
            task.cancel()
            return True
        return False

    def clear_all(self) -> None:
        self._cancel_active_task()
        self.active_run_id += 1
        self.query = ""
        self.logs = []
        self.report_markdown = ""
        self.report_html = ""
        self.trace_url = ""
        self.error = ""
        self.is_running = False
        self.status = "Ready"
        self.step_started_at = 0.0

    def stop_report(self) -> None:
        if not self.is_running:
            return
        now = time.monotonic()
        elapsed = max(0.0, now - self.step_started_at) if self.step_started_at else 0.0
        self._cancel_active_task()
        self.is_running = False
        self.error = ""
        self.status = "Stopped"
        self.step_started_at = now
        self.logs.append(f"{elapsed:.1f}s  Research stopped by user.")

    async def _log(self, message: str) -> None:
        async with self:
            now = time.monotonic()
            elapsed = max(0.0, now - self.step_started_at) if self.step_started_at else 0.0
            self.step_started_at = now
            self.logs.append(f"{elapsed:.1f}s  {message}")

    def handle_key_down(self, key: str):
        if key == "Enter":
            return State.run_report

    @rx.event(background=True)
    async def run_report(self):
        task = asyncio.current_task()
        run_id = 0
        async with self:
            query = self.query.strip()
            if not query:
                self.error = ""
                return
            self.active_run_id += 1
            run_id = self.active_run_id
            if task is not None:
                _RUNNING_TASKS[self._client_token()] = task
            self.logs = []
            self.report_markdown = ""
            self.report_html = ""
            self.trace_url = ""
            self.error = ""
            self.is_running = True
            self.status = "Researching"
            self.step_started_at = time.monotonic()

        try:
            report, trace_url = await run_research_assistant(query, progress=self._log)
            async with self:
                self.report_markdown = _plain_markdown(report.markdown_report)
                self.report_html = markdown.markdown(
                    self.report_markdown,
                    extensions=["extra", "sane_lists", "tables", NewTabLinksExtension()],
                    output_format="html5",
                )
                self.trace_url = trace_url
                self.status = "Complete"
        except asyncio.CancelledError:
            async with self:
                if self.active_run_id == run_id:
                    self.error = ""
                    self.status = "Stopped"
        except Exception as exc:
            async with self:
                if self.active_run_id == run_id:
                    self.error = str(exc)
                    self.status = "Failed"
        finally:
            async with self:
                if self.active_run_id == run_id:
                    self.is_running = False
                    _RUNNING_TASKS.pop(self._client_token(), None)

    def download_markdown(self):
        if not self.report_markdown:
            return rx.window_alert("Generate a report before downloading.")
        return rx.download(data=self.report_markdown, filename="research-report.md")


def status_badge() -> rx.Component:
    return rx.badge(
        State.status,
        color_scheme=rx.cond(State.status == "Complete", "green", rx.cond(State.status == "Failed", "red", "blue")),
        variant="soft",
        size="2",
    )


def log_panel() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.icon("activity", size=18, color="#0b7285"),
                rx.heading("Working", size="3", color="#14323b"),
                align="center",
                spacing="2",
            ),
            status_badge(),
            justify="between",
            align="center",
            width="100%",
        ),
        rx.vstack(
            rx.foreach(
                State.logs,
                lambda item: rx.text(item, font_family="monospace", font_size="0.8rem", color="#263238"),
            ),
            align="stretch",
            spacing="2",
            margin_top="0.6rem",
        ),
        max_height="10rem",
        overflow_y="auto",
        padding="0.85rem",
        border="1px solid #b6e3ea",
        border_radius="8px",
        background="rgba(235, 251, 255, 0.9)",
        box_shadow="0 8px 24px rgba(8, 92, 115, 0.10)",
        width="100%",
    )


_MARKDOWN_CSS = """
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


def report_panel() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.spacer(),
            rx.button(
                rx.icon("download", size=17),
                "Download",
                on_click=State.download_markdown,
                background="#2f9e44",
                color="white",
                border_radius="8px",
                padding_x="1rem",
                padding_y="0.45rem",
                cursor="pointer",
                margin_top="1rem",
                margin_right="1rem",
                _hover={"background": "#238b36", "transform": "translateY(-1px)", "box_shadow": "0 4px 12px rgba(47, 158, 68, 0.35)"},
                transition="all 0.2s ease",
            ),
            justify="end",
            align="start",
            width="100%",
        ),
        rx.html(
            _MARKDOWN_CSS + '<div class="md-report" style="padding: 0.5rem 1.25rem 1rem;">' + State.report_html + "</div>",
            width="100%",
            overflow_x="auto",
        ),
        padding=PANEL_PADDING,
        border="1px solid #dde6ec",
        border_radius="8px",
        background="rgba(255, 255, 255, 0.96)",
        box_shadow="0 16px 40px rgba(36, 48, 58, 0.10)",
        width="100%",
        overflow_x="auto",
    )


def index() -> rx.Component:
    _ok, _missing, _olostep_ver, _openai_ver = environment_status()
    return rx.box(
        rx.vstack(
            rx.vstack(
                rx.heading(
                    "What do you want to research today?",
                    size={"initial": "6", "md": "7"},
                    weight="regular",
                    color="#101828",
                    text_align="center",
                    line_height="1.15",
                ),
                rx.hstack(
                    rx.badge("Manager", color_scheme="blue", variant="soft", size="2", border_radius="999px"),
                    rx.badge("Judge", color_scheme="orange", variant="soft", size="2", border_radius="999px"),
                    rx.badge("Researcher", color_scheme="purple", variant="soft", size="2", border_radius="999px"),
                    rx.badge("Analyst", color_scheme="green", variant="soft", size="2", border_radius="999px"),
                    justify="center",
                    align="center",
                    wrap="wrap",
                    spacing="2",
                ),
                width="100%",
                align="center",
                spacing="3",
            ),
            rx.hstack(
                rx.input(
                    value=State.query,
                    on_change=State.set_query,
                    on_key_down=State.handle_key_down,
                    placeholder="Ask anything",
                    height="2.8rem",
                    width="100%",
                    flex="1 1 auto",
                    min_width="0",
                    background="transparent",
                    border="0",
                    box_shadow="none",
                    font_size="1.05rem",
                    margin_left="1.5rem",
                    padding_left="0",
                    text_indent="0.85rem",
                    padding_right={"initial": "0.75rem", "sm": "1rem"},
                ),
                rx.button(
                    rx.icon("rotate_ccw", size=19),
                    on_click=State.clear_all,
                    aria_label="Reset",
                    height="3.15rem",
                    width="3.15rem",
                    min_width="3.15rem",
                    padding="0",
                    flex="0 0 auto",
                    border_radius="8px",
                    background="transparent",
                    color="#111111",
                    box_shadow="none",
                    cursor="pointer",
                    _hover={"background": "#f3f4f6"},
                ),
                rx.cond(
                    State.is_running,
                    rx.button(
                        rx.icon("square", size=16),
                        on_click=State.stop_report,
                        aria_label="Stop",
                        height="3.15rem",
                        width="3.15rem",
                        min_width="3.15rem",
                        padding="0",
                        flex="0 0 auto",
                        border_radius="999px",
                        background="#111111",
                        color="white",
                        cursor="pointer",
                        position="relative",
                        z_index="1",
                        margin_right="1rem",
                    ),
                    rx.button(
                        rx.icon("search", size=17),
                        on_click=State.run_report,
                        aria_label="Search",
                        height="3.15rem",
                        width="3.15rem",
                        min_width="3.15rem",
                        padding="0",
                        flex="0 0 auto",
                        border_radius="999px",
                        background="#111111",
                        color="white",
                        cursor="pointer",
                        position="relative",
                        z_index="1",
                        margin_right="1rem",
                    ),
                ),
                width="100%",
                min_height="5rem",
                align="center",
                justify="between",
                spacing={"initial": "3", "sm": "4"},
                align_self="center",
                padding={
                    "initial": "0.75rem 1.85rem 0.75rem 1.2rem",
                    "sm": "0.8rem 2.35rem 0.8rem 1.6rem",
                },
                border="1px solid #d8d8d8",
                border_radius="999px",
                background="rgba(255, 255, 255, 0.96)",
                box_shadow="0 18px 55px rgba(16, 24, 40, 0.12)",
            ),
            rx.hstack(
                rx.button(
                    "Is remote work dying in 2026?",
                    on_click=State.set_query("Is remote work dying in 2026?"),
                    variant="soft",
                    color_scheme="gray",
                    border_radius="999px",
                ),
                rx.button(
                    "What's behind the global coffee shortage?",
                    on_click=State.set_query("What's behind the global coffee shortage?"),
                    variant="soft",
                    color_scheme="gray",
                    border_radius="999px",
                ),
                rx.button(
                    "Are electric cars actually cheaper to own?",
                    on_click=State.set_query("Are electric cars actually cheaper to own?"),
                    variant="soft",
                    color_scheme="gray",
                    border_radius="999px",
                ),
                justify="center",
                align="center",
                wrap="wrap",
                spacing="3",
                width="100%",
            ),
            rx.cond(State.error != "", rx.callout(State.error, icon="triangle_alert", color_scheme="red", width="100%")),
            rx.cond(
                State.is_running,
                log_panel(),
                rx.cond(
                    State.report_markdown != "",
                    report_panel(),
                    rx.box(
                        rx.text("Enter a question and press Search.", color="#52616b", align="center"),
                        padding="0.25rem",
                        width="100%",
                    ),
                ),
            ),
            spacing="5",
            align="stretch",
            padding=PANEL_PADDING,
            width="100%",
            max_width="780px",
            margin_x="auto",
        ),
        width="100%",
        max_width="100vw",
        padding=PAGE_PADDING,
        min_height="100vh",
        background=PAGE_BG,
        overflow_x="hidden",
        display="flex",
        align_items="center",
        justify_content="center",
    )


app = rx.App()
app.add_page(index, route="/", title="Multi-Agent Research Assistant")
