from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from config import TIMEZONE
from database import (
    format_seconds,
    get_active_workers,
    get_admin_all_workers_stats,
    get_admin_daily_stats,
    get_user_by_telegram_id,
    set_hourly_rate,
    set_role,
)

router = Router(name='admin')


def _is_admin(message: Message) -> bool:
    user = get_user_by_telegram_id(message.from_user.id)
    return bool(user and user['role'] == 'admin')


def _format_local(iso_dt: str) -> str:
    return datetime.fromisoformat(iso_dt).astimezone(TIMEZONE).strftime('%d.%m.%Y %H:%M:%S')


@router.message(F.text == 'Статистика сотрудников')
async def admin_workers_stats(message: Message) -> None:
    if not _is_admin(message):
        await message.answer('У вас нет доступа к этой функции.')
        return

    stats = get_admin_all_workers_stats()
    if not stats:
        await message.answer('Нет данных.')
        return

    lines = ['Статистика сотрудников:\n']
    for row in stats:
        lines.append(
            f'{row["full_name"]}\n'
            f'ID: {row["telegram_id"]}\n'
            f'Роль: {row["role"]}\n'
            f'Смен: {row["sessions_count"]}\n'
            f'Время: {format_seconds(int(row["total_seconds"] or 0))}\n'
            f'Текущая ставка: {row["hourly_rate"]}\n'
            f'Сумма: {round(float(row["total_amount"] or 0), 2)}\n'
        )

    text = '\n'.join(lines)
    for i in range(0, len(text), 4000):
        await message.answer(text[i:i + 4000])


@router.message(F.text == 'Статистика по дням')
async def admin_daily_stats(message: Message) -> None:
    if not _is_admin(message):
        await message.answer('У вас нет доступа к этой функции.')
        return

    stats = get_admin_daily_stats()
    if not stats:
        await message.answer('Нет данных.')
        return

    lines = ['Статистика по дням:\n']
    for row in stats:
        lines.append(
            f'Дата: {row["work_day"]}\n'
            f'Сотрудник: {row["full_name"]}\n'
            f'Смен: {row["sessions_count"]}\n'
            f'Время: {format_seconds(int(row["total_seconds"] or 0))}\n'
            f'Сумма: {round(float(row["total_amount"] or 0), 2)}\n'
        )

    text = '\n'.join(lines)
    for i in range(0, len(text), 4000):
        await message.answer(text[i:i + 4000])


@router.message(F.text == 'Кто сейчас работает')
async def active_workers(message: Message) -> None:
    if not _is_admin(message):
        await message.answer('У вас нет доступа к этой функции.')
        return

    rows = get_active_workers()
    if not rows:
        await message.answer('Сейчас нет активных смен.')
        return

    lines = ['Сейчас на смене:\n']
    now = datetime.now(TIMEZONE)
    for row in rows:
        start_dt = datetime.fromisoformat(row['start_time']).astimezone(TIMEZONE)
        seconds = max(0, int((now - start_dt).total_seconds()))
        amount = round((seconds / 3600) * float(row['hourly_rate_snapshot'] or 0), 2)
        lines.append(
            f'{row["full_name"]} (ID: {row["telegram_id"]})\n'
            f'Начало: {_format_local(row["start_time"])}\n'
            f'В работе: {format_seconds(seconds)}\n'
            f'Сумма сейчас: {amount}\n'
        )
    await message.answer('\n'.join(lines))


@router.message(Command('setrate'))
async def cmd_set_rate(message: Message) -> None:
    if not _is_admin(message):
        await message.answer('У вас нет доступа к этой команде.')
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer('Использование:\n/setrate TELEGRAM_ID СТАВКА\nПример:\n/setrate 123456789 500')
        return

    try:
        telegram_id = int(parts[1])
        rate = float(parts[2])
        if rate < 0:
            raise ValueError
    except ValueError:
        await message.answer('Ошибка в данных. Проверь ID и ставку.')
        return

    success = set_hourly_rate(telegram_id, rate, actor_telegram_id=message.from_user.id)
    await message.answer(
        f'Ставка {rate} успешно установлена для пользователя {telegram_id}' if success else 'Пользователь не найден.'
    )


@router.message(Command('setrole'))
async def cmd_set_role(message: Message) -> None:
    if not _is_admin(message):
        await message.answer('У вас нет доступа к этой команде.')
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer('Использование:\n/setrole TELEGRAM_ID employee/admin')
        return

    try:
        telegram_id = int(parts[1])
        role = parts[2].strip().lower()
    except ValueError:
        await message.answer('Ошибка в данных.')
        return

    success = set_role(telegram_id, role, actor_telegram_id=message.from_user.id)
    await message.answer(
        f'Роль {role} установлена для пользователя {telegram_id}' if success else 'Не удалось изменить роль.'
    )
