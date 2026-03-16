from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent
DB_NAME = BASE_DIR / 'work_time.db'


@contextmanager
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
    finally:
        conn.close()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    return {row['name'] for row in rows}


def init_db() -> None:
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                username TEXT,
                role TEXT NOT NULL DEFAULT 'employee' CHECK (role IN ('employee', 'admin')),
                hourly_rate REAL NOT NULL DEFAULT 0 CHECK (hourly_rate >= 0),
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            '''
        )

        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS work_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                worked_seconds INTEGER NOT NULL DEFAULT 0 CHECK (worked_seconds >= 0),
                hourly_rate_snapshot REAL NOT NULL DEFAULT 0 CHECK (hourly_rate_snapshot >= 0),
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            '''
        )

        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_telegram_id INTEGER NOT NULL,
                target_telegram_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            )
            '''
        )

        user_columns = _table_columns(conn, 'users')
        if 'created_at' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        if 'updated_at' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")

        session_columns = _table_columns(conn, 'work_sessions')
        if 'hourly_rate_snapshot' not in session_columns:
            cursor.execute('ALTER TABLE work_sessions ADD COLUMN hourly_rate_snapshot REAL NOT NULL DEFAULT 0')
        if 'created_at' not in session_columns:
            cursor.execute("ALTER TABLE work_sessions ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        if 'updated_at' not in session_columns:
            cursor.execute("ALTER TABLE work_sessions ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")

        now = utc_now().isoformat()
        cursor.execute(
            "UPDATE users SET created_at = COALESCE(NULLIF(created_at, ''), ?), updated_at = COALESCE(NULLIF(updated_at, ''), ?) WHERE created_at = '' OR updated_at = ''",
            (now, now),
        )
        cursor.execute(
            "UPDATE work_sessions SET created_at = COALESCE(NULLIF(created_at, ''), start_time), updated_at = COALESCE(NULLIF(updated_at, ''), COALESCE(end_time, start_time)) WHERE created_at = '' OR updated_at = ''"
        )
        cursor.execute(
            '''
            UPDATE work_sessions
            SET hourly_rate_snapshot = COALESCE(NULLIF(hourly_rate_snapshot, 0), (
                SELECT COALESCE(u.hourly_rate, 0)
                FROM users u
                WHERE u.id = work_sessions.user_id
            ))
            WHERE hourly_rate_snapshot = 0
            '''
        )

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users (telegram_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON work_sessions (user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON work_sessions (start_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_open ON work_sessions (user_id, end_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log (target_telegram_id, created_at)')
        conn.commit()


def log_admin_action(actor_telegram_id: int, action: str, target_telegram_id: Optional[int] = None, details: str = '') -> None:
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO audit_log (actor_telegram_id, target_telegram_id, action, details, created_at) VALUES (?, ?, ?, ?, ?)',
            (actor_telegram_id, target_telegram_id, action, details, utc_now().isoformat()),
        )
        conn.commit()


def add_or_update_user(telegram_id: int, full_name: str, username: Optional[str], is_admin: bool = False) -> None:
    now = utc_now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, role FROM users WHERE telegram_id = ?', (telegram_id,))
        existing_user = cursor.fetchone()

        if existing_user:
            role_sql = ", role = 'admin'" if is_admin and existing_user['role'] != 'admin' else ''
            cursor.execute(
                f'''UPDATE users SET full_name = ?, username = ?, updated_at = ?{role_sql} WHERE telegram_id = ?''',
                (full_name, username, now, telegram_id),
            )
        else:
            role = 'admin' if is_admin else 'employee'
            cursor.execute(
                '''
                INSERT INTO users (telegram_id, full_name, username, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (telegram_id, full_name, username, role, now, now),
            )
        conn.commit()


def get_user_by_telegram_id(telegram_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)).fetchone()


def set_hourly_rate(telegram_id: int, hourly_rate: float, actor_telegram_id: Optional[int] = None) -> bool:
    if hourly_rate < 0:
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT hourly_rate FROM users WHERE telegram_id = ?', (telegram_id,))
        current = cursor.fetchone()
        if not current:
            return False
        cursor.execute(
            'UPDATE users SET hourly_rate = ?, updated_at = ? WHERE telegram_id = ?',
            (hourly_rate, utc_now().isoformat(), telegram_id),
        )
        conn.commit()
    if actor_telegram_id is not None:
        log_admin_action(actor_telegram_id, 'set_hourly_rate', telegram_id, f'{current[0]} -> {hourly_rate}')
    return True


def set_role(telegram_id: int, role: str, actor_telegram_id: Optional[int] = None) -> bool:
    if role not in {'employee', 'admin'}:
        return False
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (telegram_id,))
        current = cursor.fetchone()
        if not current:
            return False
        cursor.execute(
            'UPDATE users SET role = ?, updated_at = ? WHERE telegram_id = ?',
            (role, utc_now().isoformat(), telegram_id),
        )
        conn.commit()
    if actor_telegram_id is not None:
        log_admin_action(actor_telegram_id, 'set_role', telegram_id, f'{current[0]} -> {role}')
    return True


def get_open_session(user_id: int) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            '''
            SELECT * FROM work_sessions
            WHERE user_id = ? AND end_time IS NULL
            ORDER BY id DESC LIMIT 1
            ''',
            (user_id,),
        ).fetchone()


def start_work_session(user_id: int, hourly_rate_snapshot: float) -> bool:
    now = utc_now().isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('BEGIN IMMEDIATE')
        open_session = cursor.execute(
            'SELECT id FROM work_sessions WHERE user_id = ? AND end_time IS NULL ORDER BY id DESC LIMIT 1',
            (user_id,),
        ).fetchone()
        if open_session:
            conn.rollback()
            return False
        cursor.execute(
            '''
            INSERT INTO work_sessions (user_id, start_time, hourly_rate_snapshot, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (user_id, now, hourly_rate_snapshot, now, now),
        )
        conn.commit()
        return True


def end_work_session(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('BEGIN IMMEDIATE')
        open_session = cursor.execute(
            '''
            SELECT * FROM work_sessions
            WHERE user_id = ? AND end_time IS NULL
            ORDER BY id DESC LIMIT 1
            ''',
            (user_id,),
        ).fetchone()
        if not open_session:
            conn.rollback()
            return None

        start_time = datetime.fromisoformat(open_session['start_time'])
        end_time = utc_now()
        worked_seconds = max(0, int((end_time - start_time).total_seconds()))
        amount = round((worked_seconds / 3600) * float(open_session['hourly_rate_snapshot'] or 0), 2)

        cursor.execute(
            '''
            UPDATE work_sessions
            SET end_time = ?, worked_seconds = ?, updated_at = ?
            WHERE id = ?
            ''',
            (end_time.isoformat(), worked_seconds, end_time.isoformat(), open_session['id']),
        )
        conn.commit()

        return {
            'worked_seconds': worked_seconds,
            'start_time': open_session['start_time'],
            'end_time': end_time.isoformat(),
            'hourly_rate_snapshot': float(open_session['hourly_rate_snapshot'] or 0),
            'amount': amount,
        }


def format_seconds(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f'{hours} ч {minutes} мин'


def get_current_session_status(telegram_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            '''
            SELECT ws.*, u.full_name, u.telegram_id
            FROM work_sessions ws
            JOIN users u ON u.id = ws.user_id
            WHERE u.telegram_id = ? AND ws.end_time IS NULL
            ORDER BY ws.id DESC LIMIT 1
            ''',
            (telegram_id,),
        ).fetchone()
    if not row:
        return None
    start_time = datetime.fromisoformat(row['start_time'])
    worked_seconds = max(0, int((utc_now() - start_time).total_seconds()))
    amount = round((worked_seconds / 3600) * float(row['hourly_rate_snapshot'] or 0), 2)
    return {
        'start_time': row['start_time'],
        'worked_seconds': worked_seconds,
        'formatted_time': format_seconds(worked_seconds),
        'hourly_rate_snapshot': float(row['hourly_rate_snapshot'] or 0),
        'amount': amount,
    }


def _stats_row_to_dict(row: sqlite3.Row, *, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    total_seconds = int(row['total_seconds'] or 0)
    total_amount = round(float(row['total_amount'] or 0), 2)
    payload = {
        'full_name': row['full_name'],
        'hourly_rate': float(row['hourly_rate'] or 0),
        'total_sessions': int(row['total_sessions'] or 0),
        'total_seconds': total_seconds,
        'formatted_time': format_seconds(total_seconds),
        'total_amount': total_amount,
    }
    if start_date is not None:
        payload['start_date'] = start_date
    if end_date is not None:
        payload['end_date'] = end_date
    return payload


def get_user_stats(telegram_id: int) -> Dict[str, Any]:
    with get_connection() as conn:
        result = conn.execute(
            '''
            SELECT
                u.full_name,
                u.hourly_rate,
                COUNT(ws.id) AS total_sessions,
                COALESCE(SUM(ws.worked_seconds), 0) AS total_seconds,
                COALESCE(SUM((ws.worked_seconds / 3600.0) * ws.hourly_rate_snapshot), 0) AS total_amount
            FROM users u
            LEFT JOIN work_sessions ws ON u.id = ws.user_id AND ws.end_time IS NOT NULL
            WHERE u.telegram_id = ?
            GROUP BY u.id
            ''',
            (telegram_id,),
        ).fetchone()
    return _stats_row_to_dict(result) if result else {}


def get_user_stats_by_period(telegram_id: int, start_date: str, end_date: str) -> Dict[str, Any]:
    start_dt = f'{start_date}T00:00:00+00:00'
    end_dt = f'{end_date}T23:59:59+00:00'
    with get_connection() as conn:
        result = conn.execute(
            '''
            SELECT
                u.full_name,
                u.hourly_rate,
                COUNT(ws.id) AS total_sessions,
                COALESCE(SUM(ws.worked_seconds), 0) AS total_seconds,
                COALESCE(SUM((ws.worked_seconds / 3600.0) * ws.hourly_rate_snapshot), 0) AS total_amount
            FROM users u
            LEFT JOIN work_sessions ws
                ON u.id = ws.user_id
                AND ws.end_time IS NOT NULL
                AND ws.start_time BETWEEN ? AND ?
            WHERE u.telegram_id = ?
            GROUP BY u.id
            ''',
            (start_dt, end_dt, telegram_id),
        ).fetchone()
    return _stats_row_to_dict(result, start_date=start_date, end_date=end_date) if result else {}


def get_admin_daily_stats() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            '''
            SELECT
                date(ws.start_time) AS work_day,
                u.full_name,
                COUNT(ws.id) AS sessions_count,
                COALESCE(SUM(ws.worked_seconds), 0) AS total_seconds,
                COALESCE(SUM((ws.worked_seconds / 3600.0) * ws.hourly_rate_snapshot), 0) AS total_amount
            FROM work_sessions ws
            JOIN users u ON ws.user_id = u.id
            WHERE ws.end_time IS NOT NULL
            GROUP BY date(ws.start_time), u.full_name
            ORDER BY work_day DESC, u.full_name
            '''
        ).fetchall()


def get_admin_all_workers_stats() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            '''
            SELECT
                u.full_name,
                u.telegram_id,
                u.role,
                u.hourly_rate,
                COUNT(ws.id) AS sessions_count,
                COALESCE(SUM(ws.worked_seconds), 0) AS total_seconds,
                COALESCE(SUM((ws.worked_seconds / 3600.0) * ws.hourly_rate_snapshot), 0) AS total_amount
            FROM users u
            LEFT JOIN work_sessions ws ON u.id = ws.user_id AND ws.end_time IS NOT NULL
            GROUP BY u.id
            ORDER BY u.full_name
            '''
        ).fetchall()


def get_active_workers() -> List[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            '''
            SELECT
                u.full_name,
                u.telegram_id,
                ws.start_time,
                ws.hourly_rate_snapshot
            FROM work_sessions ws
            JOIN users u ON u.id = ws.user_id
            WHERE ws.end_time IS NULL
            ORDER BY ws.start_time ASC
            '''
        ).fetchall()
