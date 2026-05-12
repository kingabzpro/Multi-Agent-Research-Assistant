from __future__ import annotations

import asyncio
import time

import reflex as rx

from .pdf_export import markdown_to_pdf_bytes
from .report_formatting import markdown_to_html, plain_markdown
from .research_assistant import run_research_assistant


_RUNNING_TASKS: dict[str, asyncio.Task] = {}


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
                self.report_markdown = plain_markdown(report.markdown_report)
                self.report_html = markdown_to_html(self.report_markdown)
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

    def download_pdf(self):
        if not self.report_markdown:
            return rx.window_alert("Generate a report before downloading.")
        try:
            pdf_bytes = markdown_to_pdf_bytes(self.report_markdown)
        except ImportError:
            return rx.window_alert(
                "PDF support is not installed. Run: pip install -r requirements.txt"
            )
        except Exception as exc:
            return rx.window_alert(f"Could not generate PDF: {exc}")
        return rx.download(data=pdf_bytes, filename="research-report.pdf")
