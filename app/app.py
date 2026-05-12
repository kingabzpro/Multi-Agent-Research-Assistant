from __future__ import annotations

import reflex as rx

from .report_formatting import MARKDOWN_CSS
from .state import State


PAGE_BG = "linear-gradient(135deg, #fbfdff 0%, #fffdf7 48%, #f8fff9 100%)"
PAGE_PADDING = {"initial": "1rem", "sm": "1.25rem", "lg": "2rem"}
PANEL_PADDING = {"initial": "1rem", "sm": "1.25rem"}


def status_badge() -> rx.Component:
    return rx.badge(
        State.status,
        color_scheme=rx.cond(
            State.status == "Complete",
            "green",
            rx.cond(State.status == "Failed", "red", "blue"),
        ),
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
                lambda item: rx.text(
                    item,
                    font_family="monospace",
                    font_size="0.8rem",
                    color="#263238",
                ),
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


def report_panel() -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.spacer(),
            rx.button(
                rx.icon("download", size=17),
                "Download PDF",
                on_click=State.download_pdf,
                background="#2f9e44",
                color="white",
                border_radius="8px",
                padding_x="1rem",
                padding_y="0.45rem",
                cursor="pointer",
                margin_top="1rem",
                margin_right="1rem",
                _hover={
                    "background": "#238b36",
                    "transform": "translateY(-1px)",
                    "box_shadow": "0 4px 12px rgba(47, 158, 68, 0.35)",
                },
                transition="all 0.2s ease",
            ),
            justify="end",
            align="start",
            width="100%",
        ),
        rx.html(
            MARKDOWN_CSS
            + '<div class="md-report" style="padding: 0.5rem 1.25rem 1rem;">'
            + State.report_html
            + "</div>",
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


def search_bar() -> rx.Component:
    return rx.hstack(
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
    )


def prompt_suggestions() -> rx.Component:
    return rx.hstack(
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
    )


def page_header() -> rx.Component:
    return rx.vstack(
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
    )


def result_area() -> rx.Component:
    return rx.cond(
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
    )


def index() -> rx.Component:
    return rx.box(
        rx.vstack(
            page_header(),
            search_bar(),
            prompt_suggestions(),
            rx.cond(
                State.error != "",
                rx.callout(State.error, icon="triangle_alert", color_scheme="red", width="100%"),
            ),
            result_area(),
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
