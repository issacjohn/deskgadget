"""Weather module: Open-Meteo (no API key), location auto-detected by IP."""
from __future__ import annotations

import asyncio
import logging
import time

import requests

from core.base import Module as BaseModule

log = logging.getLogger("deskgadget.weather")

WMO = {
    0: ("Clear sky", "sun"),
    1: ("Mainly clear", "sun"),
    2: ("Partly cloudy", "cloud-sun"),
    3: ("Overcast", "cloud"),
    45: ("Fog", "fog"),
    48: ("Rime fog", "fog"),
    51: ("Light drizzle", "rain"),
    53: ("Drizzle", "rain"),
    55: ("Dense drizzle", "rain"),
    56: ("Freezing drizzle", "snow"),
    57: ("Freezing drizzle", "snow"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "snow"),
    67: ("Freezing rain", "snow"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Light showers", "rain"),
    81: ("Showers", "rain"),
    82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"),
    86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "storm"),
    96: ("Thunderstorm", "storm"),
    99: ("Thunderstorm", "storm"),
}


class Module(BaseModule):
    def __init__(self, hub, settings):
        super().__init__(hub, settings)
        self.data: dict | None = None
        self.error: str | None = None
        self.place: str | None = None
        self._located_at = 0.0

    async def on_settings(self) -> None:
        self.data = None
        self._located_at = 0.0

    # -- location ----------------------------------------------------------
    def _locate(self) -> tuple[float, float, str]:
        lat = self.settings.get("latitude")
        lon = self.settings.get("longitude")
        label = str(self.settings.get("location") or "").strip()
        if lat not in (None, "", 0) and lon not in (None, "", 0):
            return float(lat), float(lon), label or f"{float(lat):.2f}, {float(lon):.2f}"
        if time.time() - self._located_at < 86400 and getattr(self, "_coords", None):
            return (*self._coords, self.place or "")
        try:
            r = requests.get(
                "http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon",
                timeout=6,
            )
            j = r.json()
            if j.get("status") == "success":
                self._coords = (float(j["lat"]), float(j["lon"]))
                self._located_at = time.time()
                self.place = ", ".join(x for x in (j.get("city"), j.get("regionName")) if x) or j.get("country")
                return (*self._coords, self.place or "")
        except Exception:
            log.warning("ip geolocation failed")
        # fallback: Berlin
        self._coords = (52.52, 13.405)
        self._located_at = time.time()
        self.place = "Berlin"
        return (*self._coords, "Berlin")

    # -- fetch -------------------------------------------------------------
    def _fetch(self) -> dict:
        lat, lon, place = self._locate()
        units = "fahrenheit" if str(self.settings.get("units", "C")).upper() == "F" else "celsius"
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": round(lat, 3),
                "longitude": round(lon, 3),
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "is_day,precipitation,weather_code,wind_speed_10m",
                "hourly": "temperature_2m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min",
                "timezone": "auto",
                "forecast_days": 7,
                "temperature_unit": units,
                "wind_speed_unit": "kmh",
            },
            timeout=12,
        )
        r.raise_for_status()
        payload = r.json()
        payload["_place"] = str(self.settings.get("location") or "").strip() or place
        return payload

    async def update(self) -> None:
        try:
            self.data = await asyncio.to_thread(self._fetch)
            self.error = None
        except Exception as exc:
            self.error = str(exc)[:120]
            log.warning("weather fetch failed: %s", exc)

    # -- render ------------------------------------------------------------
    def _fmt_hour(self, iso: str) -> str:
        try:
            return iso.split("T")[1][:5]
        except Exception:
            return iso

    def _fmt_day(self, iso: str) -> str:
        try:
            t = time.strptime(iso, "%Y-%m-%d")
            return time.strftime("%a", t)
        except Exception:
            return iso

    def page(self) -> dict:
        if not self.data:
            return {
                "blocks": [
                    {
                        "type": "hero",
                        "label": "WEATHER",
                        "value": "--",
                        "unit": "°",
                        "sub": self.error or "Fetching conditions…",
                    }
                ]
            }

        cur = self.data["current"]
        code = int(cur.get("weather_code", 0))
        text, icon = WMO.get(code, ("Unknown", "cloud"))
        unit = "°F" if str(self.settings.get("units", "C")).upper() == "F" else "°C"
        temp = round(float(cur["temperature_2m"]))

        # Details live inside the hero card so the page keeps its two columns
        # and nothing important falls below the fold on a short panel.
        blocks = [
            {
                "type": "hero",
                "label": str(self.data.get("_place") or "").upper(),
                "value": f"{temp}",
                "unit": unit,
                "sub": text,
                "icon": icon,
                "is_day": bool(cur.get("is_day", 1)),
                "stats": [
                    {"label": "Feels", "value": f"{round(float(cur['apparent_temperature']))}{unit}"},
                    {"label": "Humidity", "value": f"{round(float(cur['relative_humidity_2m']))}%"},
                    {"label": "Wind", "value": f"{round(float(cur['wind_speed_10m']))} km/h"},
                ],
                "col": 0,
            },
        ]

        hourly = self.data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        codes = hourly.get("weather_code", [])
        now_iso = str(self.data.get("current", {}).get("time", ""))
        start = 0
        for i, t in enumerate(times):
            if t >= now_iso:
                start = i
                break
        rows = []
        for i in range(start, min(start + 4, len(times))):
            _, hicon = WMO.get(int(codes[i]), ("", "cloud"))
            rows.append(
                {
                    "label": "Now" if i == start else self._fmt_hour(times[i]),
                    "value": f"{round(float(temps[i]))}{unit}",
                    "icon": hicon,
                }
            )
        if rows:
            blocks.append({"type": "hours", "items": rows, "col": 0})

        daily = self.data.get("daily", {})
        dtimes = daily.get("time", [])
        dmax = daily.get("temperature_2m_max", [])
        dmin = daily.get("temperature_2m_min", [])
        dcodes = daily.get("weather_code", [])
        drows = []
        for i in range(min(4, len(dtimes))):
            _, dicon = WMO.get(int(dcodes[i]), ("", "cloud"))
            drows.append(
                {
                    "title": "Today" if i == 0 else self._fmt_day(dtimes[i]),
                    "sub": WMO.get(int(dcodes[i]), ("", ""))[0],
                    "value": f"{round(float(dmax[i]))}° / {round(float(dmin[i]))}°",
                    "icon": dicon,
                }
            )
        if drows:
            blocks.append({"type": "list", "title": "THIS WEEK", "items": drows, "col": 1})

        return {"blocks": blocks}
