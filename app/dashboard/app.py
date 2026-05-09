"""Dash application factory.

Creates the Dash app with Bootstrap 5 theme, defines the layout,
and registers all callbacks.
"""

import dash
import dash_bootstrap_components as dbc

from app.dashboard.layouts import build_layout


def create_dash_app() -> dash.Dash:
    """Create and configure the Dash app."""
    app = dash.Dash(
        __name__,
        external_stylesheets=[
            dbc.themes.DARKLY,
            dbc.icons.FONT_AWESOME,
        ],
        requests_pathname_prefix="/dashboard/",
        suppress_callback_exceptions=True,
        title="Solar Control",
        update_title=None,
        meta_tags=[
            {"name": "viewport",
             "content": "width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no"},
        ],
    )

    app.layout = build_layout()

    # Register callbacks (import after layout to avoid circular deps)
    from app.dashboard import callbacks
    callbacks.register_callbacks(app)

    return app
