from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import TIMEZONE
from database import (
    end_work_session,
    format_seconds,
    get_current_session_status,
    get_user_by_telegram_id,
    get_user_stats,
    get_user_stats_by_period,
    start_work_session,
)
from keyboards import get_cancel_keyboard, get_main_keyboard
from states import PeriodState

router = Router(name='employee')


def format_local(iso_dt: str) -> str:
    dt = datetime.fromisoformat(iso_dt).astimezone(TIMEZONE)
    return dt.strftime('%d.%m.%Y %H:%M:%S')


@router.message(F.text == 'Начало работы')
async def start_work(message: Message) -> None:
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer('Сначала нажми /start')
        return

    success = start_work_session(user['id'], float(user['hourly_rate'] or 0))
    if success:
        now_str = datetime.now(TIMEZONE).strftime('%d.%m.%Y %H:%M:%S')
        await message.answer(
            f'Рабочая смена начата.\nВремя начала: {now_str}\nСтавка зафиксирована: {user["hourly_rate"]}'
        )
    else:
        await message.answer('У вас уже есть активная смена. Сначала завершите её.')


@router.message(F.text == 'Конец работы')
async def finish_work(message: Message) -> None:
    user = get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer('Сначала нажми /start')
        return

    result = end_work_session(user['id'])
    if result is None:
        await message.answer('У вас нет активной смены.')
        return

    await message.answer(
        'Рабочая смена завершена.\n'
        f'Время начала: {format_local(result["start_time"])}\n'
        f'Время окончания: {format_local(result["end_time"])}\n'
        f'Отработано: {format_seconds(result["worked_seconds"])}\n'
        f'Ставка: {result["hourly_rate_snapshot"]}\n'
        f'Сумма за смену: {result["amount"]}'
    )


@router.message(F.text == 'Моя смена')
async def my_current_shift(message: Message) -> None:
    status = get_current_session_status(message.from_user.id)
    if not status:
        await message.answer('Сейчас активной смены нет.')
        return

    await message.answer(
        'Текущая смена:\n'
        f'Начало: {format_local(status["start_time"])}\n'
        f'Длительность: {status["formatted_time"]}\n'
        f'Ставка: {status["hourly_rate_snapshot"]}\n'
        f'Текущая сумма: {status["amount"]}'
    )


@router.message(F.text == 'Моя статистика')
async def my_stats(message: Message) -> None:
    stats = get_user_stats(message.from_user.id)
    if not stats:
        await message.answer('Статистика не найдена.')
        return

    await message.answer(
        'Ваша статистика:\n\n'
        f'Сотрудник: {stats["full_name"]}\n'
        f'Количество смен: {stats["total_sessions"]}\n'
        f'Всего времени: {stats["formatted_time"]}\n'
        f'Текущая ставка в час: {stats["hourly_rate"]}\n'
        f'Общая сумма: {stats["total_amount"]}'
    )


@router.message(F.text == 'Подсчёт за период')
async def period_help(message: Message, state: FSMContext) -> None:
    await state.set_state(PeriodState.waiting_for_period)
    await message.answer(
        'Отправьте период в формате:\n2026-03-01 2026-03-31\n\n'
        'То есть: дата_начала дата_конца',
        reply_markup=get_cancel_keyboard(),
    )


@router.message(PeriodState.waiting_for_period, F.text == 'Отмена')
async def cancel_period(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = get_user_by_telegram_id(message.from_user.id)
    await message.answer('Действие отменено.', reply_markup=get_main_keyboard(is_admin=bool(user and user['role'] == 'admin')))


@router.message(PeriodState.waiting_for_period)
async def calculate_period_stats(message: Message, state: FSMContext) -> None:
    try:
        start_date, end_date = message.text.strip().split()
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
        if start_date > end_date:
            raise ValueError('start_date > end_date')
    except Exception:
        await message.answer('Ошибка формата. Пример:\n2026-03-01 2026-03-31')
        return

    stats = get_user_stats_by_period(message.from_user.id, start_date, end_date)
    await state.clear()
    user = get_user_by_telegram_id(message.from_user.id)

    if not stats:
        await message.answer(
            'Не удалось получить статистику за период.',
            reply_markup=get_main_keyboard(is_admin=bool(user and user['role'] == 'admin')),
        )
        return

    await message.answer(
        'Статистика за период:\n\n'
        f'Сотрудник: {stats["full_name"]}\n'
        f'Период: {stats["start_date"]} — {stats["end_date"]}\n'
        f'Количество смен: {stats["total_sessions"]}\n'
        f'Всего времени: {stats["formatted_time"]}\n'
        f'Текущая ставка в час: {stats["hourly_rate"]}\n'
        f'Сумма: {stats["total_amount"]}',
        reply_markup=get_main_keyboard(is_admin=bool(user and user['role'] == 'admin')),
    )
