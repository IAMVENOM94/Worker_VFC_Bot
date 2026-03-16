from aiogram import Router
from aiogram.types import Message

router = Router(name="fallback")


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer("Не понял команду. Используй кнопки меню или /start")
