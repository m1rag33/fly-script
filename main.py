#!/usr/bin/env python3
"""Мониторинг цен авиабилетов Минск/Москва → Анталья через Travelpayouts API."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
API_URL = "https://api.travelpayouts.com/v2/prices/month-matrix"
REQUEST_PAUSE_SECONDS = 1.0


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Не найден файл настроек: {CONFIG_PATH}")
    config = load_json(CONFIG_PATH, {})
    required = (
        "travelpayouts_token",
        "routes",
        "months",
        "max_price",
        "currency",
        "telegram_token",
        "telegram_chat_id",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"В config.json отсутствуют поля: {', '.join(missing)}")
    return config


def month_param(month: str) -> str:
    """Преобразует YYYY-MM в YYYY-MM-01, как требует month-matrix."""
    if len(month) == 7:
        return f"{month}-01"
    return month


def aviasales_date_part(date_str: str) -> str:
    """2027-04-28 → 2804"""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d%m")


def aviasales_search_url(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None,
    one_way: bool,
) -> str:
    """Ссылка на поиск Aviasales: /search/MOW2804CTU11051"""
    depart_part = aviasales_date_part(depart_date)
    passengers = "1"
    if not one_way and return_date:
        return_part = aviasales_date_part(return_date)
        return f"https://www.aviasales.ru/search/{origin}{depart_part}{destination}{return_part}{passengers}"
    return f"https://www.aviasales.ru/search/{origin}{depart_part}{destination}{passengers}"


def fetch_prices(
    token: str,
    origin: str,
    destination: str,
    month: str,
    currency: str,
    one_way: bool,
    trip_duration: int,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "month": month_param(month),
        "currency": currency,
        "one_way": str(one_way).lower(),
        "token": token,
        "sorting": "price",
        "limit": 1000,
    }
    if not one_way:
        params["trip_duration"] = trip_duration

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"API вернул ошибку: {payload}")
    data = payload.get("data") or []
    if isinstance(data, dict):
        return list(data.values())
    return data


def filter_deals(
    prices: list[dict[str, Any]],
    max_price: float,
    direct_only: bool,
) -> list[dict[str, Any]]:
    deals = []
    for item in prices:
        if item.get("value") is None or float(item["value"]) > max_price:
            continue
        if direct_only:
            try:
                changes = int(item.get("number_of_changes", -1))
            except (TypeError, ValueError):
                continue
            if changes != 0:
                continue
        deals.append(item)
    deals.sort(key=lambda item: float(item["value"]))
    return deals


def deal_key(origin: str, destination: str, item: dict[str, Any]) -> str:
    depart = item.get("depart_date", "")
    return_date = item.get("return_date") or "oneway"
    changes = item.get("number_of_changes", "x")
    return f"{origin}-{destination}-{depart}-{return_date}-{changes}"


def format_changes(number_of_changes: Any) -> str:
    try:
        n = int(number_of_changes)
    except (TypeError, ValueError):
        return "пересадки неизвестны"
    if n == 0:
        return "прямой"
    if n == 1:
        return "1 пересадка"
    if n in (2, 3, 4):
        return f"{n} пересадки"
    return f"{n} пересадок"


def format_deal_message(
    origin: str,
    destination: str,
    item: dict[str, Any],
    currency: str,
    one_way: bool,
) -> str:
    price = int(float(item["value"]))
    depart = item.get("depart_date", "?")
    return_date = item.get("return_date")
    changes = format_changes(item.get("number_of_changes"))
    url = aviasales_search_url(origin, destination, depart, return_date, one_way)
    currency_label = currency.upper()

    lines = [
        f"Нашёл билет {origin} → {destination}",
        f"Вылет: {depart}",
    ]
    if return_date and not one_way:
        lines.append(f"Обратно: {return_date}")
    lines.append(f"Цена: {price} {currency_label}")
    lines.append(f"Маршрут: {changes}")
    lines.append(url)
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API ошибка: {payload}")


def placeholders_filled(config: dict[str, Any]) -> bool:
    token = str(config.get("travelpayouts_token", ""))
    tg_token = str(config.get("telegram_token", ""))
    chat_id = str(config.get("telegram_chat_id", ""))
    return not (
        token.startswith("YOUR_")
        or tg_token.startswith("YOUR_")
        or chat_id.startswith("YOUR_")
    )


def run_cycle(config: dict[str, Any], state: dict[str, float], notify: bool) -> dict[str, float]:
    token = config["travelpayouts_token"]
    currency = config["currency"]
    max_price = float(config["max_price"])
    one_way = bool(config.get("one_way", True))
    direct_only = bool(config.get("direct_only", False))
    trip_duration = int(config.get("trip_duration", 7))
    routes = config["routes"]
    months = config["months"]

    found_total = 0
    notified = 0

    for route in routes:
        origin = route["origin"]
        destination = route["destination"]
        for month in months:
            try:
                prices = fetch_prices(
                    token=token,
                    origin=origin,
                    destination=destination,
                    month=month,
                    currency=currency,
                    one_way=one_way,
                    trip_duration=trip_duration,
                )
            except requests.RequestException as exc:
                log(f"Ошибка сети {origin}->{destination} {month}: {exc}")
                time.sleep(REQUEST_PAUSE_SECONDS)
                continue
            except Exception as exc:
                log(f"Ошибка API {origin}->{destination} {month}: {exc}")
                time.sleep(REQUEST_PAUSE_SECONDS)
                continue

            deals = filter_deals(prices, max_price, direct_only)
            extra = ", только прямые" if direct_only else ""
            log(
                f"{origin}->{destination} {month}: "
                f"всего {len(prices)} предложений, ниже {int(max_price)}{extra} — {len(deals)}"
            )

            for item in deals:
                found_total += 1
                key = deal_key(origin, destination, item)
                price = float(item["value"])
                previous = state.get(key)
                if previous is not None and price >= previous:
                    continue

                message = format_deal_message(origin, destination, item, currency, one_way)
                if notify:
                    try:
                        send_telegram(config["telegram_token"], str(config["telegram_chat_id"]), message)
                        notified += 1
                        log(f"Уведомление: {key} {int(price)} {currency.upper()}")
                    except Exception as exc:
                        log(f"Не удалось отправить в Telegram ({key}): {exc}")
                        continue
                else:
                    log(f"[dry-run] {message.replace(chr(10), ' | ')}")

                state[key] = price

            time.sleep(REQUEST_PAUSE_SECONDS)

    log(f"Цикл завершён. Подходящих: {found_total}, новых уведомлений: {notified}")
    return state


def main() -> int:
    configure_stdio()
    once = "--once" in sys.argv
    dry_run = "--dry-run" in sys.argv

    try:
        config = load_config()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        log(f"Не удалось прочитать config.json: {exc}")
        return 1

    if not dry_run and not placeholders_filled(config):
        log(
            "Заполните travelpayouts_token, telegram_token и telegram_chat_id в config.json. "
            "Или запустите с --dry-run для проверки без Telegram."
        )
        return 1

    notify = not dry_run
    interval_minutes = int(config.get("check_interval_minutes", 60))
    state = load_json(STATE_PATH, {})
    if not isinstance(state, dict):
        state = {}

    log(
        f"Старт мониторинга. Маршруты: {len(config['routes'])}, "
        f"месяцы: {', '.join(config['months'])}, порог: {config['max_price']} "
        f"{str(config['currency']).upper()}"
        f"{', только прямые' if config.get('direct_only') else ''}, "
        f"интервал: {interval_minutes} мин."
    )

    while True:
        state = run_cycle(config, state, notify=notify)
        save_json(STATE_PATH, state)
        if once or dry_run:
            break
        log(f"Следующая проверка через {interval_minutes} мин.")
        time.sleep(interval_minutes * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
