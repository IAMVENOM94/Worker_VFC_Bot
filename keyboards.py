from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text='Начало работы'), KeyboardButton(text='Конец работы')],
        [KeyboardButton(text='Моя смена'), KeyboardButton(text='Моя статистика')],
        [KeyboardButton(text='Подсчёт за период')],
    ]

    if is_admin:
        buttons.extend([
            [KeyboardButton(text='Кто сейчас работает')],
            [KeyboardButton(text='Статистика сотрудников')],
            [KeyboardButton(text='Статистика по дням')],
        ])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='Отмена')]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
