from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import aiohttp
from flask import Flask, jsonify, render_template, request


def get_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = get_int_env("PORT", 5000)
    debug: bool = get_bool_env("DEBUG", True)
    gametools_base_url: str = os.getenv("GAMETOOLS_BASE_URL", "https://api.gametools.network")
    default_platform: str = os.getenv("BFV_DEFAULT_PLATFORM", "pc")
    default_lang: str = os.getenv("BFV_DEFAULT_LANG", "zh-cn")
    request_timeout: int = get_int_env("BFV_REQUEST_TIMEOUT", 15)
    dashboard_cache_ttl: int = get_int_env("BFV_DASHBOARD_CACHE_TTL", 90)
    bfban_cache_ttl: int = get_int_env("BFV_BFBAN_CACHE_TTL", 600)
    default_server_limit: int = get_int_env("BFV_SERVER_LIMIT", 20)
    max_server_limit: int = get_int_env("BFV_MAX_SERVER_LIMIT", 50)
    user_agent: str = os.getenv("BFV_USER_AGENT", "BFV Query Tool/3.0")


SETTINGS = Settings()
PLATFORM_OPTIONS = {"pc", "xboxone", "ps4"}
REGION_OPTIONS = {"all", "Asia", "EU", "NAm", "SAm", "OC", "Afr", "AC"}

BFBAN_STATUS_LABELS = {
    "0": "待处理",
    "1": "石锤",
    "2": "待自证",
    "3": "MOSS 自证",
    "4": "无效举报",
    "5": "讨论中",
    "6": "等待确认",
    "7": "状态未知",
    "8": "刷枪",
    "9": "上诉中",
}

DEFAULT_BFBAN_STATE = {
    "hacker": False,
    "statusCode": None,
    "statusLabel": "无记录",
    "url": "",
    "cheatMethods": "",
}


app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
try:
    app.json.ensure_ascii = False
except AttributeError:
    pass


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TTLCache:
    def __init__(self, ttl: int) -> None:
        self.ttl = ttl
        self._values: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._values.get(key)
        if not item:
            return None

        expires_at, value = item
        if expires_at < time.time():
            self._values.pop(key, None)
            return None

        return value

    def set(self, key: str, value: Any) -> None:
        self._values[key] = (time.time() + self.ttl, value)


dashboard_cache = TTLCache(SETTINGS.dashboard_cache_ttl)
bfban_cache = TTLCache(SETTINGS.bfban_cache_ttl)


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_decimal(value: Any, digits: int = 2) -> float:
    return round(to_float(value), digits)


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_percentage(value: Any) -> str:
    if value in (None, ""):
        return "0%"
    if isinstance(value, (int, float)):
        return f"{value:.1f}%"
    text = str(value).strip()
    return text or "0%"


def format_seconds_as_hours(value: Any) -> float:
    seconds = to_float(value)
    if seconds <= 0:
        return 0.0
    return round(seconds / 3600, 1)


def occupancy_rate(players: int, capacity: int) -> float:
    if capacity <= 0:
        return 0.0
    return round(players / capacity * 100, 1)


def sorted_records(items: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        values: list[Any] = []
        for key in keys:
            value = item.get(key)
            if isinstance(value, str):
                values.append(value.lower())
            else:
                values.append(value if value is not None else 0)
        return tuple(values)

    return sorted(items, key=sort_key, reverse=True)


def top_records(items: list[dict[str, Any]], limit: int, primary: str, secondary: str | None = None) -> list[dict[str, Any]]:
    non_zero = [
        item
        for item in items
        if to_float(item.get(primary)) > 0 or (secondary and to_float(item.get(secondary)) > 0)
    ]
    target = non_zero if non_zero else items
    return target[:limit]


def pick_top_stats(items: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    ranked = sorted(
        [{"name": name, "value": value} for name, value in items.items()],
        key=lambda item: item["value"],
        reverse=True,
    )
    return ranked[:limit]


def normalize_bfban_entry(item: dict[str, Any] | None) -> dict[str, Any]:
    if not item:
        return dict(DEFAULT_BFBAN_STATE)

    hacker = bool(item.get("hacker"))
    status_code = str(item.get("status")) if item.get("status") is not None else None
    return {
        "hacker": hacker,
        "statusCode": status_code,
        "statusLabel": BFBAN_STATUS_LABELS.get(status_code or "", "已记录" if hacker else "无记录"),
        "url": item.get("url", "") or "",
        "cheatMethods": item.get("cheatMethods", "") or "",
    }


def normalize_weapon(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("weaponName") or "未知武器",
        "type": item.get("type") or "未知类型",
        "image": item.get("image") or "",
        "kills": to_int(item.get("kills")),
        "kpm": format_decimal(item.get("killsPerMinute")),
        "headshotKills": to_int(item.get("headshotKills")),
        "headshotRate": safe_percentage(item.get("headshots")),
        "accuracy": safe_percentage(item.get("accuracy")),
        "shotsFired": to_int(item.get("shotsFired")),
        "shotsHit": to_int(item.get("shotsHit")),
        "timeHours": format_seconds_as_hours(item.get("timeEquipped")),
    }


def normalize_vehicle(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("vehicleName") or "未知载具",
        "type": item.get("type") or "未知类型",
        "image": item.get("image") or "",
        "kills": to_int(item.get("kills")),
        "kpm": format_decimal(item.get("killsPerMinute")),
        "destroyed": to_int(item.get("destroyed")),
        "timeHours": format_seconds_as_hours(item.get("timeIn")),
    }


def normalize_class(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("className") or "未知兵种",
        "score": to_int(item.get("score")),
        "kills": to_int(item.get("kills")),
        "kpm": format_decimal(item.get("kpm")),
        "timePlayed": item.get("timePlayed") or "0:00:00",
        "timeHours": format_seconds_as_hours(item.get("secondsPlayed")),
        "image": item.get("image") or "",
        "altImage": item.get("altImage") or "",
    }


def normalize_server(item: dict[str, Any]) -> dict[str, Any]:
    players = to_int(item.get("playerAmount"))
    max_players = to_int(item.get("maxPlayers"))
    queue = to_int(item.get("inQue"))
    spectators = to_int(item.get("inSpectator"))
    return {
        "name": item.get("prefix") or item.get("name") or "未命名服务器",
        "description": item.get("description") or "",
        "players": players,
        "maxPlayers": max_players,
        "queue": queue,
        "spectators": spectators,
        "serverInfo": item.get("serverInfo") or f"{players}/{max_players}",
        "occupancy": occupancy_rate(players, max_players),
        "image": item.get("url") or "",
        "mode": item.get("mode") or item.get("gameMode") or "未知模式",
        "map": item.get("currentMap") or item.get("level") or item.get("mapName") or "未知地图",
        "country": item.get("country") or "未知",
        "region": item.get("region") or "未知",
        "platform": item.get("platform") or SETTINGS.default_platform,
        "official": bool(item.get("official")),
        "custom": bool(item.get("isCustom")),
        "gameId": str(item.get("gameId") or ""),
    }


def normalize_server_player(item: dict[str, Any], bfban: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "rank": to_int(item.get("rank")),
        "latency": to_int(item.get("latency")),
        "slot": to_int(item.get("slot")),
        "name": item.get("name") or "未知玩家",
        "platoon": item.get("platoon") or "",
        "personaId": str(item.get("player_id") or ""),
        "userId": str(item.get("user_id") or ""),
        "bfban": bfban or dict(DEFAULT_BFBAN_STATE),
    }


class GametoolsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_session(self) -> aiohttp.ClientSession:
        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)
        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": "application/json",
        }
        return aiohttp.ClientSession(timeout=timeout, headers=headers)

    def _build_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        query: dict[str, str] = {}
        for key, value in (params or {}).items():
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                query[key] = str(value).lower()
            else:
                query[key] = str(value)

        if not query:
            return f"{self.settings.gametools_base_url}{path}"

        return f"{self.settings.gametools_base_url}{path}?{urlencode(query, doseq=True)}"

    @staticmethod
    def _parse_payload(text: str) -> Any:
        if not text:
            return None

        payload = json.loads(text)
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return payload
        return payload

    @staticmethod
    def _extract_error_message(body: str, status: int) -> str:
        try:
            payload = GametoolsClient._parse_payload(body)
        except json.JSONDecodeError:
            return f"Gametools 请求失败（HTTP {status}）"

        if isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                return "；".join(str(item) for item in errors)
            for key in ("message", "detail", "code", "error"):
                if payload.get(key):
                    return str(payload[key])

        return f"Gametools 请求失败（HTTP {status}）"

    async def _request_json(
        self,
        session: aiohttp.ClientSession,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any = None,
    ) -> Any:
        url = self._build_url(path, params)

        try:
            async with session.request(method, url, json=payload) as response:
                text = await response.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise ApiError("请求 Gametools 超时或网络异常，请稍后再试。", 502) from exc

        if response.status >= 400:
            message = self._extract_error_message(text, response.status)
            raise ApiError(message, 502 if response.status >= 500 else response.status)

        try:
            return self._parse_payload(text)
        except json.JSONDecodeError as exc:
            raise ApiError("Gametools 返回了无法解析的数据。", 502) from exc

    def _player_lookup(self, query: str, platform: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "platform": platform,
            "lang": self.settings.default_lang,
        }
        if query.isdigit():
            params["playerid"] = query
        else:
            params["name"] = query
        return params

    async def _fetch_player_payloads(
        self,
        session: aiohttp.ClientSession,
        lookup: dict[str, Any],
    ) -> tuple[Any, Any, Any, Any]:
        return await asyncio.gather(
            self._request_json(session, "GET", "/bfv/stats/", params=lookup),
            self._request_json(session, "GET", "/bfv/weapons/", params=lookup),
            self._request_json(session, "GET", "/bfv/vehicles/", params=lookup),
            self._request_json(session, "GET", "/bfv/classes/", params=lookup),
        )

    async def fetch_overview(self) -> dict[str, Any]:
        cached = dashboard_cache.get("overview")
        if cached:
            return cached

        async with self.create_session() as session:
            payload = await self._request_json(session, "GET", "/bfv/status/")

        regions = payload.get("regions", {}) if isinstance(payload, dict) else {}
        all_region = regions.get("ALL", {})
        totals = all_region.get("amounts", {})

        normalized_regions = []
        for region_code, region_info in regions.items():
            if region_code == "ALL":
                continue

            amounts = region_info.get("amounts", {})
            servers = to_int(amounts.get("serverAmount"))
            players = to_int(amounts.get("soldierAmount"))
            queue = to_int(amounts.get("queueAmount"))
            if not any((servers, players, queue)):
                continue

            normalized_regions.append(
                {
                    "code": region_code,
                    "name": region_info.get("regionName") or region_code,
                    "players": players,
                    "servers": servers,
                    "queue": queue,
                }
            )

        normalized_regions = sorted(normalized_regions, key=lambda item: item["players"], reverse=True)
        result = {
            "updatedAt": current_timestamp(),
            "totals": {
                "players": to_int(totals.get("soldierAmount")),
                "servers": to_int(totals.get("serverAmount")),
                "queue": to_int(totals.get("queueAmount")),
                "spectators": to_int(totals.get("spectatorAmount")),
                "communityServers": to_int(totals.get("communityServerAmount")),
                "officialServers": to_int(totals.get("diceServerAmount")),
            },
            "topMaps": pick_top_stats(all_region.get("mapPlayers", {})),
            "topModes": pick_top_stats(all_region.get("modePlayers", {})),
            "regions": normalized_regions,
        }
        dashboard_cache.set("overview", result)
        return result

    async def check_bfban_persona_ids(
        self,
        session: aiohttp.ClientSession,
        persona_ids: list[str],
        platform: str,
    ) -> dict[str, dict[str, Any]]:
        normalized_ids = [clean_text(item) for item in persona_ids if clean_text(item)]
        if not normalized_ids:
            return {}

        results: dict[str, dict[str, Any]] = {}
        pending_payload: list[dict[str, Any]] = []

        for persona_id in dict.fromkeys(normalized_ids):
            cache_key = f"{platform}:{persona_id}"
            cached = bfban_cache.get(cache_key)
            if cached is not None:
                results[persona_id] = cached
                continue

            pending_payload.append({"platform": platform, "personaId": persona_id})

        if pending_payload:
            payload = await self._request_json(session, "POST", "/bfban/checkban/", payload=pending_payload)
            if not isinstance(payload, list):
                payload = []

            for item in payload:
                if not isinstance(item, dict):
                    continue

                persona_id = str(item.get("personaId") or item.get("originPersonaId") or "")
                if not persona_id:
                    continue

                normalized = normalize_bfban_entry(item)
                results[persona_id] = normalized
                bfban_cache.set(f"{platform}:{persona_id}", normalized)

        for persona_id in normalized_ids:
            if persona_id not in results:
                results[persona_id] = dict(DEFAULT_BFBAN_STATE)
                bfban_cache.set(f"{platform}:{persona_id}", dict(DEFAULT_BFBAN_STATE))

        return results

    async def fetch_player_bundle(self, query: str, platform: str) -> dict[str, Any]:
        async with self.create_session() as session:
            lookups = [self._player_lookup(query, platform)]
            if query.isdigit():
                lookups.append(
                    {
                        "name": query,
                        "platform": platform,
                        "lang": self.settings.default_lang,
                    }
                )

            stats_raw = weapons_raw = vehicles_raw = classes_raw = None
            last_error: ApiError | None = None
            for lookup in lookups:
                try:
                    candidate_stats, candidate_weapons, candidate_vehicles, candidate_classes = await self._fetch_player_payloads(
                        session,
                        lookup,
                    )
                except ApiError as exc:
                    last_error = exc
                    continue

                stats_raw = candidate_stats
                weapons_raw = candidate_weapons
                vehicles_raw = candidate_vehicles
                classes_raw = candidate_classes

                if isinstance(candidate_stats, dict) and not candidate_stats.get("errors"):
                    break

            if not isinstance(stats_raw, dict):
                if last_error:
                    raise last_error
                raise ApiError("没有找到该玩家的数据。", 404)

            if stats_raw.get("errors"):
                raise ApiError("；".join(str(item) for item in stats_raw["errors"]), 404)

            persona_id = clean_text(stats_raw.get("id"))
            bfban_lookup = await self.check_bfban_persona_ids(session, [persona_id], platform) if persona_id else {}

        weapons = sorted_records(
            [normalize_weapon(item) for item in (weapons_raw or {}).get("weapons", []) if isinstance(item, dict)],
            "kills",
            "timeHours",
        )
        vehicles = sorted_records(
            [normalize_vehicle(item) for item in (vehicles_raw or {}).get("vehicles", []) if isinstance(item, dict)],
            "kills",
            "timeHours",
        )
        classes = sorted_records(
            [normalize_class(item) for item in (classes_raw or {}).get("classes", []) if isinstance(item, dict)],
            "score",
            "kills",
        )

        name = stats_raw.get("userName") or query
        result = {
            "query": query,
            "platform": platform,
            "updatedAt": current_timestamp(),
            "profile": {
                "name": name,
                "avatar": stats_raw.get("avatar") or "",
                "rank": to_int(stats_raw.get("rank")),
                "personaId": persona_id,
                "userId": clean_text(stats_raw.get("userId")),
                "bestClass": stats_raw.get("bestClass") or "未知",
                "timePlayed": stats_raw.get("timePlayed") or "0:00:00",
                "kd": format_decimal(stats_raw.get("killDeath")),
                "kpm": format_decimal(stats_raw.get("killsPerMinute")),
                "spm": format_decimal(stats_raw.get("scorePerMinute")),
                "accuracy": safe_percentage(stats_raw.get("accuracy")),
                "headshots": safe_percentage(stats_raw.get("headshots")),
                "wins": to_int(stats_raw.get("wins")),
                "losses": to_int(stats_raw.get("loses")),
                "kills": to_int(stats_raw.get("kills")),
                "deaths": to_int(stats_raw.get("deaths")),
                "revives": to_int(stats_raw.get("revives")),
                "killAssists": to_int(stats_raw.get("killAssists")),
                "longestHeadShot": format_decimal(stats_raw.get("longestHeadShot"), 1),
                "highestKillStreak": to_int(stats_raw.get("highestKillStreak")),
                "roundsPlayed": to_int(stats_raw.get("roundsPlayed")),
            },
            "highlights": [
                {"label": "击杀", "value": to_int(stats_raw.get("kills"))},
                {"label": "死亡", "value": to_int(stats_raw.get("deaths"))},
                {"label": "K/D", "value": format_decimal(stats_raw.get("killDeath"))},
                {"label": "KPM", "value": format_decimal(stats_raw.get("killsPerMinute"))},
                {"label": "SPM", "value": format_decimal(stats_raw.get("scorePerMinute"))},
                {"label": "胜率", "value": safe_percentage(stats_raw.get("winPercent"))},
                {"label": "命中率", "value": safe_percentage(stats_raw.get("accuracy"))},
                {"label": "爆头率", "value": safe_percentage(stats_raw.get("headshots"))},
            ],
            "bfban": bfban_lookup.get(persona_id, dict(DEFAULT_BFBAN_STATE)),
            "weapons": weapons,
            "vehicles": vehicles,
            "classes": classes,
            "topWeapons": top_records(weapons, 8, "kills", "timeHours"),
            "topVehicles": top_records(vehicles, 6, "kills", "timeHours"),
            "topClasses": top_records(classes, 4, "score", "kills"),
        }
        return result

    async def search_servers(self, query: str, platform: str, region: str, limit: int) -> dict[str, Any]:
        params = {
            "name": query,
            "platform": platform,
            "limit": limit,
            "lang": self.settings.default_lang,
        }
        if region != "all":
            params["region"] = region

        async with self.create_session() as session:
            payload = await self._request_json(session, "GET", "/bfv/servers/", params=params)

        servers_raw = payload.get("servers", []) if isinstance(payload, dict) else []
        servers = sorted_records([normalize_server(item) for item in servers_raw if isinstance(item, dict)], "players", "queue")
        return {
            "query": query,
            "platform": platform,
            "region": region,
            "limit": limit,
            "updatedAt": current_timestamp(),
            "servers": servers,
        }

    async def fetch_server_players(self, game_id: str, platform: str) -> dict[str, Any]:
        async with self.create_session() as session:
            payload = await self._request_json(
                session,
                "GET",
                "/bfv/players/",
                params={"gameid": game_id},
            )

            if not isinstance(payload, dict) or "serverinfo" not in payload:
                raise ApiError("没有获取到服务器玩家列表。", 404)

            teams_raw = payload.get("teams", []) if isinstance(payload.get("teams"), list) else []
            queue_raw = payload.get("que", []) if isinstance(payload.get("que"), list) else []
            loading_raw = payload.get("loading", []) if isinstance(payload.get("loading"), list) else []

            persona_ids = []
            for bucket in (*teams_raw, {"players": queue_raw}, {"players": loading_raw}):
                for player in bucket.get("players", []):
                    persona_id = clean_text(player.get("player_id"))
                    if persona_id:
                        persona_ids.append(persona_id)

            bfban_lookup = await self.check_bfban_persona_ids(session, persona_ids, platform)

        teams = []
        for index, team in enumerate(teams_raw, start=1):
            players = [
                normalize_server_player(player, bfban_lookup.get(clean_text(player.get("player_id"))))
                for player in team.get("players", [])
                if isinstance(player, dict)
            ]
            players = sorted(players, key=lambda item: item["rank"], reverse=True)
            teams.append(
                {
                    "name": team.get("name") or f"队伍 {index}",
                    "teamId": team.get("teamid") or str(index),
                    "players": players,
                }
            )

        queue = [
            normalize_server_player(player, bfban_lookup.get(clean_text(player.get("player_id"))))
            for player in queue_raw
            if isinstance(player, dict)
        ]
        loading = [
            normalize_server_player(player, bfban_lookup.get(clean_text(player.get("player_id"))))
            for player in loading_raw
            if isinstance(player, dict)
        ]

        total_players = sum(len(team["players"]) for team in teams)
        server_info = payload.get("serverinfo", {})
        return {
            "updatedAt": current_timestamp(),
            "platform": platform,
            "server": {
                "name": server_info.get("name") or "服务器",
                "description": server_info.get("description") or "",
                "region": server_info.get("region") or "",
                "country": server_info.get("country") or "",
                "mode": server_info.get("mode") or "",
                "map": server_info.get("level") or "",
                "serverType": server_info.get("servertype") or "",
            },
            "summary": {
                "players": total_players,
                "queue": len(queue),
                "loading": len(loading),
                "teams": len(teams),
            },
            "teams": teams,
            "queue": queue,
            "loading": loading,
        }


client = GametoolsClient(SETTINGS)


def api_success(data: Any, status_code: int = 200):
    return jsonify({"success": True, "data": data}), status_code


def api_error(message: str, status_code: int = 400):
    return jsonify({"success": False, "message": message}), status_code


def run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def validate_platform(platform: str) -> str:
    normalized = clean_text(platform) or SETTINGS.default_platform
    if normalized not in PLATFORM_OPTIONS:
        raise ApiError("平台参数无效，请选择 PC、Xbox One 或 PS4。", 400)
    return normalized


def validate_region(region: str) -> str:
    normalized = clean_text(region) or "all"
    if normalized not in REGION_OPTIONS:
        raise ApiError("地区参数无效。", 400)
    return normalized


def validate_limit(value: Any) -> int:
    limit = to_int(value, SETTINGS.default_server_limit)
    if limit <= 0:
        limit = SETTINGS.default_server_limit
    return min(limit, SETTINGS.max_server_limit)


@app.errorhandler(ApiError)
def handle_api_error(error: ApiError):
    return api_error(error.message, error.status_code)


@app.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    app.logger.exception("Unexpected error: %s", error)
    return api_error("服务发生未预期错误，请稍后再试。", 500)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/api/overview", methods=["GET"])
def api_overview():
    return api_success(run_async(client.fetch_overview()))


@app.route("/api/bfv-stats", methods=["GET"])
def api_bfv_stats():
    overview = run_async(client.fetch_overview())
    totals = overview.get("totals", {})
    return api_success(
        {
            "server_count": totals.get("servers", 0),
            "total_players": totals.get("players", 0),
        }
    )


@app.route("/api/player", methods=["POST"])
def api_player():
    payload = request.get_json(silent=True) or {}
    query = clean_text(payload.get("query") or payload.get("username"))
    if not query:
        raise ApiError("请输入玩家名或 personaId。", 400)

    platform = validate_platform(payload.get("platform", SETTINGS.default_platform))
    return api_success(run_async(client.fetch_player_bundle(query, platform)))


@app.route("/api/server", methods=["POST"])
@app.route("/api/servers", methods=["POST"])
def api_servers():
    payload = request.get_json(silent=True) or {}
    query = clean_text(payload.get("query") or payload.get("servername"))
    if not query:
        raise ApiError("请输入服务器名称。", 400)

    platform = validate_platform(payload.get("platform", SETTINGS.default_platform))
    region = validate_region(payload.get("region", "all"))
    limit = validate_limit(payload.get("limit"))
    return api_success(run_async(client.search_servers(query, platform, region, limit)))


@app.route("/api/server-players", methods=["GET"])
def api_server_players():
    game_id = clean_text(request.args.get("gameId"))
    if not game_id:
        raise ApiError("缺少 gameId 参数。", 400)

    platform = validate_platform(request.args.get("platform", SETTINGS.default_platform))
    return api_success(run_async(client.fetch_server_players(game_id, platform)))


@app.route("/api/player-bfban", methods=["GET"])
def api_player_bfban():
    persona_id = clean_text(request.args.get("personaId"))
    if not persona_id:
        raise ApiError("缺少 personaId 参数。", 400)

    platform = validate_platform(request.args.get("platform", SETTINGS.default_platform))

    async def fetch_single_bfban() -> dict[str, Any]:
        async with client.create_session() as session:
            mapping = await client.check_bfban_persona_ids(session, [persona_id], platform)
            return mapping.get(persona_id, dict(DEFAULT_BFBAN_STATE))

    return api_success(run_async(fetch_single_bfban()))


if __name__ == "__main__":
    app.run(debug=SETTINGS.debug, host=SETTINGS.host, port=SETTINGS.port)
