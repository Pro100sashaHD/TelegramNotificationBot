import sqlite3
from datetime import datetime, timezone
import os

from config import cipher

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_database.db")

def get_connection():
    """Помощник для создания безопасного соединения с таймаутом."""
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,          -- ID
            reminder_minutes INTEGER DEFAULT 15,  -- За сколько минут уведомлять
            google_token TEXT DEFAULT NULL        -- JSON с токенами
        )
    """)

    # 2. Таблица отправленных напоминаний
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_reminders (
            user_id INTEGER,
            event_id TEXT,                        
            sent_at TEXT,                        
            PRIMARY KEY (user_id, event_id)
        )
    """)

    # 3. Таблица истории прошедших встреч
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meeting_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_title TEXT,
            start_time TEXT,
            end_time TEXT
        )
    """)

    conn.commit()
    conn.close()


def add_user(user_id: int):
    """Добавляет нового пользователя, если его еще нет в базе."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def update_reminder_time(user_id: int, minutes: int):
    """Обновляет время напоминания для конкретного пользователя."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET reminder_minutes = ? WHERE user_id = ?", (minutes, user_id))
    conn.commit()
    conn.close()


def save_google_token(user_id: int, token_json: str):
    """Сохраняет OAuth токен пользователя."""
    conn = get_connection()
    cursor = conn.cursor()
    encrypted_token = cipher.encrypt(token_json.encode())
    cursor.execute("UPDATE users SET google_token = ? WHERE user_id = ?", (encrypted_token, user_id))
    conn.commit()
    conn.close()


def get_user_settings(user_id: int):
    """Возвращает настройки пользователя (минуты, токен)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT reminder_minutes, google_token FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[1]:
        try:
            decrypted_token = cipher.decrypt(result[1]).decode()
            return (result[0], decrypted_token)
        except Exception as e:
            return (result[0], None)

    return result

def get_all_users_with_tokens():
    """Возвращает ID и токены всех пользователей, прошедших авторизацию."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, google_token FROM users WHERE google_token IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

    decrypted_rows = []
    for user_id, encrypted_token in rows:
        try:
            decrypted_token = cipher.decrypt(encrypted_token).decode()
            decrypted_rows.append((user_id, decrypted_token))
        except Exception as e:
            return

    return decrypted_rows


def is_reminder_sent(user_id: int, event_id: str) -> bool:
    """Проверяет, отправлялось ли уже напоминание для этого события."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM sent_reminders WHERE user_id = ? AND event_id = ?",
        (user_id, event_id)
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_reminder_as_sent(user_id: int, event_id: str):
    """Фиксирует факт отправки напоминания в базе данных."""
    conn = get_connection()
    cursor = conn.cursor()
    current_time = datetime.now().isoformat()
    cursor.execute(
        "INSERT OR IGNORE INTO sent_reminders (user_id, event_id, sent_at) VALUES (?, ?, ?)",
        (user_id, event_id, current_time)
    )
    conn.commit()
    conn.close()

def add_to_meeting_history(user_id: int, title: str, start_time: str, end_time: str):
    """Добавляет прошедшее или наступившее событие в историю встреч."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO meeting_history (user_id, event_title, start_time, end_time)
        VALUES (?, ?, ?, ?)
    """, (user_id, title, start_time, end_time))
    conn.commit()
    conn.close()


def get_user_history(user_id: int, limit: int = 10) -> list:
    """
    Возвращает последние N встреч из истории пользователя.
    Каждый элемент списка — это кортеж (event_title, start_time).
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
            SELECT event_title, start_time, end_time 
            FROM meeting_history 
            WHERE user_id = ? 
            ORDER BY id DESC
            LIMIT 50
        """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    now = datetime.now(timezone.utc)

    filtered_history = []
    for title, start_time, end_time in rows:
        if end_time and 'T' in end_time:
            try:
                end_dt = datetime.fromisoformat(end_time)
                if end_dt < now:
                    filtered_history.append((title, start_time))
            except Exception:
                filtered_history.append((title, start_time))
        else:
            continue

        if len(filtered_history) == limit:
            break

    return filtered_history