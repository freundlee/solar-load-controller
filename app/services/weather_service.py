"""Weather service — fetches solar forecast for strategy optimization.

Uses the Open-Meteo API (free, no API key required) to get:
- 7-day daily sunshine hours, radiation, cloud cover
- Estimated PV generation based on radiation
- Tomorrow-specific data for strategy decisions

This helps the battery_guard strategy decide how aggressive to be
with battery usage overnight.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Open-Meteo API (free, no key needed)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Rough PV yield factor: kWh per MJ/m² of radiation for a typical ~1kWp rooftop system
# This is an approximate multiplier — real yield depends on panel orientation, efficiency, etc.
_PV_YIELD_FACTOR_KWH_PER_MJ = 0.15


class WeatherService:
    """Fetches weather forecast for solar optimization."""

    def __init__(self, latitude: float = 48.14, longitude: float = 11.58,
                 pv_kwp: float = 1.6) -> None:
        """Default coordinates: Munich, Germany. pv_kwp = system peak power in kWp."""
        self.latitude = latitude
        self.longitude = longitude
        self.pv_kwp = pv_kwp  # used for generation estimate scaling
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 3600.0  # refresh hourly

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def get_forecast(self) -> dict | None:
        """Get solar forecast. Returns cached data if fresh."""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        try:
            session = await self._ensure_session()
            params = {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "daily": "sunshine_duration,shortwave_radiation_sum,"
                         "temperature_2m_max,temperature_2m_min,"
                         "precipitation_sum,weathercode",
                "hourly": "cloud_cover,direct_radiation",
                "timezone": "auto",
                "forecast_days": 7,
            }
            async with session.get(OPEN_METEO_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Weather API returned %d", resp.status)
                    return self._cache
                data = await resp.json()

            forecast = self._parse_forecast(data)
            self._cache = forecast
            self._cache_time = now
            return forecast

        except Exception as exc:
            logger.warning("Weather fetch failed: %s", exc)
            return self._cache

    def _parse_forecast(self, data: dict) -> dict:
        """Parse Open-Meteo response into a comprehensive forecast dict."""
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})

        dates = daily.get("time", [])
        sunshine_durations = daily.get("sunshine_duration", [])
        radiation_sums = daily.get("shortwave_radiation_sum", [])
        temp_maxs = daily.get("temperature_2m_max", [])
        temp_mins = daily.get("temperature_2m_min", [])
        precip_sums = daily.get("precipitation_sum", [])
        weather_codes = daily.get("weathercode", [])

        cloud_covers = hourly.get("cloud_cover", [])

        # Build per-day forecast
        days = []
        for i, date_str in enumerate(dates):
            sunshine_h = (sunshine_durations[i] / 3600) if i < len(sunshine_durations) else 0
            radiation_mj = radiation_sums[i] if i < len(radiation_sums) else 0
            temp_max = temp_maxs[i] if i < len(temp_maxs) else None
            temp_min = temp_mins[i] if i < len(temp_mins) else None
            precip = precip_sums[i] if i < len(precip_sums) else 0
            wcode = weather_codes[i] if i < len(weather_codes) else 0

            # Average cloud cover for this day (hours i*24 to (i+1)*24)
            day_clouds = cloud_covers[i * 24:(i + 1) * 24]
            avg_cloud = sum(day_clouds) / len(day_clouds) if day_clouds else 50

            # Estimated PV generation (kWh)
            est_kwh = radiation_mj * _PV_YIELD_FACTOR_KWH_PER_MJ * (self.pv_kwp / 1.0)

            days.append({
                "date": date_str,
                "sunshine_hours": round(sunshine_h, 1),
                "radiation_mj": round(radiation_mj, 1),
                "cloud_cover_pct": round(avg_cloud, 0),
                "temp_max": round(temp_max, 1) if temp_max is not None else None,
                "temp_min": round(temp_min, 1) if temp_min is not None else None,
                "precipitation_mm": round(precip, 1),
                "weather_code": wcode,
                "estimated_kwh": round(est_kwh, 2),
            })

        # Legacy top-level fields for backward compatibility
        today = days[0] if len(days) > 0 else {}
        tomorrow = days[1] if len(days) > 1 else {}

        return {
            # 7-day forecast array
            "days": days,
            # Legacy fields (used by battery_guard strategy)
            "today_solar_hours": today.get("sunshine_hours", 0),
            "tomorrow_solar_hours": tomorrow.get("sunshine_hours", 0),
            "today_radiation_mj": today.get("radiation_mj", 0),
            "tomorrow_radiation_mj": tomorrow.get("radiation_mj", 0),
            "tomorrow_cloud_cover_pct": tomorrow.get("cloud_cover_pct", 50),
            "tomorrow_is_sunny": (
                tomorrow.get("sunshine_hours", 0) >= 5
                and tomorrow.get("cloud_cover_pct", 50) < 50
            ),
            "today_estimated_kwh": today.get("estimated_kwh", 0),
            "tomorrow_estimated_kwh": tomorrow.get("estimated_kwh", 0),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
