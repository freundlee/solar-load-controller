"""Dashboard layout components.

Two-page layout:
  /dashboard/          — Operations view (real-time monitoring + manual control)
  /dashboard/admin     — Admin panel (strategy config, profiles, simulation)

Uses dash-bootstrap-components (Bootstrap 5 / Darkly theme).
"""

import dash_bootstrap_components as dbc
from dash import dcc, html


# ===================================================================
# Helpers
# ===================================================================

def _metric(id_prefix: str, label: str, icon: str, unit: str = "W",
            color: str = "primary") -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.Div([
                html.I(className=f"fas {icon} me-2 text-{color}"),
                html.Span(label, className="text-muted small"),
            ]),
            html.Div([
                html.Span("--", id=f"{id_prefix}-value",
                           className=f"fs-3 fw-bold text-{color}"),
                html.Span(f" {unit}", className="text-muted ms-1"),
            ], className="mt-1"),
        ]),
        className="h-100",
    )


# ===================================================================
# OPERATIONS PAGE — Cards
# ===================================================================

def _realtime_metrics_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-bolt me-2"),
            "Real-time Metrics",
        ]),
        dbc.CardBody(
            dbc.Row([
                dbc.Col(_metric("solar", "Solar Production", "fa-sun", "W", "warning"), md=3),
                dbc.Col(_metric("battery", "Battery SOC", "fa-battery-three-quarters", "%", "success"), md=3),
                dbc.Col(_metric("meter", "Grid Meter", "fa-gauge-high", "W", "info"), md=3),
                dbc.Col(_metric("load", "Current Load", "fa-plug", "W", "danger"), md=3),
            ], className="g-3"),
        ),
    ], className="mb-3")


def _power_flow_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-arrows-alt me-2"),
            "Power Flow",
        ]),
        dbc.CardBody([
            html.Div([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-sun fa-2x text-warning"),
                            html.Div("Solar", className="small text-muted mt-1"),
                            html.Div("--", id="flow-solar", className="fw-bold text-warning"),
                        ], className="text-center"),
                    ], width=2),
                    dbc.Col([
                        html.Div("⟶", id="flow-arrow-solar-battery",
                                 className="fs-3 text-center text-warning mt-2"),
                    ], width=1),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-battery-three-quarters fa-2x text-success"),
                            html.Div("Battery", className="small text-muted mt-1"),
                            html.Div([
                                html.Span("--", id="flow-battery-soc", className="fw-bold text-success"),
                                html.Span(" %", className="text-muted small"),
                            ]),
                            html.Div([
                                html.Span("--", id="flow-battery-power", className="small text-success"),
                                html.Span(" W", className="text-muted small"),
                            ]),
                        ], className="text-center"),
                    ], width=2),
                    dbc.Col([
                        html.Div("⟶", id="flow-arrow-battery-home",
                                 className="fs-3 text-center text-success mt-2"),
                    ], width=1),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-home fa-2x text-light"),
                            html.Div("Home", className="small text-muted mt-1"),
                            html.Div("--", id="flow-home", className="fw-bold"),
                        ], className="text-center"),
                    ], width=2),
                    dbc.Col([
                        html.Div("⟵", id="flow-arrow-grid-home",
                                 className="fs-3 text-center text-danger mt-2"),
                    ], width=1),
                    dbc.Col([
                        html.Div([
                            html.I(className="fas fa-tower-broadcast fa-2x", id="flow-grid-icon"),
                            html.Div("Grid", className="small text-muted mt-1"),
                            html.Div("--", id="flow-grid", className="fw-bold"),
                        ], className="text-center"),
                    ], width=2),
                ], className="align-items-center justify-content-center"),
            ]),
        ]),
    ], className="mb-3")


def _manual_control_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-sliders-h me-2"),
            "Load Control",
        ]),
        dbc.CardBody([
            # Auto mode toggle
            dbc.Row([
                dbc.Col([
                    dbc.Switch(
                        id="auto-mode-switch",
                        label="Auto Mode",
                        value=True,
                        className="fs-5",
                    ),
                ], md=4),
                dbc.Col([
                    html.Div(id="auto-mode-status", className="text-muted"),
                ], md=8),
            ], className="mb-3"),
            html.Hr(),
            # Manual slider
            html.Label("Manual Load Setting", className="fw-bold"),
            dbc.Row([
                dbc.Col([
                    dcc.Slider(
                        id="load-slider",
                        min=0, max=800, step=10,
                        value=200,
                        marks={i: f"{i}" for i in range(0, 801, 100)},
                        tooltip={"placement": "top", "always_visible": True},
                        className="mb-2",
                    ),
                ], md=8),
                dbc.Col([
                    html.Div([
                        html.Span(id="load-slider-display", className="fs-4 fw-bold"),
                        html.Span(" W", className="text-muted"),
                    ], className="text-center"),
                ], md=4),
            ]),
            dbc.Row([
                dbc.Col(
                    dbc.Button("Set Load", id="btn-set-load", color="primary",
                               className="w-100", size="lg"),
                    md=4,
                ),
                dbc.Col(
                    dbc.Button("Max (800W)", id="btn-max-load", color="warning",
                               className="w-100", size="lg"),
                    md=4,
                ),
                dbc.Col(
                    dbc.Button("Min (0W)", id="btn-min-load", color="secondary",
                               className="w-100", size="lg"),
                    md=4,
                ),
            ], className="mt-3 g-2"),
            html.Div(id="load-status-msg", className="mt-3"),
        ]),
    ], className="mb-3")


def _auto_status_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-robot me-2"),
            "Auto Control Status",
        ]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div("State", className="text-muted small"),
                    html.Div("--", id="strategy-state", className="fw-bold fs-5"),
                ], md=3),
                dbc.Col([
                    html.Div("Adjustments", className="text-muted small"),
                    html.Div("--", id="strategy-adjustments", className="fw-bold fs-5"),
                ], md=3),
                dbc.Col([
                    html.Div("Spikes Detected", className="text-muted small"),
                    html.Div("--", id="strategy-spikes", className="fw-bold fs-5"),
                ], md=3),
                dbc.Col([
                    html.Div("Spikes Ignored", className="text-muted small"),
                    html.Div("--", id="strategy-ignored", className="fw-bold fs-5"),
                ], md=3),
            ]),
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    html.Span("Avg 30s: ", className="text-muted small"),
                    html.Span("--", id="strategy-avg30", className="fw-bold"),
                    html.Span(" W", className="text-muted small"),
                ], md=4),
                dbc.Col([
                    html.Span("Avg 60s: ", className="text-muted small"),
                    html.Span("--", id="strategy-avg60", className="fw-bold"),
                    html.Span(" W", className="text-muted small"),
                ], md=4),
                dbc.Col([
                    html.Span("Baseline: ", className="text-muted small"),
                    html.Span("--", id="strategy-baseline", className="fw-bold"),
                    html.Span(" W", className="text-muted small"),
                ], md=4),
            ], className="mb-2"),
            html.Div([
                html.Span("Last action: ", className="text-muted"),
                html.Span("--", id="strategy-last-action"),
            ]),
            html.Div([
                html.Span("Current spike: ", className="text-muted"),
                html.Span("--", id="strategy-current-spike"),
            ], className="mt-1"),
        ]),
    ], className="mb-3")


def _daily_summary_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-chart-bar me-2"),
            "Today's Summary",
        ]),
        dbc.CardBody(
            dbc.Row([
                dbc.Col([
                    html.Div("Solar", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-solar", className="fw-bold fs-5 text-warning"),
                        html.Span(" kWh", className="text-muted"),
                    ]),
                ], md=2),
                dbc.Col([
                    html.Div("Charged", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-charge", className="fw-bold fs-5 text-success"),
                        html.Span(" kWh", className="text-muted"),
                    ]),
                ], md=2),
                dbc.Col([
                    html.Div("Discharged", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-discharge", className="fw-bold fs-5 text-info"),
                        html.Span(" kWh", className="text-muted"),
                    ]),
                ], md=2),
                dbc.Col([
                    html.Div("Home Usage", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-usage", className="fw-bold fs-5 text-light"),
                        html.Span(" kWh", className="text-muted"),
                    ]),
                ], md=2),
                dbc.Col([
                    html.Div("Grid Import", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-grid-import", className="fw-bold fs-5 text-danger"),
                        html.Span(" kWh", className="text-muted"),
                    ]),
                ], md=2),
                dbc.Col([
                    html.Div("Cost Saved", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-cost-saved", className="fw-bold fs-5 text-success"),
                        html.Span(" €", className="text-muted"),
                    ]),
                ], md=2),
            ], className="g-3"),
        ),
    ], className="mb-3")


def _live_meter_chart_card() -> dbc.Card:
    """Real-time meter reading chart (last 5 minutes from in-memory buffer)."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-wave-square me-2"),
            "Live Grid Meter (5 min)",
        ]),
        dbc.CardBody([
            dcc.Graph(id="live-meter-chart", config={"displayModeBar": False},
                      style={"height": "250px"}),
        ]),
    ], className="mb-3")


def _history_chart_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-chart-line me-2"),
            "Load & Meter History (24h)",
        ]),
        dbc.CardBody([
            dcc.Graph(id="history-chart", config={"displayModeBar": False},
                      style={"height": "300px"}),
        ]),
    ], className="mb-3")


def _iometer_status_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-wifi me-2"),
            "IOMeter Status",
        ]),
        dbc.CardBody(
            dbc.Row([
                dbc.Col([
                    html.Div("Connection", className="text-muted small"),
                    html.Div([
                        html.I(className="fas fa-circle me-1", id="iometer-conn-icon"),
                        html.Span("--", id="iometer-conn-status"),
                    ]),
                ], md=3),
                dbc.Col([
                    html.Div("Signal", className="text-muted small"),
                    html.Div("--", id="iometer-signal", className="fw-bold"),
                ], md=3),
                dbc.Col([
                    html.Div("Battery", className="text-muted small"),
                    html.Div("--", id="iometer-battery", className="fw-bold"),
                ], md=3),
                dbc.Col([
                    html.Div("Meter No.", className="text-muted small"),
                    html.Div("--", id="iometer-meter-no", className="fw-bold small"),
                ], md=3),
            ]),
        ),
    ], className="mb-3")


# ===================================================================
# ADMIN PAGE — Cards
# ===================================================================

def _strategy_config_card() -> dbc.Card:
    config_items = [
        ("polling_interval_s", "Polling Interval", "s", 5),
        ("reaction_delay_s", "Reaction Delay", "s", 15),
        ("spike_observation_period_s", "Spike Observation", "s", 90),
        ("cooldown_period_s", "Cooldown Period", "s", 45),
        ("min_change_threshold_w", "Min Change Threshold", "W", 30),
        ("emergency_threshold_w", "Emergency Threshold", "W", 500),
        ("grid_target_w", "Grid Target", "W", -10),
        ("max_load_w", "Max Load", "W", 800),
        ("min_load_w", "Min Load", "W", 0),
        ("load_step_w", "Load Step", "W", 10),
        ("electricity_price_eur_kwh", "Electricity Price", "€/kWh", 0.28),
        ("feed_in_tariff_eur_kwh", "Feed-in Tariff", "€/kWh", 0.082),
    ]

    rows = []
    for key, label, unit, default in config_items:
        rows.append(
            dbc.Row([
                dbc.Col(html.Label(f"{label} ({unit})", className="small"), md=5),
                dbc.Col(
                    dbc.Input(
                        id={"type": "config-input", "key": key},
                        type="number",
                        value=default,
                        size="sm",
                        className="bg-dark text-light border-secondary",
                    ),
                    md=4,
                ),
                dbc.Col(
                    dbc.Button(
                        html.I(className="fas fa-save"),
                        id={"type": "config-save-btn", "key": key},
                        color="outline-success",
                        size="sm",
                    ),
                    md=1,
                ),
            ], className="mb-2 align-items-center"),
        )

    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-cog me-2"),
            "Strategy Configuration",
        ]),
        dbc.CardBody([
            html.P("Adjust strategy parameters. Changes take effect on the next control cycle.",
                    className="text-muted small mb-3"),
            *rows,
            html.Div(id="config-status-msg", className="mt-2"),
        ]),
    ], className="mb-3")


def _profiles_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-plug me-2"),
            "Appliance Profiles",
        ]),
        dbc.CardBody([
            html.Div(id="profiles-table"),
            html.Hr(),
            html.H6("Add / Edit Profile", className="mt-3"),
            dbc.Row([
                dbc.Col(dbc.Input(id="profile-name", placeholder="Name", size="sm",
                                  className="bg-dark text-light border-secondary"), md=2),
                dbc.Col(dbc.Input(id="profile-min-w", placeholder="Min W", type="number",
                                  size="sm", className="bg-dark text-light border-secondary"), md=2),
                dbc.Col(dbc.Input(id="profile-max-w", placeholder="Max W", type="number",
                                  size="sm", className="bg-dark text-light border-secondary"), md=2),
                dbc.Col(dbc.Input(id="profile-typ-dur", placeholder="Typ. dur (s)", type="number",
                                  size="sm", className="bg-dark text-light border-secondary"), md=2),
                dbc.Col(dbc.Select(id="profile-action", options=[
                    {"label": "Ignore", "value": "ignore"},
                    {"label": "Observe", "value": "observe"},
                    {"label": "Adjust", "value": "adjust"},
                ], value="observe", size="sm",
                    className="bg-dark text-light border-secondary"), md=2),
                dbc.Col(dbc.Button("Add", id="btn-add-profile", color="success",
                                   size="sm", className="w-100"), md=2),
            ], className="g-2"),
            html.Div(id="profile-status-msg", className="mt-2"),
        ]),
    ], className="mb-3")


def _recent_events_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-list me-2"),
            "Recent Load Changes",
        ]),
        dbc.CardBody([
            html.Div(id="recent-events-table"),
        ]),
    ], className="mb-3")


# ===================================================================
# NAVBAR (shared)
# ===================================================================

def _navbar() -> dbc.Navbar:
    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand([
                html.I(className="fas fa-solar-panel me-2"),
                "Solar Load Controller",
            ], className="fs-4"),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink("Dashboard", href="/dashboard/", active="exact")),
                dbc.NavItem(dbc.NavLink("Admin", href="/dashboard/admin", active="exact")),
                dbc.NavItem(html.Span(id="header-time", className="text-muted nav-link")),
            ], navbar=True),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-3",
    )


# ===================================================================
# PAGE: Operations Dashboard
# ===================================================================

def _operations_page() -> html.Div:
    return html.Div([
        # Row 1: Real-time metrics
        _realtime_metrics_card(),

        # Row 2: Power flow
        _power_flow_card(),

        # Row 3: Manual control + Auto status
        dbc.Row([
            dbc.Col(_manual_control_card(), lg=6),
            dbc.Col(_auto_status_card(), lg=6),
        ]),

        # Row 4: Daily summary
        _daily_summary_card(),

        # Row 5: Live meter chart
        _live_meter_chart_card(),

        # Row 6: History chart
        _history_chart_card(),

        # Row 7: IOMeter status
        _iometer_status_card(),
    ])


# ===================================================================
# PAGE: Admin Panel
# ===================================================================

def _admin_page() -> html.Div:
    return html.Div([
        html.H4([
            html.I(className="fas fa-tools me-2"),
            "Administration",
        ], className="mb-3"),

        dbc.Row([
            dbc.Col(_strategy_config_card(), lg=6),
            dbc.Col([
                _profiles_card(),
            ], lg=6),
        ]),

        _recent_events_card(),
    ])


# ===================================================================
# MAIN LAYOUT (multi-page with dcc.Location)
# ===================================================================

def build_layout() -> html.Div:
    return html.Div([
        dcc.Location(id="url", refresh=False),

        # Interval timers for auto-refresh
        dcc.Interval(id="interval-fast", interval=3_000, n_intervals=0),
        dcc.Interval(id="interval-medium", interval=10_000, n_intervals=0),
        dcc.Interval(id="interval-slow", interval=300_000, n_intervals=0),

        # Hidden stores
        dcc.Store(id="store-prev-load", data=0),

        # Navbar
        _navbar(),

        # Page content
        dbc.Container(id="page-content", fluid=True),

        # Footer
        dbc.Container([
            html.Footer([
                html.Hr(),
                html.P([
                    "Solar Load Controller v1.1 | ",
                    html.Span(id="footer-status", className="text-muted"),
                ], className="text-center text-muted small"),
            ]),
        ], fluid=True),
    ])


def get_operations_page() -> html.Div:
    return _operations_page()


def get_admin_page() -> html.Div:
    return _admin_page()
