"""Dashboard layout components — mobile-first responsive design.

Two-page layout:
  /dashboard/          — Operations view (real-time monitoring + manual control)
  /dashboard/admin     — Admin panel (strategy config, profiles, events)

Uses dash-bootstrap-components (Bootstrap 5 / Darkly theme).
Designed for mobile-first access with responsive breakpoints.
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
                html.I(className=f"fas {icon} me-1 text-{color}"),
                html.Span(label, className="text-muted small"),
            ]),
            html.Div([
                html.Span("--", id=f"{id_prefix}-value",
                           className=f"fs-4 fw-bold text-{color}"),
                html.Span(f" {unit}", className="text-muted small"),
            ], className="mt-1"),
        ], className="p-2"),
        className="h-100",
    )


# ===================================================================
# OPERATIONS PAGE — Cards
# ===================================================================

def _realtime_metrics_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-bolt me-2"),
            "Real-time",
        ], className="py-2"),
        dbc.CardBody(
            dbc.Row([
                dbc.Col(_metric("solar", "Solar", "fa-sun", "W", "warning"), xs=6, md=3),
                dbc.Col(_metric("battery", "Battery", "fa-battery-three-quarters", "%", "success"), xs=6, md=3),
                dbc.Col(_metric("meter", "Grid", "fa-gauge-high", "W", "info"), xs=6, md=3),
                dbc.Col(_metric("load", "Load", "fa-plug", "W", "danger"), xs=6, md=3),
            ], className="g-2"),
            className="p-2",
        ),
    ], className="mb-3")


def _solar_detail_card() -> dbc.Card:
    """PV1/PV2/Microinverter per-channel solar production with daily energy."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-solar-panel me-2"),
            "Solar Channels",
        ], className="py-2"),
        dbc.CardBody(
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-sun text-warning me-1"),
                        html.Span("PV1", className="text-muted small"),
                    ]),
                    html.Div([
                        html.Span("--", id="pv1-value", className="fs-5 fw-bold text-warning"),
                        html.Span(" W", className="text-muted small"),
                    ]),
                    html.Div([
                        html.Span("--", id="pv1-kwh", className="small text-muted"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, className="text-center"),
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-sun text-warning me-1"),
                        html.Span("PV2", className="text-muted small"),
                    ]),
                    html.Div([
                        html.Span("--", id="pv2-value", className="fs-5 fw-bold text-warning"),
                        html.Span(" W", className="text-muted small"),
                    ]),
                    html.Div([
                        html.Span("--", id="pv2-kwh", className="small text-muted"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, className="text-center"),
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-microchip text-info me-1"),
                        html.Span("MI80", className="text-muted small"),
                    ]),
                    html.Div([
                        html.Span("--", id="mi-value", className="fs-5 fw-bold text-info"),
                        html.Span(" W", className="text-muted small"),
                    ]),
                    html.Div([
                        html.Span("--", id="mi-kwh", className="small text-muted"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, className="text-center"),
            ], className="g-2"),
            className="p-2",
        ),
    ], className="mb-3")


def _power_flow_card() -> dbc.Card:
    """Simplified power flow for mobile."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-arrows-alt me-2"),
            "Power Flow",
        ], className="py-2"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-sun fa-lg text-warning"),
                        html.Div("Solar", className="small text-muted"),
                        html.Div("--", id="flow-solar", className="fw-bold text-warning small"),
                    ], className="text-center"),
                ], xs=3),
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-battery-three-quarters fa-lg text-success"),
                        html.Div("Battery", className="small text-muted"),
                        html.Div([
                            html.Span("--", id="flow-battery-soc", className="fw-bold text-success small"),
                            html.Span("%", className="text-muted small"),
                        ]),
                        html.Div([
                            html.Span("--", id="flow-battery-power", className="small text-success"),
                            html.Span("W", className="text-muted small"),
                        ]),
                    ], className="text-center"),
                ], xs=3),
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-home fa-lg text-light"),
                        html.Div("Home", className="small text-muted"),
                        html.Div("--", id="flow-home", className="fw-bold small"),
                    ], className="text-center"),
                ], xs=3),
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-tower-broadcast fa-lg", id="flow-grid-icon"),
                        html.Div("Grid", className="small text-muted"),
                        html.Div("--", id="flow-grid", className="fw-bold small"),
                    ], className="text-center"),
                ], xs=3),
            ], className="align-items-center"),
        ], className="p-2"),
    ], className="mb-3")


def _manual_control_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-sliders-h me-2"),
            "Load Control",
        ], className="py-2"),
        dbc.CardBody([
            # Auto mode toggle
            dbc.Row([
                dbc.Col([
                    dbc.Switch(
                        id="auto-mode-switch",
                        label="Auto Mode",
                        value=True,
                        className="fs-6",
                    ),
                ], xs=5),
                dbc.Col([
                    html.Div(id="auto-mode-status", className="text-muted small"),
                ], xs=7),
            ], className="mb-2"),
            html.Hr(className="my-2"),
            # Manual slider
            html.Label("Manual Load", className="fw-bold small"),
            dcc.Slider(
                id="load-slider",
                min=0, max=800, step=10,
                value=200,
                marks={i: f"{i}" for i in range(0, 801, 200)},
                tooltip={"placement": "top", "always_visible": True},
                className="mb-2",
            ),
            dbc.Row([
                dbc.Col(
                    dbc.Button("Set", id="btn-set-load", color="primary",
                               className="w-100 py-2"),
                    xs=4,
                ),
                dbc.Col(
                    dbc.Button("800W", id="btn-max-load", color="warning",
                               className="w-100 py-2"),
                    xs=4,
                ),
                dbc.Col(
                    dbc.Button("0W", id="btn-min-load", color="secondary",
                               className="w-100 py-2"),
                    xs=4,
                ),
            ], className="g-2"),
            html.Div(id="load-status-msg", className="mt-2"),
            # Hidden display for slider value
            html.Span(id="load-slider-display", style={"display": "none"}),
        ], className="p-2"),
    ], className="mb-3")


def _auto_status_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-robot me-2"),
            "Auto Control",
            html.Span(id="strategy-change-status", className="ms-2"),
        ], className="py-2 d-flex align-items-center"),
        dbc.CardBody([
            # Strategy selector
            dbc.Row([
                dbc.Col([
                    html.Div("Strategy", className="text-muted small"),
                    dbc.Select(
                        id="strategy-selector",
                        options=[
                            {"label": "Proportional", "value": "proportional"},
                            {"label": "Conservative", "value": "conservative"},
                            {"label": "Smoothing", "value": "smoothing"},
                            {"label": "Battery Guard", "value": "battery_guard"},
                            {"label": "Predictive", "value": "predictive"},
                        ],
                        value="proportional",
                        size="sm",
                        className="bg-dark text-light border-secondary",
                    ),
                ], xs=8),
                dbc.Col([
                    html.Div("State", className="text-muted small"),
                    html.Div("--", id="strategy-state", className="fw-bold"),
                ], xs=4),
            ], className="g-2 mb-1"),
            # Strategy description & decision reasoning
            html.Div("--", id="strategy-description",
                      className="small text-muted fst-italic mb-1"),
            html.Div([
                html.I(className="fas fa-brain me-1 text-info", style={"fontSize": "0.7rem"}),
                html.Span("--", id="strategy-decision-notes", className="small text-info"),
            ], className="mb-1"),
            html.Hr(className="my-2"),
            dbc.Row([
                dbc.Col([
                    html.Div("Adjustments", className="text-muted small"),
                    html.Div("--", id="strategy-adjustments", className="fw-bold"),
                ], xs=4, md=3),
                dbc.Col([
                    html.Div("Spikes", className="text-muted small"),
                    html.Div("--", id="strategy-spikes", className="fw-bold"),
                ], xs=4, md=3),
                dbc.Col([
                    html.Div("Ignored", className="text-muted small"),
                    html.Div("--", id="strategy-ignored", className="fw-bold"),
                ], xs=4, md=3),
            ], className="g-2 mb-2"),
            html.Hr(className="my-2"),
            dbc.Row([
                dbc.Col([
                    html.Span("Avg30s: ", className="text-muted small"),
                    html.Span("--", id="strategy-avg30", className="fw-bold small"),
                    html.Span("W", className="text-muted small"),
                ], xs=4),
                dbc.Col([
                    html.Span("Avg60s: ", className="text-muted small"),
                    html.Span("--", id="strategy-avg60", className="fw-bold small"),
                    html.Span("W", className="text-muted small"),
                ], xs=4),
                dbc.Col([
                    html.Span("Base: ", className="text-muted small"),
                    html.Span("--", id="strategy-baseline", className="fw-bold small"),
                    html.Span("W", className="text-muted small"),
                ], xs=4),
            ]),
            html.Div([
                html.Span("Last: ", className="text-muted small"),
                html.Span("--", id="strategy-last-action", className="small"),
            ], className="mt-1"),
            html.Div([
                html.Span("Plugs: ", className="text-muted small"),
                html.Span("--", id="strategy-current-spike", className="small"),
            ]),
            # Energy tracking display
            html.Hr(className="my-2"),
            dbc.Row([
                dbc.Col([
                    html.Span("Import: ", className="text-muted small"),
                    html.Span("--", id="energy-import-today", className="fw-bold small text-danger"),
                    html.Span(" kWh", className="text-muted small"),
                ], xs=4),
                dbc.Col([
                    html.Span("Export: ", className="text-muted small"),
                    html.Span("--", id="energy-export-today", className="fw-bold small text-success"),
                    html.Span(" kWh", className="text-muted small"),
                ], xs=4),
                dbc.Col([
                    html.Span("Home: ", className="text-muted small"),
                    html.Span("--", id="energy-consumption-today", className="fw-bold small text-info"),
                    html.Span(" kWh", className="text-muted small"),
                ], xs=4),
            ]),
        ], className="p-2"),
    ], className="mb-3")


def _daily_summary_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-chart-bar me-2"),
            "Today",
        ], className="py-2"),
        dbc.CardBody(
            dbc.Row([
                dbc.Col([
                    html.Div("Solar", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-solar", className="fw-bold text-warning"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, md=2),
                dbc.Col([
                    html.Div("Charged", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-charge", className="fw-bold text-success"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, md=2),
                dbc.Col([
                    html.Div("Discharged", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-discharge", className="fw-bold text-info"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, md=2),
                dbc.Col([
                    html.Div("Home", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-usage", className="fw-bold text-light"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, md=2),
                dbc.Col([
                    html.Div("Import", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-grid-import", className="fw-bold text-danger"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, md=2),
                dbc.Col([
                    html.Div("Export", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="daily-grid-export", className="fw-bold text-success"),
                        html.Span(" kWh", className="text-muted small"),
                    ]),
                ], xs=4, md=2),
            ], className="g-2"),
            className="p-2",
        ),
    ], className="mb-3")


def _live_meter_chart_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-wave-square me-2"),
            "Live Grid",
            dbc.ButtonGroup([
                dbc.Button("5m", id="live-range-5m", color="info", size="sm",
                           outline=False, className="px-2 py-1"),
                dbc.Button("15m", id="live-range-15m", color="info", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("1h", id="live-range-1h", color="info", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("3h", id="live-range-3h", color="info", size="sm",
                           outline=True, className="px-2 py-1"),
            ], size="sm", className="ms-auto"),
        ], className="py-2 d-flex align-items-center"),
        dbc.CardBody([
            dcc.Store(id="live-range-store", data=300),
            dcc.Graph(id="live-meter-chart",
                      config={"displayModeBar": "hover", "scrollZoom": False,
                              "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
                              "displaylogo": False},
                      style={"height": "220px"}),
        ], className="p-1"),
    ], className="mb-3")


def _balance_chart_card() -> dbc.Card:
    """Load vs Grid balance chart — shows when load offsets grid import."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-scale-balanced me-2"),
            "Load ↔ Grid Balance",
            dbc.ButtonGroup([
                dbc.Button("6h", id="balance-range-6h", color="success", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("24h", id="balance-range-24h", color="success", size="sm",
                           outline=False, className="px-2 py-1"),
                dbc.Button("3d", id="balance-range-3d", color="success", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("7d", id="balance-range-7d", color="success", size="sm",
                           outline=True, className="px-2 py-1"),
            ], size="sm", className="ms-auto"),
        ], className="py-2 d-flex align-items-center"),
        dbc.CardBody([
            dcc.Store(id="balance-range-store", data=86400),
            # Summary stats row
            dbc.Row([
                dbc.Col([
                    html.Span("Self-sufficient ", className="text-muted small"),
                    html.Span("--", id="balance-self-pct",
                              className="fw-bold text-success small"),
                ], xs=4, className="text-center"),
                dbc.Col([
                    html.Span("Import ", className="text-muted small"),
                    html.Span("--", id="balance-import-dur",
                              className="fw-bold text-danger small"),
                ], xs=4, className="text-center"),
                dbc.Col([
                    html.Span("Export ", className="text-muted small"),
                    html.Span("--", id="balance-export-dur",
                              className="fw-bold text-success small"),
                ], xs=4, className="text-center"),
            ], className="mb-2 mt-1"),
            dcc.Graph(id="balance-chart",
                      config={"displayModeBar": "hover", "scrollZoom": False,
                              "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
                              "displaylogo": False},
                      style={"height": "300px"}),
        ], className="p-1"),
    ], className="mb-3")


def _daily_energy_chart_card() -> dbc.Card:
    """Daily energy flow – diverging stacked bars + self-sufficiency line."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-bolt me-2"),
            "Energy Flow (30 days)",
        ], className="py-2"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div("Self-use", className="text-muted small"),
                    html.Span("--", id="daily-energy-selfuse",
                              className="fw-bold text-success small"),
                ], xs=3, className="text-center"),
                dbc.Col([
                    html.Div("Self-sufficiency", className="text-muted small"),
                    html.Span("--", id="daily-energy-ss-pct",
                              className="fw-bold text-warning small"),
                ], xs=3, className="text-center"),
                dbc.Col([
                    html.Div("Grid Import", className="text-muted small"),
                    html.Span("--", id="daily-energy-import",
                              className="fw-bold text-danger small"),
                ], xs=3, className="text-center"),
                dbc.Col([
                    html.Div("Grid Export", className="text-muted small"),
                    html.Span("--", id="daily-energy-export",
                              className="fw-bold text-info small"),
                ], xs=3, className="text-center"),
            ], className="mb-1 g-1"),
            dcc.Graph(id="daily-energy-chart",
                      config={"displayModeBar": "hover", "scrollZoom": False,
                              "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
                              "displaylogo": False},
                      style={"height": "280px"}),
        ], className="p-1"),
    ], className="mb-3")


def _smart_plugs_card() -> dbc.Card:
    """Smart plug status - collapsible, lower priority."""
    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.I(className="fas fa-plug me-2"),
                "Smart Plugs",
                dbc.Badge("", id="plugs-count-badge", color="info",
                          className="ms-2"),
                html.I(className="fas fa-chevron-down ms-auto", id="plugs-chevron"),
            ], className="d-flex align-items-center",
               role="button", id="plugs-toggle"),
            className="py-2",
        ),
        dbc.Collapse(
            dbc.CardBody([
                html.Div(id="smart-plugs-container"),
            ], className="p-2"),
            id="plugs-collapse",
            is_open=False,
        ),
    ], className="mb-3")


def _iometer_status_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-wifi me-2"),
            "IOMeter",
        ], className="py-2"),
        dbc.CardBody(
            dbc.Row([
                dbc.Col([
                    html.I(className="fas fa-circle me-1", id="iometer-conn-icon"),
                    html.Span("--", id="iometer-conn-status", className="small"),
                ], xs=3),
                dbc.Col([
                    html.Span("Signal: ", className="text-muted small"),
                    html.Span("--", id="iometer-signal", className="small"),
                ], xs=3),
                dbc.Col([
                    html.Span("Batt: ", className="text-muted small"),
                    html.Span("--", id="iometer-battery", className="small"),
                ], xs=3),
                dbc.Col([
                    html.Span("Meter: ", className="text-muted small"),
                    html.Span("--", id="iometer-meter-no", className="small"),
                ], xs=3),
            ]),
            className="p-2",
        ),
    ], className="mb-3")


# ===================================================================
# ADMIN PAGE — Cards
# ===================================================================

def _strategy_config_card() -> dbc.Card:
    config_items = [
        ("polling_interval_s", "Polling Interval", "s", 5,
         "How often the meter is read and the control loop runs"),
        ("cooldown_period_s", "Cooldown", "s", 30,
         "Minimum wait time between two consecutive load adjustments"),
        ("min_change_threshold_w", "Min Change", "W", 20,
         "Hysteresis – ignore grid deviations smaller than this value"),
        ("emergency_threshold_w", "Emergency", "W", 500,
         "Override cooldown if grid deviation exceeds this threshold"),
        ("grid_target_w", "Grid Target", "W", 0,
         "Target meter reading; 0 = zero grid, negative = slight export"),
        ("max_load_w", "Max Load", "W", 800,
         "Maximum inverter output (German 800 W micro-inverter limit)"),
        ("min_load_w", "Min Load", "W", 0,
         "Minimum inverter output; set > 0 to keep a base load running"),
        ("load_step_w", "Load Step", "W", 10,
         "Smallest increment for load adjustments (Anker SB2 resolution)"),
        ("electricity_price_eur_kwh", "Elec. Price", "€/kWh", 0.28,
         "Grid electricity price, used for cost/savings calculations"),
        ("feed_in_tariff_eur_kwh", "Feed-in Tariff", "€/kWh", 0.082,
         "Feed-in tariff (Einspeisevergütung) for exported energy"),
    ]

    rows = []
    for key, label, unit, default, desc in config_items:
        row_id = f"cfg-tip-{key}"
        rows.append(
            dbc.Row([
                dbc.Col([
                    html.Label([
                        f"{label} ({unit}) ",
                        html.I(className="fas fa-info-circle text-muted",
                               id=row_id, style={"cursor": "pointer", "fontSize": "0.75rem"}),
                    ], className="small mb-0"),
                    dbc.Tooltip(desc, target=row_id, placement="right"),
                ], xs=5),
                dbc.Col(
                    dbc.Input(
                        id={"type": "config-input", "key": key},
                        type="number",
                        value=default,
                        size="sm",
                        className="bg-dark text-light border-secondary",
                    ),
                    xs=5,
                ),
                dbc.Col(
                    dbc.Button(
                        html.I(className="fas fa-save"),
                        id={"type": "config-save-btn", "key": key},
                        color="outline-success",
                        size="sm",
                    ),
                    xs=2,
                ),
            ], className="mb-2 align-items-center"),
        )

    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-cog me-2"),
            "Strategy Config",
        ], className="py-2"),
        dbc.CardBody([
            html.P("Changes take effect on the next control cycle.",
                    className="text-muted small mb-2"),
            *rows,
            html.Div(id="config-status-msg", className="mt-2"),
        ], className="p-2"),
    ], className="mb-3")


def _recent_events_card() -> dbc.Card:
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-list me-2"),
            "Recent Load Changes",
        ], className="py-2"),
        dbc.CardBody([
            html.Div(id="recent-events-table"),
        ], className="p-2"),
    ], className="mb-3")


# ===================================================================
# NAVBAR (shared — mobile-friendly)
# ===================================================================

def _navbar() -> dbc.Navbar:
    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand([
                html.I(className="fas fa-solar-panel me-2"),
                html.Span("Solar Control", className="d-none d-sm-inline"),
                html.Span("Solar", className="d-inline d-sm-none"),
            ], className="fs-5"),
            dbc.Nav([
                dbc.NavItem(dbc.NavLink("Dashboard", href="/dashboard/", active="exact",
                                         className="py-2 px-3")),
                dbc.NavItem(dbc.NavLink("Analytics", href="/dashboard/analytics", active="exact",
                                         className="py-2 px-3")),
                dbc.NavItem(dbc.NavLink("Admin", href="/dashboard/admin", active="exact",
                                         className="py-2 px-3")),
                dbc.NavItem(html.Span(id="header-time", className="text-muted nav-link py-2 px-2 small")),
            ], navbar=True, className="ms-auto"),
        ], fluid=True),
        color="dark",
        dark=True,
        className="mb-2 py-1",
        style={"minHeight": "auto"},
    )


# ===================================================================
# PAGE: Operations Dashboard
# ===================================================================

def _schedule_card() -> dbc.Card:
    """Read-only display of SB2 time-based schedule (from Anker cloud)."""
    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.I(className="fas fa-calendar-alt me-2"),
                "Device Schedule",
                html.Span(" (read-only)", className="text-muted small ms-1"),
                html.I(className="fas fa-chevron-down ms-auto", id="schedule-chevron"),
            ], className="d-flex align-items-center",
               role="button", id="schedule-toggle"),
            className="py-2",
        ),
        dbc.Collapse(
            dbc.CardBody([
                html.Div(id="schedule-content",
                          children=html.Span("Loading...", className="text-muted small")),
            ], className="p-2"),
            id="schedule-collapse",
            is_open=False,
        ),
    ], className="mb-3")


def _operations_page() -> html.Div:
    return html.Div([
        _realtime_metrics_card(),
        _solar_detail_card(),
        _power_flow_card(),
        dbc.Row([
            dbc.Col(_manual_control_card(), xs=12, lg=6),
            dbc.Col(_auto_status_card(), xs=12, lg=6),
        ]),
        _daily_summary_card(),
        _live_meter_chart_card(),
        _balance_chart_card(),
        _daily_energy_chart_card(),
        _smart_plugs_card(),
        _iometer_status_card(),
        _schedule_card(),
    ])


# ===================================================================
# PAGE: Admin Panel
# ===================================================================

def _iometer_config_card() -> dbc.Card:
    """Admin card for configuring IOMeter data source."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-network-wired me-2"),
            "IOMeter Source",
        ], className="py-2"),
        dbc.CardBody([
            html.P("Select meter data source", className="text-muted small mb-2"),

            # Source selector
            dbc.Row([
                dbc.Col(html.Label("Source", className="small"), xs=4),
                dbc.Col(
                    dbc.RadioItems(
                        id="iometer-source-radio",
                        options=[
                            {"label": " LAN Direct", "value": "local"},
                            {"label": " ESP32 Push (API)", "value": "esp32"},
                        ],
                        value="local",
                        inline=True,
                        className="small",
                    ),
                    xs=8,
                ),
            ], className="mb-3 align-items-center"),

            # Host input (only relevant for local mode)
            html.Div(
                id="iometer-host-group",
                children=[
                    dbc.Row([
                        dbc.Col(html.Label("IOMeter Host", className="small"), xs=4),
                        dbc.Col(
                            dbc.Input(
                                id="iometer-host-input",
                                type="text",
                                placeholder="192.168.178.96",
                                value="192.168.178.96",
                                size="sm",
                                className="bg-dark text-light border-secondary",
                            ),
                            xs=8,
                        ),
                    ], className="mb-2 align-items-center"),
                ],
            ),

            # ESP32 info (only visible in ESP32 mode)
            html.Div(
                id="iometer-esp32-info",
                children=[
                    dbc.Alert([
                        html.I(className="fas fa-info-circle me-2"),
                        "ESP32 pushes data via ",
                        html.Code("POST /api/esp32/meter"),
                        " endpoint.",
                        html.Br(),
                        html.Small("Set ESP32_API_KEY in .env",
                                   className="text-muted"),
                    ], color="info", className="small mb-0 py-2"),
                ],
                style={"display": "none"},
            ),

            # Connection status
            html.Div(id="iometer-config-status",
                      className="small text-muted mt-2"),

            # Save button
            dbc.Button(
                [html.I(className="fas fa-save me-1"), "Save"],
                id="iometer-config-save-btn",
                color="success", size="sm",
                className="mt-2 w-100",
            ),
            html.Div(id="iometer-config-save-msg", className="mt-2"),
        ], className="p-2"),
    ], className="mb-3")


def _admin_page() -> html.Div:
    return html.Div([
        html.H5([
            html.I(className="fas fa-tools me-2"),
            "Administration",
        ], className="mb-2"),

        # IOMeter data source config at top
        dbc.Row([
            dbc.Col(_iometer_config_card(), xs=12, lg=6),
        ], className="mb-3"),

        dbc.Row([
            dbc.Col(_strategy_config_card(), xs=12, lg=6),
        ]),

        _recent_events_card(),
    ])


# ===================================================================
# PAGE: Analytics (historical comparisons)
# ===================================================================

def _hourly_pattern_card() -> dbc.Card:
    """Shows average consumption pattern by hour of day."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-clock me-2"),
            "Hourly Pattern (7-day avg)",
        ], className="py-2"),
        dbc.CardBody([
            dcc.Graph(id="hourly-pattern-chart",
                      config={"displayModeBar": "hover", "scrollZoom": False,
                              "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
                              "displaylogo": False},
                      style={"height": "250px"}),
        ], className="p-1"),
    ], className="mb-3")


def _daily_comparison_card() -> dbc.Card:
    """Daily energy area chart – layered energy flow with self-sufficiency."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-layer-group me-2"),
            "Daily Energy Flow",
            dbc.ButtonGroup([
                dbc.Button("7d", id="daily-comp-7d", color="success", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("14d", id="daily-comp-14d", color="success", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("30d", id="daily-comp-30d", color="success", size="sm",
                           outline=False, className="px-2 py-1"),
                dbc.Button("90d", id="daily-comp-90d", color="success", size="sm",
                           outline=True, className="px-2 py-1"),
            ], size="sm", className="ms-auto"),
        ], className="py-2 d-flex align-items-center"),
        dbc.CardBody([
            dcc.Store(id="daily-comp-range-store", data=30),
            dbc.Row([
                dbc.Col([
                    html.Div("Avg Solar/d", className="text-muted small"),
                    html.Span("--", id="daily-comp-avg-solar",
                              className="fw-bold text-warning small"),
                ], xs=3, className="text-center"),
                dbc.Col([
                    html.Div("Avg SS%", className="text-muted small"),
                    html.Span("--", id="daily-comp-avg-ss",
                              className="fw-bold text-success small"),
                ], xs=3, className="text-center"),
                dbc.Col([
                    html.Div("Total Import", className="text-muted small"),
                    html.Span("--", id="daily-comp-import",
                              className="fw-bold text-danger small"),
                ], xs=3, className="text-center"),
                dbc.Col([
                    html.Div("Net Cost", className="text-muted small"),
                    html.Span("--", id="daily-comp-net-cost",
                              className="fw-bold text-info small"),
                ], xs=3, className="text-center"),
            ], className="mb-1 g-1"),
            dcc.Graph(id="daily-comparison-chart",
                      config={"displayModeBar": "hover", "scrollZoom": False,
                              "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
                              "displaylogo": False},
                      style={"height": "340px"}),
        ], className="p-1"),
    ], className="mb-3")


def _weekly_summary_card() -> dbc.Card:
    """Weekly horizontal diverging bars with self-sufficiency annotations."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-calendar-week me-2"),
            "Weekly Balance",
        ], className="py-2"),
        dbc.CardBody([
            dcc.Graph(id="weekly-summary-chart",
                      config={"displayModeBar": "hover", "scrollZoom": False,
                              "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
                              "displaylogo": False},
                      style={"height": "360px"}),
        ], className="p-1"),
    ], className="mb-3")


def _monthly_summary_card() -> dbc.Card:
    """Monthly summary with indicator gauges and stacked area trend."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-calendar me-2"),
            "Monthly Overview",
        ], className="py-2"),
        dbc.CardBody([
            dcc.Graph(id="monthly-summary-chart",
                      config={"displayModeBar": "hover", "scrollZoom": False,
                              "modeBarButtonsToRemove": ["lasso2d", "select2d", "toImage"],
                              "displaylogo": False},
                      style={"height": "420px"}),
        ], className="p-1"),
    ], className="mb-3")


def _weather_forecast_card() -> dbc.Card:
    """7-day weather forecast with PV generation estimate."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-cloud-sun me-2"),
            "7-Day Solar Forecast",
        ], className="py-2"),
        dbc.CardBody([
            # Summary row (today + tomorrow highlights)
            dbc.Row([
                dbc.Col([
                    html.Div("Today Sun", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="weather-today-hours", className="fw-bold text-warning"),
                        html.Span(" hrs", className="text-muted small"),
                    ]),
                ], xs=3),
                dbc.Col([
                    html.Div("Tomorrow Sun", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="weather-tomorrow-hours", className="fw-bold text-warning"),
                        html.Span(" hrs", className="text-muted small"),
                    ]),
                ], xs=3),
                dbc.Col([
                    html.Div("Cloud", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="weather-cloud-cover", className="fw-bold text-info"),
                        html.Span("%", className="text-muted small"),
                    ]),
                ], xs=3),
                dbc.Col([
                    html.Div("Outlook", className="text-muted small"),
                    html.Div([
                        html.Span("--", id="weather-outlook", className="fw-bold"),
                    ]),
                ], xs=3),
            ], className="g-2 mb-2"),
            html.Hr(className="my-2"),
            # 7-day forecast table
            html.Div(id="weather-7day-table"),
            # Generation bar chart
            dcc.Graph(id="weather-generation-chart",
                      config={"displayModeBar": False, "scrollZoom": False},
                      style={"height": "180px"}),
        ], className="p-2"),
    ], className="mb-3")


def _daily_detail_table_card() -> dbc.Card:
    """Detailed daily energy statistics table with costs."""
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="fas fa-table me-2"),
            "Daily Detail",
            dbc.ButtonGroup([
                dbc.Button("7d", id="detail-range-7d", color="info", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("14d", id="detail-range-14d", color="info", size="sm",
                           outline=True, className="px-2 py-1"),
                dbc.Button("30d", id="detail-range-30d", color="info", size="sm",
                           outline=False, className="px-2 py-1"),
                dbc.Button("90d", id="detail-range-90d", color="info", size="sm",
                           outline=True, className="px-2 py-1"),
            ], size="sm", className="ms-auto"),
        ], className="py-2 d-flex align-items-center"),
        dbc.CardBody([
            dcc.Store(id="detail-range-store", data=30),
            # Summary totals row
            dbc.Row([
                dbc.Col([
                    html.Div("Total Solar", className="text-muted small"),
                    html.Span("--", id="detail-total-solar", className="fw-bold text-warning"),
                ], xs=4, md=2, className="text-center mb-1"),
                dbc.Col([
                    html.Div("Self-use", className="text-muted small"),
                    html.Span("--", id="detail-total-selfuse", className="fw-bold text-success"),
                ], xs=4, md=2, className="text-center mb-1"),
                dbc.Col([
                    html.Div("Import", className="text-muted small"),
                    html.Span("--", id="detail-total-import", className="fw-bold text-danger"),
                ], xs=4, md=2, className="text-center mb-1"),
                dbc.Col([
                    html.Div("Export", className="text-muted small"),
                    html.Span("--", id="detail-total-export", className="fw-bold text-info"),
                ], xs=4, md=2, className="text-center mb-1"),
                dbc.Col([
                    html.Div("Grid Cost", className="text-muted small"),
                    html.Span("--", id="detail-total-cost", className="fw-bold text-danger"),
                ], xs=4, md=2, className="text-center mb-1"),
                dbc.Col([
                    html.Div("Saved", className="text-muted small"),
                    html.Span("--", id="detail-total-saved", className="fw-bold text-success"),
                ], xs=4, md=2, className="text-center mb-1"),
            ], className="mb-2 g-1"),
            html.Div(id="daily-detail-table", style={"overflowX": "auto"}),
        ], className="p-2"),
    ], className="mb-3")


def _analytics_page() -> html.Div:
    return html.Div([
        html.H5([
            html.I(className="fas fa-chart-area me-2"),
            "Analytics",
        ], className="mb-2"),

        _weather_forecast_card(),
        _hourly_pattern_card(),
        _daily_detail_table_card(),
        _daily_comparison_card(),
        _weekly_summary_card(),
        _monthly_summary_card(),

        # Refresh interval for analytics
        dcc.Interval(id="interval-analytics", interval=60_000, n_intervals=0),
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
        dbc.Container(id="page-content", fluid=True, className="px-2 px-md-3"),

        # Footer
        dbc.Container([
            html.Footer([
                html.Hr(className="my-1"),
                html.P([
                    "Solar Control v1.2 | ",
                    html.Span(id="footer-status", className="text-muted"),
                ], className="text-center text-muted small mb-1"),
            ]),
        ], fluid=True),
    ])


def get_operations_page() -> html.Div:
    return _operations_page()


def get_admin_page() -> html.Div:
    return _admin_page()


def get_analytics_page() -> html.Div:
    return _analytics_page()
