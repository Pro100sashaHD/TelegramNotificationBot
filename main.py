import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.client.session.aiohttp import AiohttpSession

from config import TELEGRAM_TOKEN, logger
from database.db import init_db
from handlers.commands import router as commands_router
from services.scheduler import start_scheduler


async def main():
    logger.info("Инициализация базы данных...")
    init_db()

    proxy_url = os.getenv("BOT_PROXY")

    if proxy_url:
        logger.info(f"Запуск бота через прокси-сервер: {proxy_url}")
        session = AiohttpSession(proxy=proxy_url)
        bot = Bot(token=TELEGRAM_TOKEN, session=session)
    else:
        logger.info("Запуск бота напрямую (без прокси).")
        bot = Bot(token=TELEGRAM_TOKEN)

    dp = Dispatcher()
    dp.include_router(commands_router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота и авторизоваться"),
        BotCommand(command="set_reminder", description="Изменить время уведомлений (например: /set_reminder 5)"),
        BotCommand(command="history", description="Показать последние 10 встреч")
    ])
    logger.info("Кнопка меню команд успешно настроена.")

    start_scheduler(bot)

    logger.info("Запуск Telegram-бота...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка при работе бота: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот успешно остановлен.")