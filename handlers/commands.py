import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.state import StatesGroup, State

import database.db as db
import services.google_cal as google_cal
from config import logger

router = Router()


class AuthStates(StatesGroup):
    waiting_for_code = State()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    db.add_user(user_id)
    logger.info(f"Пользователь {user_id} запустил бота.")

    try:
        auth_url = google_cal.get_authorization_url(user_id)
        text = (
            f"Привет, {message.from_user.full_name}! 👋\n\n"
            f"Я бот-уведомитель для твоего Google Календаря.\n"
            f"Для начала работы мне нужен доступ к событиям.\n\n"
            f"1. Перейди по этой ссылке для авторизации:\n🔗 {auth_url}\n\n"
            f"2. Войди в свой аккаунт, разреши доступ и **скопируй код авторизации**.\n"
            f"3. Отправь скопированный код мне в ответном сообщении."
        )
        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка генерации ссылки авторизации для {user_id}: {e}")
        await message.answer("Произошла ошибка при подготовке авторизации. Попробуйте позже.")


@router.message(Command("set_reminder"))
async def cmd_set_reminder(message: Message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2 or not args[1].isdigit():
        await message.answer(
            "❌ Использование команды: `/set_reminder <минуты>`\nПример: `/set_reminder 15`")
        return

    minutes = int(args[1])
    db.update_reminder_time(user_id, minutes)
    logger.info(f"Пользователь {user_id} изменил время напоминания на {minutes} мин.")
    await message.answer(
        f"🔔 Время напоминания успешно изменено! Я отправлю уведомление за {minutes} минут до начала встречи.")


@router.message(Command("history"))
async def cmd_history(message: Message):
    user_id = message.from_user.id
    history = db.get_user_history(user_id, limit=5)


    if not history:
        await message.answer("📜 Ваша история встреч пока пуста.")
        return

    text = "📜 **Последние 10 встреч:**\n\n"

    for idx, (title, start_time) in enumerate(history, start=1):
        display_time = start_time

        if start_time and 'T' in start_time:
            try:
                dt = datetime.datetime.fromisoformat(start_time)
                display_time = dt.strftime('%d.%m.%Y %H:%M')
            except Exception:
                pass

        text += f"{idx}. [{display_time}] {title}\n"

    await message.answer(text, parse_mode="Markdown")


@router.message(F.text)
async def handle_auth_code(message: Message):
    user_id = message.from_user.id
    code = message.text.strip()

    settings = db.get_user_settings(user_id)
    if not settings:
        db.add_user(user_id)
        settings = (15, None)

    try:
        if len(code) > 20 and "-" in code or len(code) > 15:
            await message.answer("🔄 Проверяю код авторизации и генерирую токен...")

            token_json = google_cal.build_credentials_from_code(code)
            db.save_google_token(user_id, token_json)

            logger.info(f"Пользователь {user_id} успешно прошел OAuth авторизацию.")
            await message.answer(
                "✅ Авторизация прошла успешно! Теперь я отслеживаю твой Google Календарь. [cite: 4, 5]")
        else:
            await message.answer(
                "🤔 Не похоже на корректный код авторизации Google. Скопируй его целиком из окна браузера.")
    except Exception as e:
        logger.error(f"Ошибка авторизации по коду для пользователя {user_id}: {e}")
        await message.answer(
            "❌ Ошибка авторизации. Возможно, код устарел или введен неверно. Попробуй вызвать /start заново. ")