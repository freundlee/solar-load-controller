"""Dash callbacks — wires dashboard UI to backend services.

All callbacks communicate with the FastAPI backend via HTTP requests
to /api/* endpoints (same server, different mount path).

Two-page routing:
  /dashboard/      — Operations dashboard
  /dashboard/admin — Admin panel
"""

import logging
from datetime import datetime, timezone

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import requests
from dash import Input, Output, State, callback_context, html, ALL, MATCH, no_update

from app.dashboard.layouts import get_operations_page, get_admin_page

logger = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:8000/api"


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
)


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
        spike_info = strategy.get("current_spike")
        spike_text = "None"
        if spike_info:
            spike_text = (f"{spike_info['peak_power_w']:.0f}W peak, "
                          f"{spike_info['duration_s']}s ({spike_info['profile_action']})")

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
            spike_text,
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
        Output("live-meter-chart", "figure"),
        Input("interval-medium", "n_intervals"),
    )
    def update_live_meter_chart(_n):
        data = _api_get("/meter-live?seconds=300") or []

        fig = go.Figure()

        if data:
            fig.add_trace(go.Scatter(
                x=[r["timestamp"] for r in data],
                y=[r["power_w"] for r in data],
                name="Grid (W)",
                line={"color": "#17a2b8", "width": 2},
                fill="tozeroy",
                fillcolor="rgba(23,162,184,0.15)",
            ))

        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)")
        fig.update_layout(**_PLOT_LAYOUT, height=200, yaxis_title="W")
        return fig

    # -------------------------------------------------------------------
    # 6. History chart (10s refresh — from DB)
    # -------------------------------------------------------------------

    @app.callback(
        Output("history-chart", "figure"),
        Input("interval-medium", "n_intervals"),
    )
    def update_history_chart(_n):
        load_data = _api_get("/load-history?hours=24") or []
        meter_data = _api_get("/meter-history?seconds=86400") or []

        fig = go.Figure()

        if meter_data:
            meter_data_sorted = sorted(meter_data, key=lambda x: x.get("timestamp", ""))
            fig.add_trace(go.Scatter(
                x=[r["timestamp"] for r in meter_data_sorted],
                y=[r["power_w"] for r in meter_data_sorted],
                name="Grid (W)",
                line={"color": "#17a2b8", "width": 1},
                fill="tozeroy",
                fillcolor="rgba(23,162,184,0.1)",
            ))

        if load_data:
            load_data_sorted = sorted(load_data, key=lambda x: x.get("timestamp", ""))
            fig.add_trace(go.Scatter(
                x=[r["timestamp"] for r in load_data_sorted],
                y=[r["new_load_w"] for r in load_data_sorted],
                name="Load (W)",
                line={"color": "#ffc107", "width": 2},
                mode="lines+markers",
                marker={"size": 3},
            ))

        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")
        fig.update_layout(**_PLOT_LAYOUT, height=250, yaxis_title="W")
        return fig

    # -------------------------------------------------------------------
    # 7. Daily energy bar chart (slow refresh)
    # -------------------------------------------------------------------

    @app.callback(
        Output("daily-energy-chart", "figure"),
        Input("interval-slow", "n_intervals"),
    )
    def update_daily_energy_chart(_n):
        data = _api_get("/daily-energy?days=30") or []

        fig = go.Figure()

        if data:
            # Sort by date ascending
            data_sorted = sorted(data, key=lambda x: x.get("date", ""))
            dates = [d["date"] for d in data_sorted]

            # Solar production
            fig.add_trace(go.Bar(
                x=dates,
                y=[d.get("solar_production_wh", 0) / 1000 for d in data_sorted],
                name="Solar (kWh)",
                marker_color="#ffc107",
                opacity=0.8,
            ))

            # Home consumption
            fig.add_trace(go.Bar(
                x=dates,
                y=[d.get("home_consumption_wh", 0) / 1000 for d in data_sorted],
                name="Home (kWh)",
                marker_color="#17a2b8",
                opacity=0.8,
            ))

            # Grid export (Einspeisung)
            fig.add_trace(go.Bar(
                x=dates,
                y=[d.get("grid_export_wh", 0) / 1000 for d in data_sorted],
                name="Export (kWh)",
                marker_color="#28a745",
                opacity=0.8,
            ))

            # Grid import
            fig.add_trace(go.Bar(
                x=dates,
                y=[d.get("grid_import_wh", 0) / 1000 for d in data_sorted],
                name="Import (kWh)",
                marker_color="#dc3545",
                opacity=0.8,
            ))

        fig.update_layout(
            **_PLOT_LAYOUT,
            height=280,
            yaxis_title="kWh",
            barmode="group",
            bargap=0.15,
            bargroupgap=0.05,
        )
        return fig

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
    # 11. Appliance profiles table
    # -------------------------------------------------------------------

    @app.callback(
        Output("profiles-table", "children"),
        Input("interval-slow", "n_intervals"),
        Input("btn-add-profile", "n_clicks"),
    )
    def render_profiles_table(_n, _add_clicks):
        profiles = _api_get("/profiles") or []

        if not profiles:
            return html.P("No profiles.", className="text-muted small")

        header = html.Thead(html.Tr([
            html.Th("Name"),
            html.Th("Range"),
            html.Th("Action"),
            html.Th(""),
        ]))

        rows = []
        for p in profiles:
            rows.append(html.Tr([
                html.Td(p["name"], className="small"),
                html.Td(f"{p['power_min_w']:.0f}–{p['power_max_w']:.0f}W", className="small"),
                html.Td(
                    dbc.Badge(p["action"],
                              color={"ignore": "secondary", "observe": "info",
                                     "adjust": "warning"}.get(p["action"], "light")),
                ),
                html.Td(
                    dbc.Button(
                        html.I(className="fas fa-trash"),
                        id={"type": "delete-profile-btn", "index": p["id"]},
                        color="outline-danger",
                        size="sm",
                    ),
                ),
            ]))

        return dbc.Table([header, html.Tbody(rows)],
                         bordered=True, dark=True, hover=True, size="sm",
                         responsive=True)

    # -------------------------------------------------------------------
    # 12. Add profile
    # -------------------------------------------------------------------

    @app.callback(
        Output("profile-status-msg", "children"),
        Input("btn-add-profile", "n_clicks"),
        [
            State("profile-name", "value"),
            State("profile-min-w", "value"),
            State("profile-max-w", "value"),
            State("profile-typ-dur", "value"),
            State("profile-action", "value"),
        ],
        prevent_initial_call=True,
    )
    def add_profile(_clicks, name, min_w, max_w, typ_dur, action):
        if not name or min_w is None or max_w is None:
            return dbc.Alert("Fill Name, Min W, Max W", color="warning", duration=3000)

        result = _api_post("/profiles", {
            "name": name,
            "power_min_w": float(min_w),
            "power_max_w": float(max_w),
            "typical_duration_s": int(typ_dur) if typ_dur else None,
            "max_duration_s": int(typ_dur * 2) if typ_dur else None,
            "action": action or "observe",
        })
        if result and result.get("success"):
            return dbc.Alert(f"'{name}' added", color="success", duration=3000)
        return dbc.Alert("Failed", color="danger", duration=3000)

    # -------------------------------------------------------------------
    # 13. Delete profile
    # -------------------------------------------------------------------

    @app.callback(
        Output("profile-status-msg", "children", allow_duplicate=True),
        Input({"type": "delete-profile-btn", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def delete_profile(n_clicks_list):
        ctx = callback_context
        if not ctx.triggered or not any(n_clicks_list):
            return no_update

        import json as _json
        triggered = ctx.triggered[0]
        btn_id = _json.loads(triggered["prop_id"].rsplit(".", 1)[0])
        profile_id = btn_id["index"]

        result = _api_delete(f"/profiles/{profile_id}")
        if result and result.get("success"):
            return dbc.Alert("Deleted", color="info", duration=3000)
        return dbc.Alert("Failed", color="danger", duration=3000)

    # -------------------------------------------------------------------
    # 14. Recent load changes table (admin page)
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
