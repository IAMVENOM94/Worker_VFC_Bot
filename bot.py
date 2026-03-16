from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from config import BOT_TOKEN, SETTINGS
from database import init_db
from handlers.admin import router as admin_router
from handlers.common import router as common_router
from handlers.employee import router as employee_router
from handlers.fallback import router as fallback_router


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if SETTINGS.debug else logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    )


async def on_error(event: ErrorEvent) -> bool:
    logging.exception('Необработанная ошибка: %s', event.exception)
    if event.update and event.update.message:
        await event.update.message.answer('Произошла ошибка. Попробуйте ещё раз чуть позже.')
    return True


async def main() -> None:
    setup_logging()
    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(common_router)
    dp.include_router(employee_router)
    dp.include_router(admin_router)
    dp.include_router(fallback_router)
    dp.errors.register(on_error)

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
