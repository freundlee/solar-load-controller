"""Anker Solarbank 2 API service wrapper.

Manages the API session lifecycle and provides simplified methods
for reading solar/battery data and setting the home load.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from aiohttp import ClientSession

from app.api import api
from app.api.apitypes import SolarbankUsageMode
from app.config import anker_cfg
from app import database as db

logger = logging.getLogger(__name__)


class AnkerService:
    """High-level wrapper around the Anker Solix API."""

    def __init__(self) -> None:
        self._api: api.AnkerSolixApi | None = None
        self._session: ClientSession | None = None
        self._initialized = False
        self._site_id: str | None = None
        self._device_sn: str | None = None

        # Cached dashboard data (refreshed by poller)
        self.solar_power_w: float = 0.0
        self.battery_soc: float = 0.0          # 0-100 %
        self.battery_power_w: float = 0.0      # charging power
        self.output_power_w: float = 0.0
        self.current_load_w: int = 0            # device preset
        self.home_demand_w: float = 0.0
        self.active_mode: str = "Unknown"

        # Per-channel solar data
        self.pv1_power_w: float = 0.0
        self.pv2_power_w: float = 0.0
        self.micro_inverter_power_w: float = 0.0
        self.ac_power_w: float = 0.0

        # Per-channel daily energy (kWh) - populated by refresh_details
        self.today_pv1_kwh: float = 0.0
        self.today_pv2_kwh: float = 0.0
        self.today_mi_kwh: float = 0.0

        # Smart plugs: list of {sn, alias, tag, power_w, online}
        self.smart_plugs: list[dict] = []

        # Inverter
        self.inverter_power_w: float = 0.0
        self.inverter_alias: str = ""
        self.inverter_online: bool = False

        # Energy stats (today)
        self.today_solar_kwh: float = 0.0

        # Schedule (cached from device data)
        self.schedule: dict | None = None
        self.today_charge_kwh: float = 0.0
        self.today_discharge_kwh: float = 0.0
        self.today_usage_kwh: float = 0.0
        self.today_grid_import_kwh: float = 0.0
        self.today_grid_export_kwh: float = 0.0

    # ---- Lifecycle ----------------------------------------------------------

    async def initialize(self) -> bool:
        """Authenticate and discover site/device."""
        if self._initialized:
            return True

        try:
            if not anker_cfg.email or not anker_cfg.password:
                logger.error("Anker credentials not configured")
                return False

            self._session = ClientSession()

            api_logger = logging.getLogger("anker_api")
            api_logger.setLevel(logging.WARNING)

            self._api = api.AnkerSolixApi(
                anker_cfg.email,
                anker_cfg.password,
                anker_cfg.country,
                self._session,
                api_logger,
                local_tz=db.get_display_tz(),
            )
            if not await self._api.async_authenticate():
                logger.error("Anker API authentication failed")
                await self._session.close()
                self._session = None
                self._api = None
                return False

            # Discover site and solarbank device
            await self._api.update_sites()
            if self._api.sites:
                self._site_id = next(iter(self._api.sites.keys()))

            await self._api.update_device_details()
            for sn, device in self._api.devices.items():
                if (
                    device.get("type") == "solarbank"
                    and device.get("site_id") == self._site_id
                ):
                    self._device_sn = sn
                    break

            if not self._site_id or not self._device_sn:
                logger.error("No solarbank device found")
                return False

            self._initialized = True
            logger.info(
                "Anker API initialized — site=%s device=%s",
                self._site_id,
                self._device_sn,
            )
            return True

        except Exception as exc:
            logger.exception("Anker API initialization failed: %s", exc)
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
            self._api = None
            return False

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._initialized = False

    async def _ensure_init(self) -> None:
        if not self._initialized:
            if not await self.initialize():
                raise RuntimeError("Anker API not initialized")

    # ---- Data polling -------------------------------------------------------

    async def refresh_data(self) -> None:
        """Refresh site & device data from Anker cloud."""
        await self._ensure_init()
        try:
            await self._api.update_sites(siteId=self._site_id)

            site = self._api.sites.get(self._site_id, {})
            sb_info = site.get("solarbank_info", {})

            self.solar_power_w = float(sb_info.get("total_photovoltaic_power", 0))
            self.battery_soc = round(
                float(sb_info.get("total_battery_power", 0)) * 100
            )
            self.battery_power_w = float(sb_info.get("total_charging_power", 0))
            self.output_power_w = float(sb_info.get("total_output_power", 0))
            self.home_demand_w = float(site.get("home_load_power", 0))

            # Per-channel solar (from solarbank_info aggregated)
            self.pv1_power_w = float(sb_info.get("solar_power_1", 0))
            self.pv2_power_w = float(sb_info.get("solar_power_2", 0))
            self.micro_inverter_power_w = float(sb_info.get("micro_inverter_power", 0))
            self.ac_power_w = float(sb_info.get("ac_power", 0))

            # Device preset (current load setting) + per-device data
            for sn, device in self._api.devices.items():
                if sn == self._device_sn:
                    preset = device.get("preset_system_output_power", 0)
                    self.current_load_w = int(float(preset or 0))
                    # Cache schedule from device data
                    if "schedule" in device:
                        self.schedule = device["schedule"]

            # Operating mode
            mode = site.get("scene_mode")
            if mode:
                mode_name = next(
                    (m.name for m in SolarbankUsageMode if m.value == mode),
                    "Unknown",
                )
                self.active_mode = mode_name

            # Smart plugs
            plugs = []
            for sn, device in self._api.devices.items():
                if device.get("type") == "smartplug":
                    plugs.append({
                        "sn": sn,
                        "alias": device.get("alias") or device.get("name", sn),
                        "tag": device.get("tag", ""),
                        "power_w": float(device.get("current_power", 0)),
                        "online": device.get("status") == "1"
                                  or device.get("status_desc") == "online",
                    })
            self.smart_plugs = plugs

            # Standalone inverter (MI80 etc.)
            for sn, device in self._api.devices.items():
                if device.get("type") == "inverter":
                    self.inverter_power_w = float(device.get("generate_power", 0))
                    self.inverter_alias = device.get("alias") or device.get("name", "")
                    self.inverter_online = (device.get("status_desc") == "online")
                    break

            # Energy today — only update if energy_details is populated.
            # update_sites() replaces the sites dict and wipes energy_details,
            # so skip the update when it's empty to preserve values from
            # refresh_details() / update_device_energy().
            energy = site.get("energy_details") or {}
            today = energy.get("today") or {}
            if today:
                self.today_solar_kwh = float(today.get("solar_production", 0))
                self.today_charge_kwh = float(today.get("solar_to_battery", 0))
                self.today_discharge_kwh = float(today.get("battery_discharge", 0))
                self.today_usage_kwh = float(today.get("solar_to_home", 0))
                self.today_grid_import_kwh = float(today.get("grid_to_home", 0))
                self.today_grid_export_kwh = float(today.get("solar_to_grid", 0))
                # Per-channel daily energy
                self.today_pv1_kwh = float(today.get("solar_production_pv1", 0))
                self.today_pv2_kwh = float(today.get("solar_production_pv2", 0))
                self.today_mi_kwh = float(today.get("solar_production_microinverter", 0))

        except Exception as exc:
            logger.exception("Error refreshing Anker data: %s", exc)

    async def refresh_details(self) -> None:
        """Refresh detailed device/energy data (slow, call less frequently)."""
        await self._ensure_init()
        try:
            await self._api.update_device_details()
            await self._api.update_site_details()
            await self._api.update_device_energy()

            # Read energy now — update_device_energy populates energy_details,
            # but the next update_sites() call will wipe it.
            site = self._api.sites.get(self._site_id, {})
            energy = site.get("energy_details") or {}
            today = energy.get("today") or {}
            if today:
                self.today_solar_kwh = float(today.get("solar_production", 0))
                self.today_charge_kwh = float(today.get("solar_to_battery", 0))
                self.today_discharge_kwh = float(today.get("battery_discharge", 0))
                self.today_usage_kwh = float(today.get("solar_to_home", 0))
                self.today_grid_import_kwh = float(today.get("grid_to_home", 0))
                self.today_grid_export_kwh = float(today.get("solar_to_grid", 0))
                self.today_pv1_kwh = float(today.get("solar_production_pv1", 0))
                self.today_pv2_kwh = float(today.get("solar_production_pv2", 0))
                self.today_mi_kwh = float(today.get("solar_production_microinverter", 0))
                logger.info(
                    "Energy updated: solar=%.2f charge=%.2f discharge=%.2f "
                    "pv1=%.2f pv2=%.2f mi=%.2f kWh",
                    self.today_solar_kwh, self.today_charge_kwh,
                    self.today_discharge_kwh, self.today_pv1_kwh,
                    self.today_pv2_kwh, self.today_mi_kwh,
                )
        except Exception as exc:
            logger.exception("Error refreshing Anker details: %s", exc)

    # ---- Load control -------------------------------------------------------

    async def set_home_load(self, watts: int) -> tuple[bool, str]:
        """Set the SB2 home load preset.

        Args:
            watts: Load value 0-800W (must be multiple of 10).

        Returns:
            (success, message) tuple.
        """
        await self._ensure_init()
        try:
            # Validate
            watts = max(0, min(800, watts))
            watts = round(watts / 10) * 10  # snap to 10W grid

            result = await self._api.set_sb2_home_load(
                siteId=self._site_id,
                deviceSn=self._device_sn,
                preset=watts,
            )

            if result:
                old_load = self.current_load_w
                self.current_load_w = watts
                logger.info("Home load set: %dW → %dW", old_load, watts)
                return True, f"Load set to {watts}W"
            else:
                return False, f"API returned failure for {watts}W"

        except Exception as exc:
            logger.exception("Error setting home load: %s", exc)
            return False, str(exc)

    async def get_schedule(self) -> dict | None:
        """Get current device schedule/parameters."""
        await self._ensure_init()
        try:
            result = await self._api.get_device_parm(
                siteId=self._site_id,
                paramType="6",
                deviceSn=self._device_sn,
            )
            return result.get("param_data") if result else None
        except Exception as exc:
            logger.exception("Error getting schedule: %s", exc)
            return None

    # ---- Convenience getters ------------------------------------------------

    def get_dashboard_data(self) -> dict:
        """Return snapshot of all cached data for the dashboard."""
        return {
            "solar_power_w": self.solar_power_w,
            "battery_soc": self.battery_soc,
            "battery_power_w": self.battery_power_w,
            "output_power_w": self.output_power_w,
            "current_load_w": self.current_load_w,
            "home_demand_w": self.home_demand_w,
            "active_mode": self.active_mode,
            # Per-channel solar
            "pv1_power_w": self.pv1_power_w,
            "pv2_power_w": self.pv2_power_w,
            "micro_inverter_power_w": self.micro_inverter_power_w,
            "ac_power_w": self.ac_power_w,
            "today_pv1_kwh": self.today_pv1_kwh,
            "today_pv2_kwh": self.today_pv2_kwh,
            "today_mi_kwh": self.today_mi_kwh,
            # Inverter
            "inverter_power_w": self.inverter_power_w,
            "inverter_alias": self.inverter_alias,
            "inverter_online": self.inverter_online,
            # Smart plugs
            "smart_plugs": self.smart_plugs,
            # Energy today
            "today_solar_kwh": self.today_solar_kwh,
            "today_charge_kwh": self.today_charge_kwh,
            "today_discharge_kwh": self.today_discharge_kwh,
            "today_usage_kwh": self.today_usage_kwh,
            "today_grid_import_kwh": self.today_grid_import_kwh,
            "today_grid_export_kwh": self.today_grid_export_kwh,
            # Meta
            "site_id": self._site_id,
            "device_sn": self._device_sn,
            "initialized": self._initialized,
            "schedule": self.schedule,
        }
