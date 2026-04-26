"""Dash callbacks — wires dashboard UI to backend services.

All callbacks communicate with the FastAPI backend via HTTP requests
to /api/* endpoints (same server, different mount path).
"""

import logging
from datetime import datetime, timezone

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import requests
from dash import Input, Output, State, callback_context, html, ALL, MATCH, no_update

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


# ---------------------------------------------------------------------------
# Register all callbacks
# ---------------------------------------------------------------------------

def register_callbacks(app: dash.Dash) -> None:

    # -------------------------------------------------------------------
    # 1. Fast refresh: real-time metrics, power flow, auto status (3s)
    # -------------------------------------------------------------------

    @app.callback(
        [
            # Realtime metrics
            Output("solar-value", "children"),
            Output("battery-value", "children"),
            Output("meter-value", "children"),
            Output("load-value", "children"),
            # Power flow
            Output("flow-solar", "children"),
            Output("flow-battery-soc", "children"),
            Output("flow-battery-power", "children"),
            Output("flow-home", "children"),
            Output("flow-grid", "children"),
            Output("flow-grid-icon", "className"),
            Output("flow-arrow-grid-home", "children"),
            Output("flow-arrow-grid-home", "className"),
            # Auto status
            Output("strategy-state", "children"),
            Output("strategy-adjustments", "children"),
            Output("strategy-spikes", "children"),
            Output("strategy-ignored", "children"),
            Output("strategy-last-action", "children"),
            Output("strategy-current-spike", "children"),
            # Daily summary
            Output("daily-solar", "children"),
            Output("daily-charge", "children"),
            Output("daily-discharge", "children"),
            Output("daily-usage", "children"),
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

        # Grid display
        meter_display = f"{meter_w:.0f}" if meter_w is not None else "--"
        if meter_w is not None:
            if meter_w > 10:
                grid_icon_class = "fas fa-tower-broadcast fa-2x text-danger"
                grid_arrow = "⟶"
                grid_arrow_class = "fs-3 text-center text-danger mt-2"
            elif meter_w < -10:
                grid_icon_class = "fas fa-tower-broadcast fa-2x text-success"
                grid_arrow = "⟵"
                grid_arrow_class = "fs-3 text-center text-success mt-2"
            else:
                grid_icon_class = "fas fa-tower-broadcast fa-2x text-muted"
                grid_arrow = "⟷"
                grid_arrow_class = "fs-3 text-center text-muted mt-2"
        else:
            grid_icon_class = "fas fa-tower-broadcast fa-2x text-muted"
            grid_arrow = "⟷"
            grid_arrow_class = "fs-3 text-center text-muted mt-2"

        # Strategy
        spike_info = strategy.get("current_spike")
        spike_text = "None"
        if spike_info:
            spike_text = f"{spike_info['peak_power_w']:.0f}W peak, {spike_info['duration_s']}s ({spike_info['profile_action']})"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        connected = "Connected" if meter.get("connected") else "Disconnected"
        init = "Anker OK" if anker.get("initialized") else "Anker N/A"
        footer = f"{init} | IOMeter {connected} | {now_str}"

        return [
            # Metrics
            f"{solar_w:.0f}",
            f"{battery_soc:.0f}",
            meter_display,
            f"{load_w}",
            # Power flow
            f"{solar_w:.0f} W",
            f"{battery_soc:.0f}",
            f"{battery_pw:.0f}",
            f"{home_w:.0f} W",
            f"{meter_display} W",
            grid_icon_class,
            grid_arrow,
            grid_arrow_class,
            # Strategy
            strategy.get("state", "--"),
            str(strategy.get("total_adjustments", 0)),
            str(strategy.get("total_spikes_detected", 0)),
            str(strategy.get("total_spikes_ignored", 0)),
            strategy.get("last_action", "none"),
            spike_text,
            # Daily
            f"{anker.get('today_solar_kwh', 0):.2f}",
            f"{anker.get('today_charge_kwh', 0):.2f}",
            f"{anker.get('today_discharge_kwh', 0):.2f}",
            f"{anker.get('today_usage_kwh', 0):.2f}",
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
            return dbc.Alert(
                f"✅ Load set to {load_val}W",
                color="success",
                duration=4000,
            )
        else:
            error = result.get("detail", "Unknown error") if result else "API unreachable"
            return dbc.Alert(
                f"❌ Failed: {error}",
                color="danger",
                duration=4000,
            )

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
            status = "🟢 Auto mode active" if enabled else "🔴 Auto mode disabled"
            return html.Span(status)
        return html.Span("⚠️ Failed to toggle auto mode", className="text-warning")

    # -------------------------------------------------------------------
    # 5. History chart (30s refresh)
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
                name="Grid Meter (W)",
                line={"color": "#17a2b8", "width": 1},
                fill="tozeroy",
                fillcolor="rgba(23,162,184,0.1)",
            ))

        if load_data:
            load_data_sorted = sorted(load_data, key=lambda x: x.get("timestamp", ""))
            fig.add_trace(go.Scatter(
                x=[r["timestamp"] for r in load_data_sorted],
                y=[r["new_load_w"] for r in load_data_sorted],
                name="Load Setting (W)",
                line={"color": "#ffc107", "width": 2},
                mode="lines+markers",
            ))

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin={"l": 40, "r": 20, "t": 10, "b": 30},
            legend={"orientation": "h", "y": 1.1},
            xaxis={"gridcolor": "rgba(255,255,255,0.05)"},
            yaxis={"gridcolor": "rgba(255,255,255,0.05)", "title": "Watts"},
            height=280,
        )

        # Zero line
        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")

        return fig

    # -------------------------------------------------------------------
    # 6. Grid import / cost estimate (daily — slow refresh)
    # -------------------------------------------------------------------

    @app.callback(
        [
            Output("daily-grid-import", "children"),
            Output("daily-cost-saved", "children"),
        ],
        Input("interval-slow", "n_intervals"),
    )
    def update_daily_energy(_n):
        data = _api_get("/daily-energy?days=1")
        if data and len(data) > 0:
            today = data[0]
            grid_kwh = today.get("grid_import_wh", 0) / 1000
            saved = today.get("cost_saved_eur", 0)
            return f"{grid_kwh:.2f}", f"{saved:.2f}"
        return "0.00", "0.00"

    # -------------------------------------------------------------------
    # 7. Strategy config load (on page load + slow interval)
    # -------------------------------------------------------------------

    @app.callback(
        Output({"type": "config-input", "key": ALL}, "value"),
        Input("interval-slow", "n_intervals"),
    )
    def load_config(_n):
        config = _api_get("/config")
        if config is None:
            raise dash.exceptions.PreventUpdate

        # We need to return values in the same order as ALL pattern-matching
        # outputs. Dash resolves them alphabetically by key.
        keys = sorted(config.keys())
        # But we only have inputs for specific keys. Use ctx to get ids.
        ctx = callback_context
        output_ids = [o["id"]["key"] for o in ctx.outputs_list]
        return [config.get(k, 0) for k in output_ids]

    # -------------------------------------------------------------------
    # 8. Strategy config save (individual buttons)
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

        # Find which button was clicked
        triggered = ctx.triggered[0]
        prop_id = triggered["prop_id"]

        # Parse the key from the pattern-matched ID
        import json as _json
        btn_id = _json.loads(prop_id.rsplit(".", 1)[0])
        key = btn_id["key"]

        # Find the corresponding value
        for i, inp_id in enumerate(ctx.inputs_list[0]):
            if inp_id["id"]["key"] == key:
                value = values[i]
                break
        else:
            return dbc.Alert("Key not found", color="danger", duration=3000)

        result = _api_post("/config", {"key": key, "value": value})
        if result and result.get("success"):
            return dbc.Alert(f"✅ {key} = {value}", color="success", duration=3000)
        return dbc.Alert(f"❌ Failed to save {key}", color="danger", duration=3000)

    # -------------------------------------------------------------------
    # 9. Appliance profiles table
    # -------------------------------------------------------------------

    @app.callback(
        Output("profiles-table", "children"),
        Input("interval-slow", "n_intervals"),
        Input("btn-add-profile", "n_clicks"),
    )
    def render_profiles_table(_n, _add_clicks):
        profiles = _api_get("/profiles") or []

        if not profiles:
            return html.P("No profiles configured.", className="text-muted")

        header = html.Thead(html.Tr([
            html.Th("Name"),
            html.Th("Power Range (W)"),
            html.Th("Typ. Duration"),
            html.Th("Action"),
            html.Th("Seen"),
            html.Th(""),
        ]))

        rows = []
        for p in profiles:
            rows.append(html.Tr([
                html.Td(p["name"]),
                html.Td(f"{p['power_min_w']:.0f} – {p['power_max_w']:.0f}"),
                html.Td(f"{p.get('typical_duration_s', '?')}s"),
                html.Td(
                    dbc.Badge(p["action"],
                              color={"ignore": "secondary", "observe": "info",
                                     "adjust": "warning"}.get(p["action"], "light")),
                ),
                html.Td(str(p.get("occurrences", 0))),
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
                         bordered=True, dark=True, hover=True, size="sm")

    # -------------------------------------------------------------------
    # 10. Add profile
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
            return dbc.Alert("Please fill in Name, Min W, and Max W", color="warning", duration=3000)

        result = _api_post("/profiles", {
            "name": name,
            "power_min_w": float(min_w),
            "power_max_w": float(max_w),
            "typical_duration_s": int(typ_dur) if typ_dur else None,
            "max_duration_s": int(typ_dur * 2) if typ_dur else None,
            "action": action or "observe",
        })
        if result and result.get("success"):
            return dbc.Alert(f"✅ Profile '{name}' added", color="success", duration=3000)
        return dbc.Alert("❌ Failed to add profile", color="danger", duration=3000)

    # -------------------------------------------------------------------
    # 11. Delete profile
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
            return dbc.Alert("✅ Profile deleted", color="info", duration=3000)
        return dbc.Alert("❌ Failed to delete", color="danger", duration=3000)

    # -------------------------------------------------------------------
    # 12. IOMeter status (slow refresh)
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
        icon_class = "fas fa-circle text-success" if connected else "fas fa-circle text-danger"
        conn_text = "Connected" if connected else "Disconnected"
        rssi = meter.get("bridge_rssi")
        signal = f"{rssi} dBm" if rssi is not None else "--"
        batt = meter.get("battery_level")
        batt_text = f"{batt}%" if batt is not None else "--"
        meter_no = meter.get("meter_number") or "--"

        return icon_class, conn_text, signal, batt_text, meter_no
