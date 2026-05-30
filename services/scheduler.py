import json
import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import logger
from database.db import get_all_users_with_tokens, is_reminder_sent, mark_reminder_as_sent, get_user_settings, save_google_token


async def check_google_calendars(bot: Bot):
    """Фоновая задача: проверяет календари пользователей с учетом их личных настроек времени."""
    logger.info("Фоновый планировщик: запуск сканирования календарей...")

    users = get_all_users_with_tokens()

    if not users:
        logger.debug("Фоновый планировщик: нет авторизованных пользователей.")
        return

    for user_id, token_json in users:
        try:
            settings = get_user_settings(user_id)
            if settings:
                reminder_minutes = settings[0]
            else:
                reminder_minutes = 5

            now = datetime.datetime.now(datetime.timezone.utc)

            time_min = now
            time_max = now + datetime.timedelta(minutes=int(reminder_minutes) + 2)

            now_iso = time_min.isoformat().replace('+00:00', 'Z')
            time_max_iso = time_max.isoformat().replace('+00:00', 'Z')

            token_data = json.loads(token_json)
            credentials = Credentials(
                token=token_data.get('token'),
                refresh_token=token_data.get('refresh_token'),
                token_uri=token_data.get('token_uri'),
                client_id=token_data.get('client_id'),
                client_secret=token_data.get('client_secret'),
                scopes=token_data.get('scopes')
            )

            service = build('calendar', 'v3', credentials=credentials)

            events_result = service.events().list(
                calendarId='primary',
                timeMin=now_iso,
                timeMax=time_max_iso,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            if credentials.valid and credentials.token:
                updated_token_data = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                updated_token_json = json.dumps(updated_token_data)

                if token_json != updated_token_json:
                    save_google_token(user_id, updated_token_json)

            events = events_result.get('items', [])

            for event in events:
                event_id = event.get('id')

                if is_reminder_sent(user_id, event_id):
                    continue

                summary = event.get('summary', 'Без названия')
                start_time_raw = event['start'].get('dateTime', event['start'].get('date'))
                end_time_raw = event['end'].get('dateTime', event['end'].get('date', start_time_raw))

                display_time = start_time_raw
                if 'T' in start_time_raw:
                    try:
                        dt = datetime.datetime.fromisoformat(start_time_raw)
                        display_time = dt.strftime('%d-%m-%Y %H:%M')
                    except Exception:
                        pass

                message_text = (
                    f"⏰ **Напоминание о событии!**\n\n"
                    f"📌 **Событие:** {summary}\n"
                    f"📅 **Время начала:** {display_time}"
                )

                await bot.send_message(chat_id=user_id, text=message_text, parse_mode="Markdown")

                from database.db import add_to_meeting_history
                add_to_meeting_history(
                    user_id=user_id,
                    title=summary,
                    start_time=start_time_raw,
                    end_time=end_time_raw
                )

                mark_reminder_as_sent(user_id, event_id)
                logger.info(f"Уведомление по событию '{summary}' отправлено пользователю {user_id}")



        except Exception as e:
            logger.error(f"Ошибка при проверке календаря для пользователя {user_id}: {e}")


def start_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_google_calendars,
        trigger="interval",
        seconds=60,
        args=[bot]
    )
    scheduler.start()
    logger.info("Фоновый планировщик APScheduler успешно запущен.")