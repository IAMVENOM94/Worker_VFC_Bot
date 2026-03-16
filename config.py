from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.split(','):
        value = item.strip()
        if value.isdigit():
            result.add(int(value))
    return result


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    timezone_name: str
    debug: bool

    @property
    def timezone(self):
        try:
            return ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError:
            return timezone.utc


BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
if not BOT_TOKEN:
    raise ValueError('Не найден BOT_TOKEN. Создай .env на основе .env.example')

SETTINGS = Settings(
    bot_token=BOT_TOKEN,
    admin_ids=_parse_admin_ids(os.getenv('ADMIN_IDS', '')),
    timezone_name=os.getenv('TIMEZONE', 'Europe/Moscow').strip() or 'Europe/Moscow',
    debug=os.getenv('DEBUG', 'false').strip().lower() in {'1', 'true', 'yes', 'on'},
)

ADMIN_IDS = SETTINGS.admin_ids
TIMEZONE = SETTINGS.timezone
