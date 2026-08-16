# Скрипт поиска билетов

Мониторинг цен Aviasales по заданным маршрутам и месяцам. Если цена не выше порога — приходит уведомление в Telegram.

Цены берутся из официального [Travelpayouts Data API](https://api.travelpayouts.com/documentation) (кэш поисков Aviasales за последние 1–2 дня). Это не парсинг сайта.

По умолчанию смотрит **Минск / Москва → Анталья**, но маршруты, месяцы и порог цены задаются в `config.json`.

## Возможности

- Несколько маршрутов и месяцев в одном цикле
- Поиск в одну сторону или туда-обратно
- Фильтр только прямых рейсов
- Уведомление в Telegram со ссылкой на поиск Aviasales
- Без спама: повторно пишет только если цена стала ниже

## Что нужно

- Python 3.10+
- Бесплатный токен [Travelpayouts](https://www.travelpayouts.com/) — после регистрации: **Профиль → API-ключ**
- Telegram-бот через [@BotFather](https://t.me/BotFather) и свой `chat_id` (например через [@userinfobot](https://t.me/userinfobot))

Проект создавать не нужно. После регистрации скопируйте токен и при необходимости подключите программу Aviasales.

## Установка

```bash
git clone https://github.com/m1rag33/fly-script.git
cd fly-script
python -m pip install -r requirements.txt
cp config.example.json config.json
```

На Windows вместо `cp`:

```powershell
copy config.example.json config.json
```

Заполните в `config.json` токены и параметры поиска.

## Настройки

| Поле | Пример | Описание |
| --- | --- | --- |
| `travelpayouts_token` | токен из кабинета | API-ключ Travelpayouts |
| `telegram_token` | токен от BotFather | токен бота |
| `telegram_chat_id` | `123456789` | ваш чат |
| `routes` | `MSQ → AYT`, `MOW → AYT` | маршруты (IATA городов) |
| `months` | `["2027-05"]` | месяцы вылета (`YYYY-MM`) |
| `max_price` | `30000` | максимальная цена |
| `currency` | `rub` | `rub`, `usd` или `byn` |
| `one_way` | `false` | `true` — в одну сторону, `false` — туда-обратно |
| `direct_only` | `true` | `true` — только без пересадок |
| `trip_duration` | `13` | длительность поездки в днях (если `one_way: false`) |
| `check_interval_minutes` | `60` | пауза между проверками |

`config.json` в репозиторий не коммитится — там лежат токены.

## Запуск

Постоянный мониторинг:

```bash
python main.py
```

Один цикл и выход:

```bash
python main.py --once
```

Проверка без Telegram (уведомления только в консоль):

```bash
python main.py --dry-run
```

`--dry-run` всегда делает один цикл и завершается. Остановка постоянного режима: `Ctrl+C`.

Чтобы скрипт работал в фоне, можно повесить в Планировщик Windows задачу `python main.py --once` раз в час.

## Как это устроено

Каждый цикл скрипт запрашивает календарь цен `v2/prices/month-matrix` для каждой пары маршрут × месяц, отбирает билеты не дороже `max_price` и при необходимости только прямые. Состояние хранится в `state.json`: если по этой дате уже отправляли ту же или более высокую цену, повторное сообщение не уйдёт.
