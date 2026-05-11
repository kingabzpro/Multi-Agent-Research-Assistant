import reflex as rx


config = rx.Config(
    app_name="app",
    env_file=".env",
    show_built_with_reflex=False,
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(
                appearance="light",
                accent_color="blue",
                gray_color="slate",
                radius="medium",
            )
        ),
    ],
)
