"""Dash callbacks — wires dashboard UI to backend services.

All callbacks communicate with the FastAPI backend via HTTP requests
to /api/* endpoints (same server, different mount path).

Two-page routing:
  /dashboard/      — Operations dashboard
  /dashboard/admin — Admin panel
"""

import logging
import os
import zoneinfo
from datetime import datetime, timezone

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from dash import Input, Output, State, callback_context, html, ALL, MATCH, no_update

from app.dashboard.layouts import get_operations_page, get_admin_page, get_analytics_page
from app.services.strategies import list_strategies

logger = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:8000/api"

# Local timezone for chart display (reads TZ env var, falls back to Europe/Berlin)
_LOCAL_TZ = zoneinfo.ZoneInfo(os.environ.get("TZ", "Europe/Berlin"))


def _to_local_ts(utc_ts: str) -> str:
    """Convert a UTC ISO timestamp string to a naive local-time ISO string for Plotly."""
    try:
        dt = datetime.fromisoformat(utc_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_LOCAL_TZ).strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        return utc_ts


# Strategy descriptions cache
_STRATEGY_DESCS: dict[str, str] = {}


def _get_strategy_description(name: str) -> str:
    """Get a strategy's description by name."""
    if not _STRATEGY_DESCS:
        for s in list_strategies():
            _STRATEGY_DESCS[s["name"]] = s["description"]
    return _STRATEGY_DESCS.get(name, "")


def _api_get(path: str) -> dict | list | None:
    try:
        resp = requests.get(f"{API_BASE}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("API GET %s failed: %s", path, exc)
        return None


def _api_post(path: str, json_data: dict | None = None) -> dict | None:
    try:
        resp = requests.post(f"{API_BASE}{path}", json=json_data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("API POST %s failed: %s", path, exc)
        return None


def _api_delete(path: str) -> dict | None:
    try:
        resp = requests.delete(f"{API_BASE}{path}", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("API DELETE %s failed: %s", path, exc)
        return None


# Plotly dark layout defaults (compact for mobile)
_PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin={"l": 35, "r": 10, "t": 5, "b": 30},
    legend={"orientation": "h", "y": 1.12, "font": {"size": 10}},
    xaxis={"gridcolor": "rgba(255,255,255,0.05)"},
    yaxis={"gridcolor": "rgba(255,255,255,0.05)"},
    hovermode="x unified",
    hoverlabel={"bgcolor": "rgba(30,30,30,0.9)", "font_size": 11},
    spikedistance=-1,
)

# Spike crosshair styling — applied via update_xaxes/update_yaxes after layout
_SPIKE_STYLE = dict(
    showspikes=True,
    spikemode="across",
    spikethickness=0.5,
    spikecolor="rgba(180,180,180,0.4)",
    spikedash="dash",
    spikesnap="cursor",
)


def _apply_crosshair(fig: go.Figure) -> go.Figure:
    """Apply dashed crosshair spike lines to a figure."""
    fig.update_xaxes(**_SPIKE_STYLE)
    fig.update_yaxes(**_SPIKE_STYLE)
    return fig


# ---------------------------------------------------------------------------
# Register all callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:

    # -------------------------------------------------------------------
    # 0. Page routing
    # -------------------------------------------------------------------

    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
    )
    def route_page(pathname):
        if pathname == "/dashboard/admin":
            return get_admin_page()
        if pathname == "/dashboard/analytics":
            return get_analytics_page()
        return get_operations_page()

    # -------------------------------------------------------------------
    # 1. Fast refresh: metrics, flow, solar channels, auto status (3s)
    # -------------------------------------------------------------------

    @app.callback(
        [
            # Realtime metrics
            Output("solar-value", "children"),
            Output("battery-value", "children"),
            Output("meter-value", "children"),
            Output("load-value", "children"),
            # Solar channels
            Output("pv1-value", "children"),
            Output("pv2-value", "children"),
            Output("mi-value", "children"),
            Output("pv1-kwh", "children"),
            Output("pv2-kwh", "children"),
            Output("mi-kwh", "children"),
            # Power flow
            Output("flow-solar", "children"),
            Output("flow-battery-soc", "children"),
            Output("flow-battery-power", "children"),
            Output("flow-home", "children"),
            Output("flow-grid", "children"),
            Output("flow-grid-icon", "className"),
            # Auto status
            Output("strategy-state", "children"),
            Output("strategy-adjustments", "children"),
            Output("strategy-spikes", "children"),
            Output("strategy-ignored", "children"),
            Output("strategy-avg30", "children"),
            Output("strategy-avg60", "children"),
            Output("strategy-baseline", "children"),
            Output("strategy-last-action", "children"),
            Output("strategy-current-spike", "children"),
            # Strategy explanation
            Output("strategy-description", "children"),
            Output("strategy-decision-notes", "children"),
            # Energy tracking
            Output("energy-import-today", "children"),
            Output("energy-export-today", "children"),
            Output("energy-consumption-today", "children"),
            # Strategy selector sync
            Output("strategy-selector", "value"),
            # Daily summary
            Output("daily-solar", "children"),
            Output("daily-charge", "children"),
            Output("daily-discharge", "children"),
            Output("daily-usage", "children"),
            Output("daily-grid-import", "children"),
            Output("daily-grid-export", "children"),
            # Smart plugs
            Output("smart-plugs-container", "children"),
            Output("plugs-count-badge", "children"),
            # Header time
            Output("header-time", "children"),
            # Footer status
            Output("footer-status", "children"),
            # Load slider sync
            Output("load-slider", "value"),
            # Auto mode switch sync
            Output("auto-mode-switch", "value"),
        ],
        Input("interval-fast", "n_intervals"),
        prevent_initial_call=False,
    )
    def update_realtime(_n):
        data = _api_get("/data")
        if data is None:
            raise dash.exceptions.PreventUpdate

        anker = data.get("anker", {})
        meter = data.get("meter", {})
        strategy = data.get("strategy", {})

        solar_w = anker.get("solar_power_w", 0)
        battery_soc = anker.get("battery_soc", 0)
        meter_w = meter.get("power_w")
        load_w = anker.get("current_load_w", 0)
        battery_pw = anker.get("battery_power_w", 0)
        home_w = anker.get("home_demand_w", 0)

        # Per-channel solar
        pv1 = anker.get("pv1_power_w", 0)
        pv2 = anker.get("pv2_power_w", 0)
        mi = anker.get("micro_inverter_power_w", 0)
        pv1_kwh = anker.get("today_pv1_kwh", 0)
        pv2_kwh = anker.get("today_pv2_kwh", 0)
        mi_kwh = anker.get("today_mi_kwh", 0)

        # Grid display
        meter_display = f"{meter_w:.0f}" if meter_w is not None else "--"
        if meter_w is not None:
            if meter_w > 10:
                grid_icon_class = "fas fa-tower-broadcast fa-lg text-danger"
            elif meter_w < -10:
                grid_icon_class = "fas fa-tower-broadcast fa-lg text-success"
            else:
                grid_icon_class = "fas fa-tower-broadcast fa-lg text-muted"
        else:
            grid_icon_class = "fas fa-tower-broadcast fa-lg text-muted"

        # Strategy
        plug_total = strategy.get("plug_total_w", 0)
        plug_text = f"Plugs: {plug_total:.0f}W"

        avg30 = strategy.get("meter_avg_30s")
        avg60 = strategy.get("meter_avg_60s")

        # Smart plugs
        plugs = anker.get("smart_plugs", [])
        plug_rows = []
        for p in plugs:
            online = p.get("online", False)
            status_icon = "fas fa-circle text-success" if online else "fas fa-circle text-danger"
            pw = p.get("power_w", 0)
            plug_rows.append(
                dbc.Row([
                    dbc.Col([
                        html.I(className=f"{status_icon} me-1", style={"fontSize": "0.5rem"}),
                        html.Span(p.get("alias", "?"), className="small"),
                    ], xs=5),
                    dbc.Col([
                        html.Span(f"{pw:.0f}W", className="small fw-bold"
                                  + (" text-warning" if pw > 5 else " text-muted")),
                    ], xs=3),
                    dbc.Col([
                        html.Span(p.get("tag", ""), className="small text-muted"),
                    ], xs=4),
                ], className="mb-1")
            )
        plugs_content = plug_rows if plug_rows else [html.Span("No plugs", className="text-muted small")]

        now_str = datetime.now().strftime("%H:%M:%S")
        connected = "Connected" if meter.get("connected") else "Disconnected"
        init = "OK" if anker.get("initialized") else "N/A"
        footer = f"Anker {init} | Meter {connected} | {now_str}"

        return [
            # Metrics
            f"{solar_w:.0f}",
            f"{battery_soc:.0f}",
            meter_display,
            f"{load_w}",
            # Solar channels
            f"{pv1:.0f}",
            f"{pv2:.0f}",
            f"{mi:.0f}",
            f"{pv1_kwh:.2f}",
            f"{pv2_kwh:.2f}",
            f"{mi_kwh:.2f}",
            # Power flow
            f"{solar_w:.0f}W",
            f"{battery_soc:.0f}",
            f"{battery_pw:.0f}",
            f"{home_w:.0f}W",
            f"{meter_display}W",
            grid_icon_class,
            # Strategy
            strategy.get("state", "--"),
            str(strategy.get("total_adjustments", 0)),
            str(strategy.get("total_spikes_detected", 0)),
            str(strategy.get("total_spikes_ignored", 0)),
            f"{avg30:.0f}" if avg30 is not None else "--",
            f"{avg60:.0f}" if avg60 is not None else "--",
            str(strategy.get("baseline_load_w", 0)),
            strategy.get("last_action", "none"),
            plug_text,
            # Strategy explanation
            _get_strategy_description(strategy.get("active_strategy", "proportional")),
            strategy.get("last_decision_notes", "") or "Waiting for data…",
            # Energy tracking
            f"{strategy.get('energy', {}).get('grid_import_kwh', 0):.3f}",
            f"{strategy.get('energy', {}).get('grid_export_kwh', 0):.3f}",
            f"{strategy.get('energy', {}).get('home_consumption_kwh', 0):.3f}",
            # Strategy selector
            strategy.get("active_strategy", "proportional"),
            # Daily
            f"{anker.get('today_solar_kwh', 0):.2f}",
            f"{anker.get('today_charge_kwh', 0):.2f}",
            f"{anker.get('today_discharge_kwh', 0):.2f}",
            f"{anker.get('today_usage_kwh', 0):.2f}",
            f"{anker.get('today_grid_import_kwh', 0):.2f}",
            f"{anker.get('today_grid_export_kwh', 0):.2f}",
            # Smart plugs
            plugs_content,
            f"{len(plugs)}",
            # Header / footer
            now_str,
            footer,
            # Load slider
            load_w,
            # Auto mode
            strategy.get("auto_enabled", True),
        ]

    # -------------------------------------------------------------------
    # 2. Load slider display
    # -------------------------------------------------------------------

    @app.callback(
        Output("load-slider-display", "children"),
        Input("load-slider", "value"),
    )
    def update_slider_display(value):
        return str(value or 0)

    # -------------------------------------------------------------------
    # 3. Manual load control buttons
    # -------------------------------------------------------------------

    @app.callback(
        Output("load-status-msg", "children"),
        [
            Input("btn-set-load", "n_clicks"),
            Input("btn-max-load", "n_clicks"),
            Input("btn-min-load", "n_clicks"),
        ],
        State("load-slider", "value"),
        prevent_initial_call=True,
    )
    def handle_load_buttons(set_clicks, max_clicks, min_clicks, slider_val):
        ctx = callback_context
        if not ctx.triggered:
            return no_update

        btn_id = ctx.triggered[0]["prop_id"].split(".")[0]

        if btn_id == "btn-max-load":
            load_val = 800
        elif btn_id == "btn-min-load":
            load_val = 0
        else:
            load_val = slider_val or 0

        result = _api_post("/set-load", {"load": load_val})
        if result and result.get("success"):
            return dbc.Alert(f"Load → {load_val}W", color="success", duration=3000)
        else:
            error = result.get("detail", "Unknown error") if result else "API unreachable"
            return dbc.Alert(f"Failed: {error}", color="danger", duration=3000)

    # -------------------------------------------------------------------
    # 4. Auto mode toggle
    # -------------------------------------------------------------------

    @app.callback(
        Output("auto-mode-status", "children"),
        Input("auto-mode-switch", "value"),
        prevent_initial_call=True,
    )
    def toggle_auto_mode(enabled):
        result = _api_post(f"/auto-mode?enabled={'true' if enabled else 'false'}")
        if result and result.get("success"):
            status = "ON" if enabled else "OFF"
            color = "text-success" if enabled else "text-danger"
            return html.Span(status, className=f"{color} fw-bold")
        return html.Span("Error", className="text-warning")

    # -------------------------------------------------------------------
    # 5. Live meter chart (10s refresh — from in-memory buffer)
    # -------------------------------------------------------------------

    @app.callback(
        Output("live-range-store", "data"),
        [Input("live-range-5m", "n_clicks"),
         Input("live-range-15m", "n_clicks"),
         Input("live-range-1h", "n_clicks"),
         Input("live-range-3h", "n_clicks")],
        prevent_initial_call=True,
    )
    def set_live_range(n5, n15, n1h, n3h):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
        ranges = {
            "live-range-5m": 300,
            "live-range-15m": 900,
            "live-range-1h": 3600,
            "live-range-3h": 10800,
        }
        return ranges.get(btn_id, 300)

    @app.callback(
        [Output("live-range-5m", "outline"),
         Output("live-range-15m", "outline"),
         Output("live-range-1h", "outline"),
         Output("live-range-3h", "outline")],
        Input("live-range-store", "data"),
    )
    def update_live_btn_style(seconds):
        active = {300: 0, 900: 1, 3600: 2, 10800: 3}.get(seconds, 0)
        return [i != active for i in range(4)]

    @app.callback(
        Output("live-meter-chart", "figure"),
        [Input("interval-medium", "n_intervals"),
         Input("live-range-store", "data")],
    )
    def update_live_meter_chart(_n, seconds):
        seconds = seconds or 300
        data = _api_get(f"/meter-live?seconds={seconds}") or []

        fig = go.Figure()

        if data:
            fig.add_trace(go.Scatter(
                x=[_to_local_ts(r["timestamp"]) for r in data],
                y=[r["power_w"] for r in data],
                name="Grid (W)",
                line={"color": "#17a2b8", "width": 2},
                fill="tozeroy",
                fillcolor="rgba(23,162,184,0.15)",
                hovertemplate="%{x|%H:%M:%S}<br>Grid: %{y:.0f}W<extra></extra>",
            ))

        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
        fig.update_layout(**_PLOT_LAYOUT, height=220, yaxis_title="W", uirevision="live")
        _apply_crosshair(fig)
        return fig

    # -------------------------------------------------------------------
    # 6b. Load ↔ Grid Balance chart
    # -------------------------------------------------------------------

    @app.callback(
        Output("balance-range-store", "data"),
        [Input("balance-range-6h", "n_clicks"),
         Input("balance-range-24h", "n_clicks"),
         Input("balance-range-3d", "n_clicks"),
         Input("balance-range-7d", "n_clicks")],
        prevent_initial_call=True,
    )
    def set_balance_range(n6, n24, n3d, n7d):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
        ranges = {
            "balance-range-6h": 21600,
            "balance-range-24h": 86400,
            "balance-range-3d": 259200,
            "balance-range-7d": 604800,
        }
        return ranges.get(btn_id, 86400)

    @app.callback(
        [Output("balance-range-6h", "outline"),
         Output("balance-range-24h", "outline"),
         Output("balance-range-3d", "outline"),
         Output("balance-range-7d", "outline")],
        Input("balance-range-store", "data"),
    )
    def update_balance_btn_style(seconds):
        active = {21600: 0, 86400: 1, 259200: 2, 604800: 3}.get(seconds, 1)
        return [i != active for i in range(4)]

    @app.callback(
        [Output("balance-chart", "figure"),
         Output("balance-self-pct", "children"),
         Output("balance-import-dur", "children"),
         Output("balance-export-dur", "children")],
        [Input("interval-medium", "n_intervals"),
         Input("balance-range-store", "data")],
    )
    def update_balance_chart(_n, seconds):
        seconds = seconds or 86400
        hours = seconds // 3600
        load_data = _api_get(f"/load-history?hours={hours}") or []
        meter_data = _api_get(f"/meter-history?seconds={seconds}") or []

        fig = go.Figure()

        if not meter_data:
            fig.update_layout(**_PLOT_LAYOUT, height=300, uirevision="balance")
            _apply_crosshair(fig)
            return fig, "--", "--", "--"

        meter_sorted = sorted(meter_data, key=lambda x: x.get("timestamp", ""))
        load_sorted = sorted(load_data, key=lambda x: x.get("timestamp", ""))

        m_ts_raw = [r["timestamp"] for r in meter_sorted]
        m_ts = [_to_local_ts(ts) for ts in m_ts_raw]
        m_pw = [r["power_w"] for r in meter_sorted]

        # Build a step-interpolated load series aligned to meter timestamps
        # Load changes are sparse events; between them the load is constant
        load_at_meter = []
        li = 0
        current_load = 0
        for ts in m_ts:
            while li < len(load_sorted) and load_sorted[li]["timestamp"] <= ts:
                current_load = load_sorted[li].get("new_load_w", 0)
                li += 1
            load_at_meter.append(current_load)

        # --- Traces ---

        # 1. Grid meter line (the actual reading)
        fig.add_trace(go.Scatter(
            x=m_ts, y=m_pw,
            name="Grid (W)",
            line={"color": "#17a2b8", "width": 1.5},
            hovertemplate="%{x|%m-%d %H:%M}<br>Grid: %{y:.0f}W<extra></extra>",
        ))

        # 2. Load setting as step line
        fig.add_trace(go.Scatter(
            x=m_ts, y=load_at_meter,
            name="Load (W)",
            line={"color": "#ffc107", "width": 2, "shape": "hv"},
            hovertemplate="%{x|%m-%d %H:%M}<br>Load: %{y}W<extra></extra>",
        ))

        # 3. Colored fill: green when grid <= 0 (self-sufficient/exporting),
        #    red when grid > 0 (importing)
        import_y = []
        export_y = []
        for pw in m_pw:
            if pw > 0:
                import_y.append(pw)
                export_y.append(0)
            else:
                import_y.append(0)
                export_y.append(pw)

        fig.add_trace(go.Scatter(
            x=m_ts, y=import_y,
            fill="tozeroy",
            fillcolor="rgba(220,53,69,0.25)",
            line={"width": 0},
            name="Importing",
            showlegend=True,
            hoverinfo="skip",
        ))

        fig.add_trace(go.Scatter(
            x=m_ts, y=export_y,
            fill="tozeroy",
            fillcolor="rgba(40,167,69,0.25)",
            line={"width": 0},
            name="Exporting",
            showlegend=True,
            hoverinfo="skip",
        ))

        # Zero line
        fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.4)",
                      line_width=1.5)

        fig.update_layout(**_PLOT_LAYOUT, height=300, yaxis_title="W",
                          uirevision="balance")

        # --- Compute summary stats ---
        total_points = len(m_pw)
        import_points = sum(1 for pw in m_pw if pw > 10)    # >10W = importing
        export_points = sum(1 for pw in m_pw if pw < -10)   # <-10W = exporting
        self_sufficient = total_points - import_points  # grid ≤ 10W

        pct = f"{self_sufficient / total_points * 100:.0f}%" if total_points > 0 else "--"

        # Estimate durations from reading intervals
        if total_points >= 2:
            try:
                from datetime import datetime as _dt
                first = _dt.fromisoformat(m_ts_raw[0].replace("Z", "+00:00"))
                last = _dt.fromisoformat(m_ts_raw[-1].replace("Z", "+00:00"))
                span_s = (last - first).total_seconds()
                avg_interval = span_s / (total_points - 1) if total_points > 1 else 0
            except Exception:
                avg_interval = seconds / total_points

            import_s = import_points * avg_interval
            export_s = export_points * avg_interval

            def _fmt_dur(secs):
                if secs < 60:
                    return f"{secs:.0f}s"
                if secs < 3600:
                    return f"{secs / 60:.0f}m"
                h = int(secs // 3600)
                m = int((secs % 3600) // 60)
                return f"{h}h{m:02d}m"

            import_dur = _fmt_dur(import_s)
            export_dur = _fmt_dur(export_s)
        else:
            import_dur = "--"
            export_dur = "--"

        _apply_crosshair(fig)
        return fig, pct, import_dur, export_dur

    # -------------------------------------------------------------------
    # 7. Daily energy flow chart (slow refresh)
    # -------------------------------------------------------------------

    @app.callback(
        [Output("daily-energy-chart", "figure"),
         Output("daily-energy-selfuse", "children"),
         Output("daily-energy-ss-pct", "children"),
         Output("daily-energy-import", "children"),
         Output("daily-energy-export", "children")],
        Input("interval-slow", "n_intervals"),
    )
    def update_daily_energy_chart(_n):
        data = _api_get("/daily-energy?days=30") or []

        fig = go.Figure()
        if not data:
            fig.update_layout(**_PLOT_LAYOUT, height=280, uirevision="daily-energy")
            _apply_crosshair(fig)
            return fig, "--", "--", "--", "--"

        data_sorted = sorted(data, key=lambda x: x.get("date", ""))
        dates = [d["date"] for d in data_sorted]

        solar = [d.get("solar_production_wh", 0) / 1000 for d in data_sorted]
        home = [d.get("home_consumption_wh", 0) / 1000 for d in data_sorted]
        imp = [d.get("grid_import_wh", 0) / 1000 for d in data_sorted]
        exp = [d.get("grid_export_wh", 0) / 1000 for d in data_sorted]
        selfuse = [max(s - e, 0) for s, e in zip(solar, exp)]
        ss_pct = [min(su / h * 100, 100) if h > 0 else 0
                  for su, h in zip(selfuse, home)]

        # --- Diverging stacked bars ---
        # Upward: Self-use (green) + Export (teal)
        fig.add_trace(go.Bar(
            x=dates, y=selfuse, name="Self-use",
            marker_color="rgba(40,167,69,0.85)",
            hovertemplate="%{x}<br>Self-use: %{y:.2f} kWh<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            x=dates, y=exp, name="Export",
            marker_color="rgba(23,162,184,0.75)",
            hovertemplate="%{x}<br>Export: %{y:.2f} kWh<extra></extra>",
        ))
        # Downward: Import (red, negative)
        fig.add_trace(go.Bar(
            x=dates, y=[-v for v in imp], name="Import",
            marker_color="rgba(220,53,69,0.80)",
            hovertemplate="%{x}<br>Import: %{customdata:.2f} kWh<extra></extra>",
            customdata=imp,
        ))
        # Self-sufficiency % line on secondary axis
        fig.add_trace(go.Scatter(
            x=dates, y=ss_pct, name="SS%",
            yaxis="y2", mode="lines+markers",
            line={"color": "#ffc107", "width": 2, "dash": "dot"},
            marker={"size": 4, "symbol": "diamond"},
            hovertemplate="%{x}<br>Self-sufficiency: %{y:.0f}%<extra></extra>",
        ))

        fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)
        fig.update_layout(
            **_PLOT_LAYOUT, height=280,
            yaxis_title="kWh", barmode="relative",
            bargap=0.15,
            yaxis2={"overlaying": "y", "side": "right", "title": "%",
                     "showgrid": False, "range": [0, 110],
                     "tickfont": {"color": "#ffc107", "size": 10},
                     "titlefont": {"color": "#ffc107"}},
            uirevision="daily-energy",
        )
        fig.update_layout(legend={"orientation": "h", "y": 1.12, "x": 0.5,
                                  "xanchor": "center", "font": {"size": 10}})
        _apply_crosshair(fig)

        # KPI badges
        t_selfuse = sum(selfuse)
        t_home = sum(home)
        avg_ss = t_selfuse / t_home * 100 if t_home > 0 else 0
        t_imp = sum(imp)
        t_exp = sum(exp)

        return (fig,
                f"{t_selfuse:.1f} kWh",
                f"{avg_ss:.0f}%",
                f"{t_imp:.1f} kWh",
                f"{t_exp:.1f} kWh")

    # -------------------------------------------------------------------
    # 7b. Smart Plugs collapse toggle
    # -------------------------------------------------------------------

    @app.callback(
        Output("plugs-collapse", "is_open"),
        Input("plugs-toggle", "n_clicks"),
        State("plugs-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_plugs(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return is_open

    # -------------------------------------------------------------------
    # 8. IOMeter status (slow refresh)
    # -------------------------------------------------------------------

    @app.callback(
        [
            Output("iometer-conn-icon", "className"),
            Output("iometer-conn-status", "children"),
            Output("iometer-signal", "children"),
            Output("iometer-battery", "children"),
            Output("iometer-meter-no", "children"),
        ],
        Input("interval-slow", "n_intervals"),
    )
    def update_iometer_status(_n):
        data = _api_get("/data")
        if data is None:
            return "fas fa-circle text-muted", "--", "--", "--", "--"

        meter = data.get("meter", {})
        connected = meter.get("connected", False)

        if connected:
            icon_class = "fas fa-circle text-success"
            conn_text = "OK"
        else:
            icon_class = "fas fa-circle text-danger"
            conn_text = "Off"

        rssi = meter.get("bridge_rssi")
        signal = f"{rssi}dBm" if rssi is not None else "--"
        batt = meter.get("battery_level")
        batt_text = f"{batt}%" if batt is not None else "--"
        meter_no = meter.get("meter_number") or "--"

        return icon_class, conn_text, signal, batt_text, meter_no

    # ===================================================================
    # ADMIN PAGE callbacks
    # ===================================================================

    # -------------------------------------------------------------------
    # 9. Strategy config load (on page load + slow interval)
    # -------------------------------------------------------------------

    @app.callback(
        Output({"type": "config-input", "key": ALL}, "value"),
        Input("interval-slow", "n_intervals"),
    )
    def load_config(_n):
        config = _api_get("/config")
        if config is None:
            raise dash.exceptions.PreventUpdate

        ctx = callback_context
        output_ids = [o["id"]["key"] for o in ctx.outputs_list]
        return [config.get(k, 0) for k in output_ids]

    # -------------------------------------------------------------------
    # 10. Strategy config save (individual buttons)
    # -------------------------------------------------------------------

    @app.callback(
        Output("config-status-msg", "children"),
        Input({"type": "config-save-btn", "key": ALL}, "n_clicks"),
        State({"type": "config-input", "key": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_config(n_clicks_list, values):
        ctx = callback_context
        if not ctx.triggered:
            return no_update

        triggered = ctx.triggered[0]
        prop_id = triggered["prop_id"]

        import json as _json
        btn_id = _json.loads(prop_id.rsplit(".", 1)[0])
        key = btn_id["key"]

        for i, inp_id in enumerate(ctx.inputs_list[0]):
            if inp_id["id"]["key"] == key:
                value = values[i]
                break
        else:
            return dbc.Alert("Key not found", color="danger", duration=3000)

        result = _api_post("/config", {"key": key, "value": value})
        if result and result.get("success"):
            return dbc.Alert(f"{key} = {value}", color="success", duration=3000)
        return dbc.Alert(f"Failed to save {key}", color="danger", duration=3000)

    # -------------------------------------------------------------------
    # 11. Recent load changes table (admin page)
    # -------------------------------------------------------------------

    @app.callback(
        Output("recent-events-table", "children"),
        Input("interval-medium", "n_intervals"),
    )
    def render_recent_events(_n):
        events = _api_get("/load-history?hours=24") or []

        if not events:
            return html.P("No changes in 24h.", className="text-muted small")

        header = html.Thead(html.Tr([
            html.Th("Time"),
            html.Th("Load"),
            html.Th("Reason"),
            html.Th("Meter"),
        ]))

        rows = []
        for e in events[:30]:
            ts = e.get("timestamp", "")
            try:
                ts = ts.split("T")[1][:5] if "T" in ts else ts[-8:]
            except Exception:
                pass
            reason = e.get("reason", "")
            reason_color = {
                "manual": "primary",
                "auto_adjust": "success",
                "auto_reduce_export": "info",
                "auto_emergency": "danger",
                "auto_spike": "warning",
                "auto_readjust": "secondary",
                "auto_restore": "light",
            }.get(reason, "secondary")

            rows.append(html.Tr([
                html.Td(ts, className="small"),
                html.Td(f"{e.get('old_load_w', 0)}→{e.get('new_load_w', 0)}W",
                         className="small fw-bold"),
                html.Td(dbc.Badge(reason, color=reason_color)),
                html.Td(f"{e.get('meter_reading_w', 0):.0f}W"
                         if e.get("meter_reading_w") else "--", className="small"),
            ]))

        return dbc.Table([header, html.Tbody(rows)],
                         bordered=True, dark=True, hover=True, size="sm",
                         responsive=True)

    # ------------------------------------------------------------------
    # 15. IOMeter config — load current settings
    # ------------------------------------------------------------------

    @app.callback(
        [Output("iometer-source-radio", "value"),
         Output("iometer-host-input", "value"),
         Output("iometer-config-status", "children")],
        Input("interval-slow", "n_intervals"),
    )
    def load_iometer_config(_n):
        config = _api_get("/config")
        if config is None:
            raise dash.exceptions.PreventUpdate
        source = config.get("iometer_source", "local")
        host = config.get("iometer_host", "192.168.178.96")
        status_text = f"Mode: {'LAN Direct' if source == 'local' else 'ESP32 Push'}"
        return source, host, status_text

    # ------------------------------------------------------------------
    # 16. IOMeter config — toggle host input / ESP32 info visibility
    # ------------------------------------------------------------------

    @app.callback(
        [Output("iometer-host-group", "style"),
         Output("iometer-esp32-info", "style")],
        Input("iometer-source-radio", "value"),
    )
    def toggle_iometer_mode(source):
        if source == "esp32":
            return {"display": "none"}, {"display": "block"}
        return {"display": "block"}, {"display": "none"}

    # ------------------------------------------------------------------
    # 17. IOMeter config — save
    # ------------------------------------------------------------------

    @app.callback(
        Output("iometer-config-save-msg", "children"),
        Input("iometer-config-save-btn", "n_clicks"),
        [State("iometer-source-radio", "value"),
         State("iometer-host-input", "value")],
        prevent_initial_call=True,
    )
    def save_iometer_config(n_clicks, source, host):
        if not n_clicks:
            return no_update

        results = []
        r1 = _api_post("/config", {"key": "iometer_source", "value": source})
        results.append(r1)

        if source == "local" and host:
            r2 = _api_post("/config", {"key": "iometer_host", "value": host})
            results.append(r2)

        if all(r and r.get("success") for r in results):
            mode_label = "LAN Direct" if source == "local" else "ESP32 Push"
            msg = f"Saved: {mode_label}"
            if source == "local":
                msg += f" ({host})"
            return dbc.Alert(msg, color="success", duration=4000)
        return dbc.Alert("Save failed", color="danger", duration=4000)

    # ------------------------------------------------------------------
    # 18. Device schedule — collapse toggle + read-only display
    # ------------------------------------------------------------------

    @app.callback(
        Output("schedule-collapse", "is_open"),
        Input("schedule-toggle", "n_clicks"),
        State("schedule-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_schedule(n_clicks, is_open):
        if n_clicks:
            return not is_open
        return is_open

    @app.callback(
        Output("schedule-content", "children"),
        Input("interval-slow", "n_intervals"),
    )
    def render_schedule(_n):
        data = _api_get("/schedule")
        if data is None or data.get("schedule") is None:
            return html.Span("Schedule not available", className="text-muted small")

        schedule = data["schedule"]

        # Weekday mapping
        day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

        # Parse SB2 schedule format: custom_rate_plan / blend_plan
        sections = []

        # Mode type
        mode_type = schedule.get("mode_type")
        mode_labels = {1: "Smart Match", 2: "Time of Use", 3: "Manual"}
        mode_name = mode_labels.get(mode_type, f"Mode {mode_type}")
        default_load = schedule.get("default_home_load", "?")
        load_range = f"{schedule.get('min_load', 0)}–{schedule.get('max_load', 800)}W"

        sections.append(
            dbc.Row([
                dbc.Col([
                    html.Span("Mode: ", className="text-muted small"),
                    html.Span(mode_name, className="small fw-bold"),
                ], xs=4),
                dbc.Col([
                    html.Span("Default: ", className="text-muted small"),
                    html.Span(f"{default_load}W", className="small fw-bold"),
                ], xs=4),
                dbc.Col([
                    html.Span("Range: ", className="text-muted small"),
                    html.Span(load_range, className="small"),
                ], xs=4),
            ], className="mb-2")
        )

        # Render plan groups
        for plan_key, plan_label in [
            ("custom_rate_plan", "Custom Plan"),
            ("blend_plan", "Blend Plan"),
        ]:
            plan = schedule.get(plan_key)
            if not plan:
                continue

            sections.append(html.Hr(className="my-2"))
            sections.append(html.Div(plan_label, className="small fw-bold mb-1"))

            for group in plan:
                week_days = group.get("week", [])
                day_str = ", ".join(day_names[d] for d in week_days if 0 <= d < 7)
                ranges = group.get("ranges", [])

                rows = []
                for slot in ranges:
                    start = slot.get("start_time", "?")
                    end = slot.get("end_time", "?")
                    power = slot.get("power", "?")
                    rows.append(
                        html.Div([
                            html.Span(f"  {start}–{end}: ",
                                      className="small text-muted",
                                      style={"fontFamily": "monospace"}),
                            html.Span(f"{power}W",
                                      className="small fw-bold text-warning"),
                        ])
                    )

                sections.append(
                    dbc.Card(
                        dbc.CardBody([
                            html.Div(day_str, className="small fw-bold text-info"),
                            *rows,
                        ], className="p-1"),
                        className="mb-1 bg-dark border-secondary",
                    )
                )

        return html.Div(sections)

    # ===================================================================
    # STRATEGY CHANGE callback
    # ===================================================================

    @app.callback(
        Output("strategy-change-status", "children"),
        Input("strategy-selector", "value"),
        prevent_initial_call=True,
    )
    def change_strategy(strategy_name):
        if not strategy_name:
            return no_update
        # Check if already the active strategy
        current = _api_get("/strategies")
        if current and current.get("active") == strategy_name:
            return ""
        result = _api_post("/strategies", {"strategy": strategy_name})
        if result and result.get("success"):
            return html.Span(f"→ {strategy_name}", className="text-success small")
        return html.Span("failed", className="text-danger small")

    # ===================================================================
    # ANALYTICS PAGE callbacks
    # ===================================================================

    # -------------------------------------------------------------------
    # A1. Hourly pattern chart
    # -------------------------------------------------------------------

    @app.callback(
        Output("hourly-pattern-chart", "figure"),
        Input("interval-analytics", "n_intervals"),
    )
    def update_hourly_pattern(_n):
        data = _api_get("/analytics/hourly?days=7") or []
        fig = go.Figure()

        if data:
            hours = [d.get("hour", 0) for d in data]
            avg_power = [d.get("avg_power_w", 0) for d in data]
            min_power = [d.get("min_power_w", 0) for d in data]
            max_power = [d.get("max_power_w", 0) for d in data]

            # Range band (min-max)
            fig.add_trace(go.Scatter(
                x=hours + hours[::-1],
                y=max_power + min_power[::-1],
                fill="toself",
                fillcolor="rgba(23,162,184,0.1)",
                line={"color": "rgba(0,0,0,0)"},
                name="Range",
                showlegend=False,
            ))
            # Average line
            fig.add_trace(go.Scatter(
                x=hours, y=avg_power,
                name="Avg Grid (W)",
                line={"color": "#17a2b8", "width": 2},
                mode="lines+markers",
                marker={"size": 4},
                hovertemplate="Hour %{x}:00<br>Avg: %{y:.0f}W<extra></extra>",
            ))

        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
        fig.update_layout(**_PLOT_LAYOUT, height=250,
                          xaxis_title="Hour of Day", yaxis_title="W",
                          uirevision="hourly")
        _apply_crosshair(fig)
        return fig

    # -------------------------------------------------------------------
    # A1b. Daily detail statistics table
    # -------------------------------------------------------------------

    @app.callback(
        Output("detail-range-store", "data"),
        [Input("detail-range-7d", "n_clicks"),
         Input("detail-range-14d", "n_clicks"),
         Input("detail-range-30d", "n_clicks"),
         Input("detail-range-90d", "n_clicks")],
        prevent_initial_call=True,
    )
    def set_detail_range(n7, n14, n30, n90):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
        ranges = {
            "detail-range-7d": 7,
            "detail-range-14d": 14,
            "detail-range-30d": 30,
            "detail-range-90d": 90,
        }
        return ranges.get(btn_id, 30)

    @app.callback(
        [Output("detail-range-7d", "outline"),
         Output("detail-range-14d", "outline"),
         Output("detail-range-30d", "outline"),
         Output("detail-range-90d", "outline")],
        Input("detail-range-store", "data"),
    )
    def update_detail_btn_style(days):
        active = {7: 0, 14: 1, 30: 2, 90: 3}.get(days, 2)
        return [i != active for i in range(4)]

    @app.callback(
        [Output("daily-detail-table", "children"),
         Output("detail-total-solar", "children"),
         Output("detail-total-selfuse", "children"),
         Output("detail-total-import", "children"),
         Output("detail-total-export", "children"),
         Output("detail-total-cost", "children"),
         Output("detail-total-saved", "children")],
        [Input("interval-analytics", "n_intervals"),
         Input("detail-range-store", "data")],
    )
    def update_daily_detail_table(_n, days):
        days = days or 30
        data = _api_get(f"/analytics/daily?days={days}") or []
        config = _api_get("/config") or {}

        price_kwh = float(config.get("electricity_price_eur_kwh", 0.28))
        feed_in = float(config.get("feed_in_tariff_eur_kwh", 0.082))

        if not data:
            empty = html.P("No data available.", className="text-muted small")
            return empty, "--", "--", "--", "--", "--", "--"

        # --- Build table ---
        header = html.Thead(html.Tr([
            html.Th("Date", className="small"),
            html.Th("Solar", className="small text-end"),
            html.Th("Home", className="small text-end"),
            html.Th("Self-use", className="small text-end"),
            html.Th("Import", className="small text-end"),
            html.Th("Export", className="small text-end"),
            html.Th("Cost", className="small text-end"),
            html.Th("Saved", className="small text-end"),
            html.Th("Feed-in", className="small text-end"),
            html.Th("Load Adj.", className="small text-end"),
        ]), className="table-dark")

        rows = []
        t_solar = t_home = t_import = t_export = t_selfuse = 0.0
        t_cost = t_saved = t_feedin = 0.0

        for d in reversed(data):  # newest first
            solar_kwh = d.get("solar_production_wh", 0) / 1000
            home_kwh = d.get("home_consumption_wh", 0) / 1000
            import_kwh = d.get("grid_import_wh", 0) / 1000
            export_kwh = d.get("grid_export_wh", 0) / 1000
            changes = d.get("load_changes_count", 0)

            # Self-use = solar produced - exported (what we actually used from solar)
            selfuse_kwh = max(solar_kwh - export_kwh, 0)
            # Grid cost = import * price
            grid_cost = import_kwh * price_kwh
            # Saved = self-use * grid price (avoided import)
            saved = selfuse_kwh * price_kwh
            # Feed-in revenue = export * feed-in tariff
            feedin_rev = export_kwh * feed_in

            t_solar += solar_kwh
            t_home += home_kwh
            t_import += import_kwh
            t_export += export_kwh
            t_selfuse += selfuse_kwh
            t_cost += grid_cost
            t_saved += saved
            t_feedin += feedin_rev

            date_str = d.get("date", "")
            # Short date: MM-DD
            short_date = date_str[5:] if len(date_str) >= 10 else date_str

            rows.append(html.Tr([
                html.Td(short_date, className="small"),
                html.Td(f"{solar_kwh:.2f}", className="small text-end text-warning"),
                html.Td(f"{home_kwh:.2f}", className="small text-end"),
                html.Td(f"{selfuse_kwh:.2f}", className="small text-end text-success"),
                html.Td(f"{import_kwh:.2f}", className="small text-end text-danger"),
                html.Td(f"{export_kwh:.2f}", className="small text-end text-info"),
                html.Td(f"€{grid_cost:.2f}", className="small text-end text-danger"),
                html.Td(f"€{saved:.2f}", className="small text-end text-success"),
                html.Td(f"€{feedin_rev:.3f}", className="small text-end text-info"),
                html.Td(str(changes), className="small text-end text-muted"),
            ]))

        # Totals / averages footer
        n_days = len(data)
        footer = html.Tfoot(html.Tr([
            html.Td(f"Σ {n_days}d", className="small fw-bold"),
            html.Td(f"{t_solar:.1f}", className="small text-end fw-bold text-warning"),
            html.Td(f"{t_home:.1f}", className="small text-end fw-bold"),
            html.Td(f"{t_selfuse:.1f}", className="small text-end fw-bold text-success"),
            html.Td(f"{t_import:.1f}", className="small text-end fw-bold text-danger"),
            html.Td(f"{t_export:.1f}", className="small text-end fw-bold text-info"),
            html.Td(f"€{t_cost:.2f}", className="small text-end fw-bold text-danger"),
            html.Td(f"€{t_saved:.2f}", className="small text-end fw-bold text-success"),
            html.Td(f"€{t_feedin:.2f}", className="small text-end fw-bold text-info"),
            html.Td("", className="small"),
        ], className="table-secondary"))

        table = dbc.Table(
            [header, html.Tbody(rows), footer],
            bordered=True, dark=True, hover=True, size="sm",
            responsive=True, striped=True,
        )

        # Summary badges
        solar_s = f"{t_solar:.1f} kWh"
        selfuse_s = f"{t_selfuse:.1f} kWh"
        import_s = f"{t_import:.1f} kWh"
        export_s = f"{t_export:.1f} kWh"
        cost_s = f"€{t_cost:.2f}"
        saved_s = f"€{t_saved + t_feedin:.2f}"

        return table, solar_s, selfuse_s, import_s, export_s, cost_s, saved_s

    # -------------------------------------------------------------------
    # A2. Daily comparison chart
    # -------------------------------------------------------------------

    @app.callback(
        Output("daily-comp-range-store", "data"),
        [Input("daily-comp-7d", "n_clicks"),
         Input("daily-comp-14d", "n_clicks"),
         Input("daily-comp-30d", "n_clicks"),
         Input("daily-comp-90d", "n_clicks")],
        prevent_initial_call=True,
    )
    def set_daily_comp_range(n7, n14, n30, n90):
        ctx = callback_context
        if not ctx.triggered:
            return no_update
        btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
        ranges = {
            "daily-comp-7d": 7,
            "daily-comp-14d": 14,
            "daily-comp-30d": 30,
            "daily-comp-90d": 90,
        }
        return ranges.get(btn_id, 30)

    @app.callback(
        [Output("daily-comp-7d", "outline"),
         Output("daily-comp-14d", "outline"),
         Output("daily-comp-30d", "outline"),
         Output("daily-comp-90d", "outline")],
        Input("daily-comp-range-store", "data"),
    )
    def update_daily_comp_btn_style(days):
        active = {7: 0, 14: 1, 30: 2, 90: 3}.get(days, 2)
        return [i != active for i in range(4)]

    @app.callback(
        [Output("daily-comparison-chart", "figure"),
         Output("daily-comp-avg-solar", "children"),
         Output("daily-comp-avg-ss", "children"),
         Output("daily-comp-import", "children"),
         Output("daily-comp-net-cost", "children")],
        [Input("interval-analytics", "n_intervals"),
         Input("daily-comp-range-store", "data")],
    )
    def update_daily_comparison(_n, days):
        days = days or 30
        data = _api_get(f"/analytics/daily?days={days}") or []
        config = _api_get("/config") or {}
        price_kwh = float(config.get("electricity_price_eur_kwh", 0.28))
        feed_in = float(config.get("feed_in_tariff_eur_kwh", 0.082))

        fig = go.Figure()
        if not data:
            fig.update_layout(**_PLOT_LAYOUT, height=340, uirevision="daily-comp")
            _apply_crosshair(fig)
            return fig, "--", "--", "--", "--"

        dates = [d.get("date", "") for d in data]
        solar = [d.get("solar_production_wh", 0) / 1000 for d in data]
        home = [d.get("home_consumption_wh", 0) / 1000 for d in data]
        imp = [d.get("grid_import_wh", 0) / 1000 for d in data]
        exp = [d.get("grid_export_wh", 0) / 1000 for d in data]
        selfuse = [max(s - e, 0) for s, e in zip(solar, exp)]
        ss_pct = [min(su / h * 100, 100) if h > 0 else 0
                  for su, h in zip(selfuse, home)]

        # --- Stacked areas: energy flow ---
        # Self-use area (green, bottom layer)
        fig.add_trace(go.Scatter(
            x=dates, y=selfuse, name="Self-use",
            fill="tozeroy", fillcolor="rgba(40,167,69,0.35)",
            line={"color": "#28a745", "width": 1.5},
            stackgroup="pos",
            hovertemplate="%{x}<br>Self-use: %{y:.2f} kWh<extra></extra>",
        ))
        # Export area (teal, stacked on top of self-use)
        fig.add_trace(go.Scatter(
            x=dates, y=exp, name="Export",
            fill="tonexty", fillcolor="rgba(23,162,184,0.25)",
            line={"color": "#17a2b8", "width": 1.5},
            stackgroup="pos",
            hovertemplate="%{x}<br>Export: %{y:.2f} kWh<extra></extra>",
        ))
        # Import area (red, below zero)
        fig.add_trace(go.Scatter(
            x=dates, y=[-v for v in imp], name="Import",
            fill="tozeroy", fillcolor="rgba(220,53,69,0.30)",
            line={"color": "#dc3545", "width": 1.5},
            hovertemplate="%{x}<br>Import: %{customdata:.2f} kWh<extra></extra>",
            customdata=imp,
        ))
        # Home consumption as dashed white line
        fig.add_trace(go.Scatter(
            x=dates, y=home, name="Home",
            mode="lines",
            line={"color": "rgba(255,255,255,0.6)", "width": 1.5, "dash": "dot"},
            hovertemplate="%{x}<br>Home: %{y:.2f} kWh<extra></extra>",
        ))
        # Self-sufficiency % on right axis
        fig.add_trace(go.Scatter(
            x=dates, y=ss_pct, name="SS%",
            yaxis="y2", mode="lines+markers",
            line={"color": "#ffc107", "width": 2},
            marker={"size": 3, "symbol": "diamond"},
            hovertemplate="%{x}<br>SS: %{y:.0f}%<extra></extra>",
        ))

        fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)
        fig.update_layout(
            **_PLOT_LAYOUT, height=340,
            yaxis_title="kWh",
            yaxis2={"overlaying": "y", "side": "right", "title": "%",
                     "showgrid": False, "range": [0, 110],
                     "tickfont": {"color": "#ffc107", "size": 10},
                     "titlefont": {"color": "#ffc107"}},
            uirevision="daily-comp",
        )
        fig.update_layout(legend={"orientation": "h", "y": 1.12, "x": 0.5,
                                  "xanchor": "center", "font": {"size": 10}})
        _apply_crosshair(fig)

        # KPI
        n_days = len(data) or 1
        t_solar = sum(solar)
        t_selfuse = sum(selfuse)
        t_home = sum(home)
        t_imp = sum(imp)
        t_exp = sum(exp)
        avg_ss = t_selfuse / t_home * 100 if t_home > 0 else 0
        net_cost = t_imp * price_kwh - t_exp * feed_in

        return (fig,
                f"{t_solar / n_days:.1f} kWh",
                f"{avg_ss:.0f}%",
                f"{t_imp:.1f} kWh",
                f"\u20ac{net_cost:.2f}")

    # -------------------------------------------------------------------
    # A3. Weekly balance – horizontal diverging bars
    # -------------------------------------------------------------------

    @app.callback(
        Output("weekly-summary-chart", "figure"),
        Input("interval-analytics", "n_intervals"),
    )
    def update_weekly_summary(_n):
        data = _api_get("/analytics/weekly?weeks=12") or []
        fig = go.Figure()

        if data:
            weeks = [d.get("week", "") for d in data]
            solar = [d.get("solar_wh", 0) / 1000 for d in data]
            home = [d.get("consumption_wh", 0) / 1000 for d in data]
            imp = [d.get("import_wh", 0) / 1000 for d in data]
            exp = [d.get("export_wh", 0) / 1000 for d in data]
            selfuse = [max(s - e, 0) for s, e in zip(solar, exp)]
            ss_pct = [min(su / h * 100, 100) if h > 0 else 0
                      for su, h in zip(selfuse, home)]

            # Horizontal diverging bars
            # Right side: Self-use (green) + Export (teal)
            fig.add_trace(go.Bar(
                y=weeks, x=selfuse, name="Self-use",
                orientation="h", marker_color="rgba(40,167,69,0.85)",
                hovertemplate="%{y}<br>Self-use: %{x:.1f} kWh<extra></extra>",
            ))
            fig.add_trace(go.Bar(
                y=weeks, x=exp, name="Export",
                orientation="h", marker_color="rgba(23,162,184,0.75)",
                hovertemplate="%{y}<br>Export: %{x:.1f} kWh<extra></extra>",
            ))
            # Left side: Import (red, negative)
            fig.add_trace(go.Bar(
                y=weeks, x=[-v for v in imp], name="Import",
                orientation="h", marker_color="rgba(220,53,69,0.80)",
                hovertemplate="%{y}<br>Import: %{customdata:.1f} kWh<extra></extra>",
                customdata=imp,
            ))
            # SS% annotations on the right
            max_solar = max(solar) if solar else 10
            for i, (w, pct) in enumerate(zip(weeks, ss_pct)):
                fig.add_annotation(
                    x=max_solar * 1.05, y=w,
                    text=f"<b>{pct:.0f}%</b>",
                    font={"color": "#ffc107", "size": 10},
                    showarrow=False, xanchor="left",
                )

        fig.add_vline(x=0, line_color="rgba(255,255,255,0.4)", line_width=1)
        fig.update_layout(
            **_PLOT_LAYOUT, height=360,
            xaxis_title="kWh", barmode="relative",
            bargap=0.2,
            uirevision="weekly",
        )
        fig.update_layout(legend={"orientation": "h", "y": 1.08, "x": 0.5,
                                  "xanchor": "center", "font": {"size": 10}})
        _apply_crosshair(fig)
        return fig

    # -------------------------------------------------------------------
    # A4. Monthly overview – indicators + stacked area
    # -------------------------------------------------------------------

    @app.callback(
        Output("monthly-summary-chart", "figure"),
        Input("interval-analytics", "n_intervals"),
    )
    def update_monthly_summary(_n):
        data = _api_get("/analytics/monthly?months=12") or []
        config = _api_get("/config") or {}
        price_kwh = float(config.get("electricity_price_eur_kwh", 0.28))
        feed_in = float(config.get("feed_in_tariff_eur_kwh", 0.082))

        if not data:
            fig = go.Figure()
            fig.update_layout(**_PLOT_LAYOUT, height=420, uirevision="monthly")
            _apply_crosshair(fig)
            return fig

        months = [d.get("month", "") for d in data]
        solar = [d.get("solar_wh", 0) / 1000 for d in data]
        home = [d.get("consumption_wh", 0) / 1000 for d in data]
        imp = [d.get("import_wh", 0) / 1000 for d in data]
        exp = [d.get("export_wh", 0) / 1000 for d in data]
        selfuse = [max(s - e, 0) for s, e in zip(solar, exp)]
        ss_pct = [min(su / h * 100, 100) if h > 0 else 0
                  for su, h in zip(selfuse, home)]
        net_cost = [i * price_kwh - e * feed_in for i, e in zip(imp, exp)]

        # Build subplots: top row = 3 indicators, bottom = area chart
        fig = make_subplots(
            rows=2, cols=3,
            specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}],
                   [{"type": "xy", "colspan": 3}, None, None]],
            row_heights=[0.22, 0.78],
            vertical_spacing=0.12,
        )

        # Latest month values + delta vs previous
        cur_solar = solar[-1] if solar else 0
        prev_solar = solar[-2] if len(solar) > 1 else cur_solar
        cur_ss = ss_pct[-1] if ss_pct else 0
        prev_ss = ss_pct[-2] if len(ss_pct) > 1 else cur_ss
        cur_cost = net_cost[-1] if net_cost else 0
        prev_cost = net_cost[-2] if len(net_cost) > 1 else cur_cost

        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=cur_solar,
            delta={"reference": prev_solar, "relative": True,
                   "valueformat": ".0%", "increasing": {"color": "#28a745"},
                   "decreasing": {"color": "#dc3545"}},
            title={"text": "Solar kWh", "font": {"size": 12, "color": "#aaa"}},
            number={"font": {"size": 22, "color": "#ffc107"}, "valueformat": ".1f"},
        ), row=1, col=1)

        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=cur_ss,
            delta={"reference": prev_ss, "valueformat": ".0f",
                   "suffix": "%",
                   "increasing": {"color": "#28a745"},
                   "decreasing": {"color": "#dc3545"}},
            title={"text": "Self-sufficiency", "font": {"size": 12, "color": "#aaa"}},
            number={"font": {"size": 22, "color": "#28a745"}, "valueformat": ".0f",
                    "suffix": "%"},
        ), row=1, col=2)

        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=cur_cost,
            delta={"reference": prev_cost, "valueformat": ".2f",
                   "prefix": "\u20ac",
                   "increasing": {"color": "#dc3545"},
                   "decreasing": {"color": "#28a745"}},
            title={"text": "Net Grid Cost", "font": {"size": 12, "color": "#aaa"}},
            number={"font": {"size": 22, "color": "#dc3545"}, "valueformat": ".2f",
                    "prefix": "\u20ac"},
        ), row=1, col=3)

        # Area chart: Self-use + Export stacked, Import negative
        fig.add_trace(go.Scatter(
            x=months, y=selfuse, name="Self-use",
            fill="tozeroy", fillcolor="rgba(40,167,69,0.4)",
            line={"color": "#28a745", "width": 2},
            stackgroup="pos",
            hovertemplate="%{x}<br>Self-use: %{y:.1f} kWh<extra></extra>",
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=months, y=exp, name="Export",
            fill="tonexty", fillcolor="rgba(23,162,184,0.3)",
            line={"color": "#17a2b8", "width": 2},
            stackgroup="pos",
            hovertemplate="%{x}<br>Export: %{y:.1f} kWh<extra></extra>",
        ), row=2, col=1)
        fig.add_trace(go.Scatter(
            x=months, y=[-v for v in imp], name="Import",
            fill="tozeroy", fillcolor="rgba(220,53,69,0.3)",
            line={"color": "#dc3545", "width": 2},
            hovertemplate="%{x}<br>Import: %{customdata:.1f} kWh<extra></extra>",
            customdata=imp,
        ), row=2, col=1)
        # Net cost line on area chart
        fig.add_trace(go.Scatter(
            x=months, y=net_cost, name="Net Cost \u20ac",
            mode="lines+markers", yaxis="y2",
            line={"color": "#ff6b6b", "width": 2, "dash": "dot"},
            marker={"size": 5},
            hovertemplate="%{x}<br>Net cost: \u20ac%{y:.2f}<extra></extra>",
        ), row=2, col=1)

        fig.update_layout(
            **_PLOT_LAYOUT, height=420,
            uirevision="monthly",
        )
        fig.update_layout(legend={"orientation": "h", "y": 0.45, "x": 0.5,
                                  "xanchor": "center", "font": {"size": 10}})
        # Area chart axes
        fig.update_yaxes(title_text="kWh", row=2, col=1)
        fig.update_xaxes(row=2, col=1)
        _apply_crosshair(fig)
        return fig

    # -------------------------------------------------------------------
    # A5. Weather forecast (7-day)
    # -------------------------------------------------------------------

    # WMO weather code → icon/description mapping
    _WMO_ICONS = {
        0: ("☀️", "Clear"), 1: ("🌤️", "Mainly clear"), 2: ("⛅", "Partly cloudy"),
        3: ("☁️", "Overcast"), 45: ("🌫️", "Fog"), 48: ("🌫️", "Fog"),
        51: ("🌦️", "Light drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌧️", "Heavy drizzle"),
        61: ("🌧️", "Light rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
        71: ("🌨️", "Light snow"), 73: ("🌨️", "Snow"), 75: ("🌨️", "Heavy snow"),
        80: ("🌦️", "Light showers"), 81: ("🌧️", "Showers"), 82: ("⛈️", "Heavy showers"),
        95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "Thunderstorm"), 99: ("⛈️", "Thunderstorm"),
    }

    @app.callback(
        [Output("weather-today-hours", "children"),
         Output("weather-tomorrow-hours", "children"),
         Output("weather-cloud-cover", "children"),
         Output("weather-outlook", "children"),
         Output("weather-7day-table", "children"),
         Output("weather-generation-chart", "figure")],
        Input("interval-analytics", "n_intervals"),
    )
    def update_weather(_n):
        data = _api_get("/weather")
        empty_fig = go.Figure()
        empty_fig.update_layout(**_PLOT_LAYOUT, height=180)

        if data is None or data.get("forecast") is None:
            return "--", "--", "--", "--", "", empty_fig

        forecast = data["forecast"]
        today_h = forecast.get("today_solar_hours", 0)
        tomorrow_h = forecast.get("tomorrow_solar_hours", 0)
        cloud = forecast.get("tomorrow_cloud_cover_pct", 0)
        is_sunny = forecast.get("tomorrow_is_sunny", False)
        outlook = (html.Span("☀️ Sunny", className="text-warning")
                   if is_sunny else html.Span("☁️ Cloudy", className="text-muted"))

        # --- 7-day table ---
        days = forecast.get("days", [])
        if days:
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            header = html.Thead(html.Tr([
                html.Th("Day", className="small"),
                html.Th("", className="small"),
                html.Th("Sun", className="small text-end"),
                html.Th("Cloud", className="small text-end"),
                html.Th("Rain", className="small text-end"),
                html.Th("Temp", className="small text-end"),
                html.Th("Est. kWh", className="small text-end"),
            ]), className="table-dark")

            rows = []
            for i, d in enumerate(days):
                date_str = d.get("date", "")
                try:
                    from datetime import datetime as _dt
                    dt = _dt.strptime(date_str, "%Y-%m-%d")
                    day_label = day_names[dt.weekday()]
                    short_date = date_str[5:]  # MM-DD
                except Exception:
                    day_label = ""
                    short_date = date_str

                wcode = d.get("weather_code", 0)
                icon, _ = _WMO_ICONS.get(wcode, ("❓", "Unknown"))

                sun_h = d.get("sunshine_hours", 0)
                cloud_pct = d.get("cloud_cover_pct", 0)
                precip = d.get("precipitation_mm", 0)
                t_max = d.get("temp_max")
                t_min = d.get("temp_min")
                est = d.get("estimated_kwh", 0)

                temp_str = ""
                if t_max is not None and t_min is not None:
                    temp_str = f"{t_min:.0f}/{t_max:.0f}°"

                # Color est_kwh
                if est >= 4:
                    est_cls = "small text-end fw-bold text-warning"
                elif est >= 2:
                    est_cls = "small text-end text-success"
                else:
                    est_cls = "small text-end text-muted"

                # Highlight today
                row_cls = "table-active" if i == 0 else ""

                rows.append(html.Tr([
                    html.Td(f"{day_label} {short_date}", className="small"),
                    html.Td(icon, className="small text-center"),
                    html.Td(f"{sun_h:.1f}h", className="small text-end text-warning"),
                    html.Td(f"{cloud_pct:.0f}%", className="small text-end"),
                    html.Td(f"{precip:.1f}" if precip > 0 else "-",
                             className="small text-end text-info"),
                    html.Td(temp_str, className="small text-end"),
                    html.Td(f"{est:.1f}", className=est_cls),
                ], className=row_cls))

            table = dbc.Table(
                [header, html.Tbody(rows)],
                bordered=True, dark=True, hover=True, size="sm",
                responsive=True, className="mb-1",
            )
        else:
            table = html.P("No forecast data", className="text-muted small")

        # --- Generation bar chart ---
        fig = go.Figure()
        if days:
            dates = [d.get("date", "")[5:] for d in days]  # MM-DD
            est_kwhs = [d.get("estimated_kwh", 0) for d in days]
            sun_hours = [d.get("sunshine_hours", 0) for d in days]

            # Color bars by estimate
            colors = []
            for e in est_kwhs:
                if e >= 4:
                    colors.append("#ffc107")
                elif e >= 2:
                    colors.append("#28a745")
                else:
                    colors.append("#6c757d")

            fig.add_trace(go.Bar(
                x=dates, y=est_kwhs,
                name="Est. kWh",
                marker_color=colors,
                text=[f"{e:.1f}" for e in est_kwhs],
                textposition="outside",
                textfont={"size": 10, "color": "white"},
                hovertemplate="%{x}<br>Est: %{y:.1f} kWh<extra></extra>",
            ))

            # Add sunshine hours as line overlay
            fig.add_trace(go.Scatter(
                x=dates, y=sun_hours,
                name="Sun hrs",
                yaxis="y2",
                line={"color": "#ffc107", "width": 1.5, "dash": "dot"},
                mode="lines+markers",
                marker={"size": 4},
                hovertemplate="%{x}<br>Sun: %{y:.1f}h<extra></extra>",
            ))

        fig.update_layout(
            **_PLOT_LAYOUT, height=180,
            yaxis_title="kWh",
            yaxis2={"overlaying": "y", "side": "right", "title": "hrs",
                     "gridcolor": "rgba(0,0,0,0)",
                     "showgrid": False},
            showlegend=False,
            uirevision="weather-gen",
        )
        _apply_crosshair(fig)

        return (f"{today_h:.1f}", f"{tomorrow_h:.1f}", f"{cloud:.0f}",
                outlook, table, fig)
