import sqlite3
from datetime import datetime, timedelta

def get_db_connection():
    conn = sqlite3.connect('system.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """ایجاد دیتابیس و جداول"""
    conn = get_db_connection()
    
    # جدول تنظیمات
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # جدول کاربران قفل شده
    conn.execute('''
        CREATE TABLE IF NOT EXISTS locked_users (
            username TEXT PRIMARY KEY,
            attempts INTEGER DEFAULT 0,
            locked_until DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول پروژه‌ها
    conn.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY,
            identifier TEXT,
            name TEXT,
            description TEXT,
            status TEXT,
            active BOOLEAN,
            public BOOLEAN,
            percentage_done REAL,
            start_date TEXT,
            due_date TEXT,
            created_at TEXT,
            updated_at TEXT,
            parent_id INTEGER,
            parent_name TEXT,
            custom_fields TEXT,
            sync_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # تنظیمات پیش‌فرض
    default_settings = {
        'system_name': 'سامانه مدیریت پروژه‌های کاربان',
        'header_color': '#0d6efd',
        'header_text_color': '#ffffff',
        'background_color': '#f8f9fa',
        'login_width': '380',
        'login_position_x': '50',
        'login_position_y': '50',
        'max_login_attempts': '3',
        'lockout_time': '30',
        'flash_timeout': '3'
    }
    
    for key, value in default_settings.items():
        conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    conn.commit()
    conn.close()
    print("✅ دیتابیس سیستم ایجاد شد")

def get_setting(key, default=None):
    """دریافت تنظیم از دیتابیس"""
    conn = get_db_connection()
    result = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return result['value'] if result else default

def save_setting(key, value):
    """ذخیره تنظیم در دیتابیس"""
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_all_settings():
    """دریافت تمام تنظیمات"""
    conn = get_db_connection()
    settings = conn.execute('SELECT * FROM settings').fetchall()
    conn.close()
    return {setting['key']: setting['value'] for setting in settings}

def check_user_lock(username):
    """بررسی قفل بودن کاربر"""
    conn = get_db_connection()
    user = conn.execute(
        'SELECT * FROM locked_users WHERE username = ?', (username,)
    ).fetchone()
    conn.close()
    
    if user:
        locked_until = datetime.fromisoformat(user['locked_until']) if user['locked_until'] else None
        if locked_until and datetime.now() < locked_until:
            return True, locked_until
    return False, None

def increment_login_attempt(username):
    """افزایش تعداد تلاش‌های ناموفق"""
    conn = get_db_connection()
    
    max_attempts = int(get_setting('max_login_attempts', 3))
    lockout_time = int(get_setting('lockout_time', 30))
    
    user = conn.execute(
        'SELECT * FROM locked_users WHERE username = ?', (username,)
    ).fetchone()
    
    if user:
        new_attempts = user['attempts'] + 1
        if new_attempts >= max_attempts:
            locked_until = datetime.now() + timedelta(minutes=lockout_time)
            conn.execute(
                'UPDATE locked_users SET attempts = ?, locked_until = ? WHERE username = ?',
                (new_attempts, locked_until.isoformat(), username)
            )
        else:
            conn.execute(
                'UPDATE locked_users SET attempts = ? WHERE username = ?',
                (new_attempts, username)
            )
    else:
        conn.execute(
            'INSERT INTO locked_users (username, attempts) VALUES (?, 1)',
            (username,)
        )
    
    conn.commit()
    conn.close()

def reset_login_attempts(username):
    """ریست کردن تلاش‌های ناموفق"""
    conn = get_db_connection()
    conn.execute('DELETE FROM locked_users WHERE username = ?', (username,))
    conn.commit()
    conn.close()
