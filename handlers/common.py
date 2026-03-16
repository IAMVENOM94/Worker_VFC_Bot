from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import ADMIN_IDS
from database import add_or_update_user, get_user_by_telegram_id
from keyboards import get_main_keyboard

router = Router(name='common')


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    telegram_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username
    is_admin = message.from_user.id in ADMIN_IDS

    add_or_update_user(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username,
        is_admin=is_admin,
    )

    user = get_user_by_telegram_id(telegram_id)
    role_title = 'Администратор' if user['role'] == 'admin' else 'Сотрудник'
    text = (
        f'Привет, {full_name}!\n\n'
        'Это бот учёта рабочего времени.\n'
        f'Ваша роль: {role_title}\n'
        f'Текущая ставка в час: {user["hourly_rate"]}'
    )
    await message.answer(text, reply_markup=get_main_keyboard(is_admin=user['role'] == 'admin'))


@router.message(Command('myid'))
async def cmd_my_id(message: Message) -> None:
    await message.answer(f'Ваш Telegram ID: {message.from_user.id}')
