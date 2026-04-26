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

        # Energy stats (today)
        self.today_solar_kwh: float = 0.0
        self.today_charge_kwh: float = 0.0
        self.today_discharge_kwh: float = 0.0
        self.today_usage_kwh: float = 0.0

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
            unit = sb_info.get("power_unit", "W")

            self.solar_power_w = float(sb_info.get("total_photovoltaic_power", 0))
            self.battery_soc = round(
                float(sb_info.get("total_battery_power", 0)) * 100
            )
            self.battery_power_w = float(sb_info.get("total_charging_power", 0))
            self.output_power_w = float(sb_info.get("total_output_power", 0))

            self.home_demand_w = float(site.get("home_load_power", 0))

            # Device preset (current load setting)
            for sn, device in self._api.devices.items():
                if sn == self._device_sn:
                    preset = device.get("preset_system_output_power", 0)
                    self.current_load_w = int(float(preset or 0))
                    break

            # Operating mode
            mode = site.get("scene_mode")
            if mode:
                mode_name = next(
                    (m.name for m in SolarbankUsageMode if m.value == mode),
                    "Unknown",
                )
                self.active_mode = mode_name

            # Energy today
            energy = site.get("energy_details") or {}
            today = energy.get("today") or {}
            self.today_solar_kwh = float(today.get("solar_production", 0))
            self.today_charge_kwh = float(today.get("solar_to_battery", 0))
            self.today_discharge_kwh = float(today.get("battery_discharge", 0))
            self.today_usage_kwh = float(today.get("solar_to_home", 0))

        except Exception as exc:
            logger.exception("Error refreshing Anker data: %s", exc)

    async def refresh_details(self) -> None:
        """Refresh detailed device/energy data (slow, call less frequently)."""
        await self._ensure_init()
        try:
            await self._api.update_device_details()
            await self._api.update_site_details()
            await self._api.update_device_energy()
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
            "today_solar_kwh": self.today_solar_kwh,
            "today_charge_kwh": self.today_charge_kwh,
            "today_discharge_kwh": self.today_discharge_kwh,
            "today_usage_kwh": self.today_usage_kwh,
            "site_id": self._site_id,
            "device_sn": self._device_sn,
            "initialized": self._initialized,
        }
