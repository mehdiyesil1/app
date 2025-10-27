from flask import Flask, session, redirect, request, flash, render_template, url_for, send_from_directory, jsonify, Response
import os
import jdatetime
import requests
import secrets
import urllib3
import urllib.parse
import sqlite3
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from PIL import Image
import io
import json
import csv
import re

# غیرفعال کردن هشدارهای SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'my-super-secret-key-12345-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# تنظیمات آپلود فایل
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

# ایجاد پوشه آپلود اگر وجود ندارد
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'avatars'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'logo'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'background'), exist_ok=True)

# تنظیمات کاربان
OP_BASE_URL = 'http://karban.jaboun.network'
CLIENT_ID = 'UlsOOwE8Tun_CIFPRCoP3aLsVWyI1RRmzmBlTRbdClk'
CLIENT_SECRET = 'QosufrY3lq3_Ypd7T5Yn7al7kjUNlQs-qGiRA4_ZwuU'
REDIRECT_URI = 'http://localhost:5000/'

# ==================== توابع کمکی ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, folder):
    """ذخیره فایل آپلود شده با نام تصادفی"""
    if file and allowed_file(file.filename):
        # ایجاد نام فایل منحصر به فرد
        file_ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{secrets.token_hex(8)}.{file_ext}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], folder, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        file.save(file_path)
        
        # بهینه‌سازی سایز عکس برای آواتار
        if folder == 'avatars':
            optimize_image_size(file_path, max_size=(150, 150))
        
        return f'uploads/{folder}/{filename}'
    return None

def optimize_image_size(image_path, max_size=(150, 150)):
    """بهینه‌سازی سایز عکس برای آواتار"""
    try:
        with Image.open(image_path) as img:
            # تبدیل به RGB اگر لازم باشد
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # ذخیره با کیفیت مناسب
            img.save(image_path, optimize=True, quality=85)
            print(f"✅ تصویر آواتار بهینه‌سازی شد: {image_path}")
    except Exception as e:
        print(f"⚠️ Error optimizing image: {str(e)}")

def get_persian_datetime():
    """دریافت تاریخ و زمان شمسی"""
    now = datetime.now()
    jalali_date = jdatetime.datetime.fromgregorian(datetime=now)
    return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d} - {jalali_date.hour:02d}:{jalali_date.minute:02d}"

def clean_html_description(html_text):
    """پاکسازی HTML از توضیحات"""
    if not html_text:
        return ""
    # حذف تگ‌های HTML
    clean_text = re.sub('<[^<]+?>', '', html_text)
    # حذف فضاهای اضافی
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    return clean_text

def extract_custom_fields(project_data):
    """استخراج فیلدهای سفارشی از داده‌های پروژه"""
    custom_fields = {}
    try:
        project_id = project_data.get('id')
        
        # استخراج از کلیدهای مستقیم customFieldX
        for key in project_data.keys():
            if key.startswith('customField'):
                value = project_data[key]
                
                if isinstance(value, dict):
                    if 'title' in value and value['title']:
                        custom_fields[key] = value['title']
                    elif 'name' in value and value['name']:
                        custom_fields[key] = value['name']
                    elif '_links' in value and 'title' in value.get('_links', {}).get('self', {}):
                        custom_fields[key] = value['_links']['self']['title']
                    else:
                        custom_fields[key] = str(value)
                else:
                    custom_fields[key] = value

        # استخراج از _links
        if '_links' in project_data:
            for link_key, link_value in project_data['_links'].items():
                if link_key.startswith('customField'):
                    if isinstance(link_value, dict) and 'title' in link_value:
                        custom_fields[link_key] = link_value['title']
                    elif link_value:
                        custom_fields[link_key] = str(link_value)
        
        # استخراج از _embedded/customFields
        if '_embedded' in project_data and 'customFields' in project_data['_embedded']:
            for field in project_data['_embedded']['customFields']:
                field_id = field.get('id')
                field_name = f"customField{field_id}"
                field_value = field.get('value')
                
                if field_name not in custom_fields and field_value is not None:
                    if isinstance(field_value, dict):
                        if 'title' in field_value and field_value['title']:
                            custom_fields[field_name] = field_value['title']
                        elif 'name' in field_value and field_value['name']:
                            custom_fields[field_name] = field_value['name']
                        else:
                            custom_fields[field_name] = str(field_value)
                    else:
                        custom_fields[field_name] = field_value
        
        # اضافه کردن status از _embedded
        if '_embedded' in project_data:
            embedded = project_data['_embedded']
            if 'status' in embedded and embedded['status']:
                project_data['status'] = embedded['status'].get('id', '')

    except Exception as e:
        print(f"⚠️ خطا در استخراج فیلدهای سفارشی: {str(e)}")

    return custom_fields

def get_custom_field_value(project, field_name):
    """دریافت مقدار فیلد سفارشی"""
    try:
        if field_name.isdigit():
            field_key = f"customField{field_name}"
        else:
            field_mapping = {
                'کد پروژه': '1',
                'سطح ولتاژ': '16', 
                'نوع تابلو': '21',
                'تعداد تابلو': '4',
                'تعداد سلول': '5',
                'دپارتمان': '20',
                'مسئول تیم': '18', 
                'تیم': '17',
                'تاریخ لیست تجهیزات': '8',
                'پروژه فوری': '10'
            }
            field_key = f"customField{field_mapping.get(field_name, field_name)}"
        
        # جستجو مستقیم در پروژه
        if field_key in project:
            value = project[field_key]
            
            if isinstance(value, list):
                titles = []
                for item in value:
                    if isinstance(item, dict) and 'title' in item and item['title']:
                        titles.append(item['title'])
                    elif isinstance(item, dict) and 'name' in item and item['name']:
                        titles.append(item['name'])
                    elif item and item != 'None' and item != 'null' and item != '':
                        titles.append(str(item))
                
                if titles:
                    return ', '.join(titles)
                return ''
            
            elif isinstance(value, dict):
                if 'title' in value and value['title']:
                    return str(value['title'])
                elif 'name' in value and value['name']:
                    return str(value['name'])
                elif 'value' in value and value['value']:
                    return str(value['value'])
                elif '_links' in value and 'title' in value.get('_links', {}).get('self', {}):
                    return str(value['_links']['self']['title'])
                else:
                    return str(value)
            elif value and value != 'None' and value != 'null' and value != '':
                return str(value)
            return ''
        
        # جستجو در custom_fields استخراج شده
        custom_fields = project.get('custom_fields', {})
        if field_key in custom_fields:
            value = custom_fields[field_key]
            if value and value != 'None' and value != 'null' and value != '':
                return str(value)
        
        return ''
        
    except Exception as e:
        print(f"⚠️ خطا در دریافت فیلد {field_name}: {str(e)}")
        return ''

def convert_to_jalali(gregorian_date):
    """تبدیل تاریخ میلادی به شمسی"""
    try:
        if not gregorian_date:
            return '---'
        
        if isinstance(gregorian_date, str):
            gregorian_date = gregorian_date.strip()
            
            if 'T' in gregorian_date:
                date_part = gregorian_date.split('T')[0]
            elif ' ' in gregorian_date:
                date_part = gregorian_date.split(' ')[0]
            else:
                date_part = gregorian_date
            
            parts = date_part.split('-')
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                
                jalali_date = jdatetime.date.fromgregorian(year=year, month=month, day=day)
                return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d}"
        
        return '---'
    except Exception as e:
        print(f"⚠️ خطا در تبدیل تاریخ {gregorian_date}: {str(e)}")
        return '---'

def format_sync_date(datetime_str):
    """فرمت‌دهی تاریخ همگام‌سازی"""
    try:
        if not datetime_str:
            return 'نامشخص'
        
        if 'T' in datetime_str:
            datetime_str = datetime_str.split('.')[0]
            dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
        
        jalali_date = jdatetime.date.fromgregorian(year=dt.year, month=dt.month, day=dt.day)
        return f"{jalali_date.year}/{jalali_date.month:02d}/{jalali_date.day:02d}"
    
    except Exception as e:
        print(f"⚠️ خطا در فرمت تاریخ همگام‌سازی {datetime_str}: {str(e)}")
        return 'نامشخص'

def get_user_access_level(user_data):
    """دریافت سطح دسترسی کاربر"""
    try:
        # بررسی وضعیت مدیر بودن از OpenProject
        is_admin = user_data.get('admin', False)
        
        # بررسی نقش کاربری از فیلدهای سفارشی
        user_role = get_user_custom_field_value(user_data, 'نقش کاربری')
        
        if is_admin:
            return 'مدیر سیستم'
        elif user_role:
            return user_role
        else:
            return 'کاربر عادی'
            
    except Exception as e:
        print(f"⚠️ خطا در دریافت سطح دسترسی کاربر: {str(e)}")
        return 'کاربر عادی'

def extract_user_custom_fields(user_data):
    """استخراج فیلدهای سفارشی از داده‌های کاربر - مشابه تابع پروژه‌ها"""
    custom_fields = {}
    try:
        user_id = user_data.get('id')
        
        # استخراج از کلیدهای مستقیم customFieldX
        for key in user_data.keys():
            if key.startswith('customField'):
                value = user_data[key]
                
                if isinstance(value, dict):
                    if 'title' in value and value['title']:
                        custom_fields[key] = value['title']
                    elif 'name' in value and value['name']:
                        custom_fields[key] = value['name']
                    elif '_links' in value and 'title' in value.get('_links', {}).get('self', {}):
                        custom_fields[key] = value['_links']['self']['title']
                    else:
                        custom_fields[key] = str(value)
                else:
                    custom_fields[key] = value

        # استخراج از _links
        if '_links' in user_data:
            for link_key, link_value in user_data['_links'].items():
                if link_key.startswith('customField'):
                    if isinstance(link_value, dict) and 'title' in link_value:
                        custom_fields[link_key] = link_value['title']
                    elif link_value:
                        custom_fields[link_key] = str(link_value)
        
        # استخراج از _embedded/customFields
        if '_embedded' in user_data and 'customFields' in user_data['_embedded']:
            for field in user_data['_embedded']['customFields']:
                field_id = field.get('id')
                field_name = f"customField{field_id}"
                field_value = field.get('value')
                
                if field_name not in custom_fields and field_value is not None:
                    if isinstance(field_value, dict):
                        if 'title' in field_value and field_value['title']:
                            custom_fields[field_name] = field_value['title']
                        elif 'name' in field_value and field_value['name']:
                            custom_fields[field_name] = field_value['name']
                        else:
                            custom_fields[field_name] = str(field_value)
                    else:
                        custom_fields[field_name] = field_value

        print(f"✅ {len(custom_fields)} فیلد سفارشی کاربر استخراج شد")

    except Exception as e:
        print(f"⚠️ خطا در استخراج فیلدهای سفارشی کاربر: {str(e)}")

    return custom_fields

def get_user_custom_field_value(user_data, field_name):
    """دریافت مقدار فیلد سفارشی کاربر - مشابه تابع پروژه‌ها"""
    try:
        if field_name.isdigit():
            field_key = f"customField{field_name}"
        else:
            # مپینگ نام فیلدها به شناسه‌های آنها
            field_mapping = {
                'دپارتمان': '22',
                'نقش کاربری': '23',
                'department': '22',
                'user_role': '23',
                'تیم': '28',
                'team': '28',
                'موقعیت سازمانی': '18',
                'organizational_position': '18'
            }
            field_key = f"customField{field_mapping.get(field_name, field_name)}"
        
        # جستجو مستقیم در داده کاربر
        if field_key in user_data:
            value = user_data[field_key]
            
            if isinstance(value, list):
                titles = []
                for item in value:
                    if isinstance(item, dict) and 'title' in item and item['title']:
                        titles.append(item['title'])
                    elif isinstance(item, dict) and 'name' in item and item['name']:
                        titles.append(item['name'])
                    elif item and item != 'None' and item != 'null' and item != '':
                        titles.append(str(item))
                
                if titles:
                    return ', '.join(titles)
                return ''
            
            elif isinstance(value, dict):
                if 'title' in value and value['title']:
                    return str(value['title'])
                elif 'name' in value and value['name']:
                    return str(value['name'])
                elif 'value' in value and value['value']:
                    return str(value['value'])
                elif '_links' in value and 'title' in value.get('_links', {}).get('self', {}):
                    return str(value['_links']['self']['title'])
                else:
                    return str(value)
            elif value and value != 'None' and value != 'null' and value != '':
                return str(value)
            return ''
        
        # جستجو در custom_fields استخراج شده
        custom_fields = user_data.get('custom_fields', {})
        if field_key in custom_fields:
            value = custom_fields[field_key]
            if value and value != 'None' and value != 'null' and value != '':
                return str(value)
        
        return ''
        
    except Exception as e:
        print(f"⚠️ خطا در دریافت فیلد کاربر {field_name}: {str(e)}")
        return ''

def get_user_display_avatar(user_id):
    """دریافت آواتار نمایشی کاربر (اولویت با آواتار آپلود شده)"""
    # اولویت اول: آواتار آپلود شده توسط کاربر
    uploaded_avatar = get_user_avatar(user_id)
    if uploaded_avatar:
        return uploaded_avatar
    
    # اولویت دوم: آواتار از کش کاربران
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT uc.user_data 
            FROM users_cache uc 
            WHERE uc.user_id = ?
        ''', (user_id,)).fetchone()
        
        if result:
            user_data = json.loads(result['user_data'])
            if user_data.get('avatar'):
                return user_data['avatar']
    except Exception as e:
        print(f"⚠️ خطا در دریافت آواتار از کش: {str(e)}")
    finally:
        conn.close()
    
    return None

def get_complete_user_profile(access_token, user_id):
    """دریافت اطلاعات کامل پروفایل کاربر از کاربان"""
    try:
        user_url = f"{OP_BASE_URL}/api/v3/users/{user_id}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        user_response = requests.get(user_url, headers=headers, verify=False)
        
        if user_response.status_code == 200:
            user_data = user_response.json()
            
            # استخراج فیلدهای سفارشی
            custom_fields = extract_user_custom_fields(user_data)
            
            # ایجاد اطلاعات پروفایل
            profile_info = {
                'id': user_data.get('id'),
                'login': user_data.get('login', ''),
                'name': user_data.get('name', ''),
                'email': user_data.get('email', ''),
                'status': user_data.get('status', 'active'),
                'admin': user_data.get('admin', False),
                'firstname': user_data.get('firstName', ''),
                'lastname': user_data.get('lastName', ''),
                'position': 'عضو',
                'custom_fields': custom_fields,
                'access_level': get_user_access_level(user_data)
            }
            
            # اگر کاربر admin است، position را تغییر دهید
            if profile_info['admin']:
                profile_info['position'] = 'مدیر سیستم'
            
            # دریافت مقادیر فیلدهای خاص از فیلدهای سفارشی
            department = get_user_custom_field_value({'custom_fields': custom_fields}, 'دپارتمان')
            if department and department != 'فناوری اطلاعات':
                profile_info['department'] = department
            else:
                profile_info['department'] = ''
            
            user_role = get_user_custom_field_value({'custom_fields': custom_fields}, 'نقش کاربری')
            if user_role:
                profile_info['user_role_custom'] = user_role
            else:
                profile_info['user_role_custom'] = ''
            
            team = get_user_custom_field_value({'custom_fields': custom_fields}, 'تیم')
            if team:
                profile_info['team'] = team
            else:
                profile_info['team'] = ''
            
            # اولویت‌بندی آواتار: ابتدا آواتار آپلود شده، سپس آواتار کاربان
            uploaded_avatar = get_user_avatar(user_id)
            if uploaded_avatar:
                # استفاده از آواتار آپلود شده توسط کاربر
                profile_info['avatar'] = uploaded_avatar
                profile_info['avatar_source'] = 'آپلود شده'
                print(f"✅ از آواتار آپلود شده کاربر {user_id} استفاده شد")
            else:
                # دریافت آواتار از کاربان
                try:
                    avatar_url = f"{OP_BASE_URL}/users/{user_id}/avatar"
                    avatar_response = requests.get(avatar_url, headers=headers, verify=False, allow_redirects=True)
                    
                    if avatar_response.status_code == 200 and len(avatar_response.content) > 100:
                        avatar_filename = f"avatar_{user_id}.jpg"
                        avatar_path = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars', avatar_filename)
                        
                        with open(avatar_path, 'wb') as f:
                            f.write(avatar_response.content)
                        
                        optimize_image_size(avatar_path)
                        
                        profile_info['avatar'] = f"uploads/avatars/{avatar_filename}"
                        profile_info['avatar_source'] = 'کاربان'
                        print(f"✅ آواتار کاربر {user_id} از کاربان دریافت و ذخیره شد")
                    else:
                        profile_info['avatar'] = None
                        profile_info['avatar_source'] = 'ندارد'
                        print(f"⚠️ آواتار برای کاربر {user_id} موجود نیست")
                        
                except Exception as e:
                    print(f"⚠️ Error loading avatar for user {user_id}: {str(e)}")
                    profile_info['avatar'] = None
                    profile_info['avatar_source'] = 'خطا'
            
            print(f"✅ اطلاعات کاربر دریافت شد - سطح دسترسی: {profile_info['access_level']} - آواتار: {profile_info['avatar_source']}")
            
            return profile_info
        else:
            print(f"❌ User API error: {user_response.text}")
            return None
        
    except Exception as e:
        print(f"❌ Error fetching user profile: {str(e)}")
        return None

# ==================== توابع دیتابیس ====================

def get_db_connection():
    """ایجاد اتصال به دیتابیس"""
    conn = sqlite3.connect('system.db')
    conn.row_factory = sqlite3.Row
    init_db_safe(conn)
    return conn

def init_db_safe(conn=None):
    """ایجاد جداول اگر وجود ندارند"""
    close_after = False
    if conn is None:
        conn = sqlite3.connect('system.db')
        close_after = True
    
    try:
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
        
        # جدول آواتارهای کاربران
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_avatars (
                user_id TEXT PRIMARY KEY,
                avatar_path TEXT,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول کش پروژه‌ها
        conn.execute('''
            CREATE TABLE IF NOT EXISTS projects_cache (
                project_id INTEGER PRIMARY KEY,
                project_data TEXT,
                custom_fields TEXT,
                excel_data TEXT,
                last_sync DATETIME DEFAULT CURRENT_TIMESTAMP,
                sync_count INTEGER DEFAULT 0
            )
        ''')
        
        # جدول تنظیمات نمایش ستون‌ها
        conn.execute('''
            CREATE TABLE IF NOT EXISTS column_settings (
                column_name TEXT PRIMARY KEY,
                visible BOOLEAN DEFAULT 1,
                display_order INTEGER DEFAULT 0
            )
        ''')
        
        # جدول جدید: پیشرفت پروژه‌ها
        conn.execute('''
            CREATE TABLE IF NOT EXISTS project_progress (
                project_id INTEGER PRIMARY KEY,
                percentage_done INTEGER DEFAULT 0,
                work_package_id INTEGER,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول جدید: کش کاربران
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users_cache (
                user_id INTEGER PRIMARY KEY,
                user_data TEXT,
                custom_fields TEXT,
                last_sync DATETIME DEFAULT CURRENT_TIMESTAMP,
                sync_count INTEGER DEFAULT 0
            )
        ''')
        
        # تنظیمات پیش‌فرض
        default_settings = {
            'system_name': 'سامانه مدیریت پروژه‌های کاربان',
            'header_color': '#0d6efd',
            'header_text_color': '#ffffff',
            'background_color': '#f8f9fa',
            'login_width': '380',
            'login_height': 'auto',
            'login_position_x': '50',
            'login_position_y': '50',
            'max_login_attempts': '3',
            'lockout_time': '30',
            'flash_timeout': '3',
            'session_timeout': '30',
            'login_button_text': 'ورود با اکانت کاربان',
            'login_button_icon': 'bi-box-arrow-in-right',
            'login_text_1': 'مدیریت پروژه‌ها و وظایف',
            'login_icon_1': '🔐',
            'login_text_2': 'گزارش‌گیری و آنالیز پیشرفت',
            'login_icon_2': '📊',
            'login_text_3': 'همکاری تیمی و مدیریت زمان',
            'login_icon_3': '📈',
            'copyright_text': '© 1404 سامانه مدیریت عملکرد'
        }
        
        for key, value in default_settings.items():
            conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
        
        # تنظیمات پیش‌فرض ستون‌ها
        default_columns = [
            ('row_number', 1, 0),
            ('avatar', 1, 1),
            ('id', 1, 2),
            ('name', 1, 3),
            ('identifier', 1, 4),
            ('project_code', 1, 5),
            ('voltage_level', 1, 6),
            ('panel_type', 1, 7),
            ('panel_count', 1, 8),
            ('cell_count', 1, 9),
            ('department', 1, 10),
            ('team_leader', 1, 11),
            ('team', 1, 12),
            ('equipment_date', 1, 13),
            ('urgent', 1, 14),
            ('status', 1, 15),
            ('active', 1, 16),
            ('public', 1, 17),
            ('created_at', 1, 18),
            ('updated_at', 1, 19),
            ('link', 1, 20),
            ('description', 1, 21),
            ('progress_percentage', 1, 22)
        ]
        
        for column_name, visible, display_order in default_columns:
            conn.execute('INSERT OR IGNORE INTO column_settings (column_name, visible, display_order) VALUES (?, ?, ?)', 
                        (column_name, visible, display_order))
        
        conn.commit()
        print("✅ دیتابیس سیستم بررسی و ایجاد شد")
        
    except Exception as e:
        print(f"❌ خطا در ایجاد دیتابیس: {str(e)}")
        raise e
    finally:
        if close_after:
            conn.close()

def get_setting(key, default=None):
    """دریافت تنظیم از دیتابیس"""
    conn = get_db_connection()
    try:
        result = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        return result['value'] if result else default
    except Exception as e:
        print(f"⚠️ خطا در دریافت تنظیم {key}: {str(e)}")
        return default
    finally:
        conn.close()

def save_setting(key, value):
    """ذخیره تنظیم در دیتابیس"""
    conn = get_db_connection()
    try:
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()
    except Exception as e:
        print(f"❌ خطا در ذخیره تنظیم: {str(e)}")
        raise e
    finally:
        conn.close()

def get_all_settings():
    """دریافت تمام تنظیمات"""
    conn = get_db_connection()
    try:
        settings = conn.execute('SELECT * FROM settings').fetchall()
        return {setting['key']: setting['value'] for setting in settings}
    except Exception as e:
        print(f"❌ خطا در دریافت تنظیمات: {str(e)}")
        return {}
    finally:
        conn.close()

def get_column_settings():
    """دریافت تنظیمات نمایش ستون‌ها"""
    conn = get_db_connection()
    try:
        columns = conn.execute('SELECT * FROM column_settings ORDER BY display_order').fetchall()
        return {column['column_name']: {'visible': bool(column['visible']), 'order': column['display_order']} for column in columns}
    except Exception as e:
        print(f"❌ خطا در دریافت تنظیمات ستون‌ها: {str(e)}")
        return {}
    finally:
        conn.close()

def save_column_settings(column_settings):
    """ذخیره تنظیمات نمایش ستون‌ها"""
    conn = get_db_connection()
    try:
        for column_name, settings in column_settings.items():
            conn.execute('INSERT OR REPLACE INTO column_settings (column_name, visible, display_order) VALUES (?, ?, ?)', 
                        (column_name, settings['visible'], settings['order']))
        conn.commit()
        print(f"✅ تنظیمات {len(column_settings)} ستون ذخیره شد")
    except Exception as e:
        print(f"❌ خطا در ذخیره تنظیمات ستون‌ها: {str(e)}")
        raise e
    finally:
        conn.close()

def save_user_avatar(user_id, avatar_path):
    """ذخیره آواتار کاربر"""
    conn = get_db_connection()
    try:
        conn.execute('INSERT OR REPLACE INTO user_avatars (user_id, avatar_path) VALUES (?, ?)', (user_id, avatar_path))
        conn.commit()
    finally:
        conn.close()

def get_user_avatar(user_id):
    """دریافت آواتار کاربر"""
    if not user_id:
        return None
    conn = get_db_connection()
    try:
        result = conn.execute('SELECT avatar_path FROM user_avatars WHERE user_id = ?', (user_id,)).fetchone()
        return result['avatar_path'] if result else None
    finally:
        conn.close()

def check_user_lock(username):
    """بررسی قفل بودن کاربر"""
    conn = get_db_connection()
    try:
        user = conn.execute(
            'SELECT * FROM locked_users WHERE username = ?', (username,)
        ).fetchone()
        
        if user:
            locked_until = datetime.fromisoformat(user['locked_until']) if user['locked_until'] else None
            if locked_until and datetime.now() < locked_until:
                return True, locked_until
        return False, None
    finally:
        conn.close()

def increment_login_attempt(username):
    """افزایش تعداد تلاش‌های ناموفق"""
    conn = get_db_connection()
    try:
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
    finally:
        conn.close()

def reset_login_attempts(username):
    """ریست کردن تلاش‌های ناموفق"""
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM locked_users WHERE username = ?', (username,))
        conn.commit()
    finally:
        conn.close()

def save_projects_cache(projects_data):
    """ذخیره پروژه‌ها در کش"""
    conn = get_db_connection()
    try:
        # حذف کش قدیمی
        conn.execute('DELETE FROM projects_cache')
        
        # ذخیره پروژه‌های جدید
        for project in projects_data:
            project_id = project.get('id')
            if project_id:
                # استخراج فیلدهای سفارشی
                custom_fields = extract_custom_fields(project)
                
                # دریافت داده‌های اکسل برای این پروژه
                excel_data = get_excel_data_for_project(project_id)
                
                conn.execute(
                    'INSERT INTO projects_cache (project_id, project_data, custom_fields, excel_data, sync_count) VALUES (?, ?, ?, ?, COALESCE((SELECT sync_count FROM projects_cache WHERE project_id = ?), 0) + 1)',
                    (project_id, json.dumps(project), json.dumps(custom_fields), json.dumps(excel_data), project_id)
                )
        
        conn.commit()
        print(f"✅ {len(projects_data)} پروژه در کش ذخیره شد")
    except Exception as e:
        print(f"❌ خطا در ذخیره کش: {str(e)}")
    finally:
        conn.close()

def get_projects_cache():
    """دریافت پروژه‌ها از کش"""
    conn = get_db_connection()
    try:
        results = conn.execute('''
            SELECT pc.project_data, pc.custom_fields, pc.excel_data, pp.percentage_done, pp.last_updated
            FROM projects_cache pc
            LEFT JOIN project_progress pp ON pc.project_id = pp.project_id
            ORDER BY pc.project_id
        ''').fetchall()
        
        projects = []
        for result in results:
            try:
                project_data = json.loads(result['project_data'])
                custom_fields = json.loads(result['custom_fields']) if result['custom_fields'] else {}
                excel_data = json.loads(result['excel_data']) if result['excel_data'] else {}
                
                # ادغام فیلدهای سفارشی و داده‌های اکسل با داده‌های اصلی پروژه
                project_data['custom_fields'] = custom_fields
                project_data['excel_data'] = excel_data
                
                # اضافه کردن اطلاعات پیشرفت
                if result['percentage_done'] is not None:
                    project_data['progress'] = {
                        'percentage_done': result['percentage_done'],
                        'last_updated': result['last_updated']
                    }
                
                projects.append(project_data)
            except Exception as e:
                print(f"⚠️ خطا در خواندن پروژه از کش: {str(e)}")
                continue
        
        return projects
    except Exception as e:
        print(f"❌ خطا در خواندن کش: {str(e)}")
        return []
    finally:
        conn.close()

def save_users_cache(users_data):
    """ذخیره کاربران در کش"""
    conn = get_db_connection()
    try:
        # حذف کش قدیمی
        conn.execute('DELETE FROM users_cache')
        
        # ذخیره کاربران جدید
        for user in users_data:
            user_id = user.get('id')
            if user_id:
                # استخراج فیلدهای سفارشی
                custom_fields = user.get('custom_fields', {})
                
                conn.execute(
                    'INSERT INTO users_cache (user_id, user_data, custom_fields, sync_count) VALUES (?, ?, ?, COALESCE((SELECT sync_count FROM users_cache WHERE user_id = ?), 0) + 1)',
                    (user_id, json.dumps(user), json.dumps(custom_fields), user_id)
                )
        
        conn.commit()
        print(f"✅ {len(users_data)} کاربر در کش ذخیره شد")
    except Exception as e:
        print(f"❌ خطا در ذخیره کش کاربران: {str(e)}")
    finally:
        conn.close()

def get_users_cache():
    """دریافت کاربران از کش"""
    conn = get_db_connection()
    try:
        results = conn.execute('SELECT user_data, custom_fields FROM users_cache ORDER BY user_id').fetchall()
        
        users = []
        for result in results:
            try:
                user_data = json.loads(result['user_data'])
                custom_fields = json.loads(result['custom_fields']) if result['custom_fields'] else {}
                
                # ادغام فیلدهای سفارشی با داده‌های اصلی کاربر
                user_data['custom_fields'] = custom_fields
                
                users.append(user_data)
            except Exception as e:
                print(f"⚠️ خطا در خواندن کاربر از کش: {str(e)}")
                continue
        
        return users
    except Exception as e:
        print(f"❌ خطا در خواندن کش کاربران: {str(e)}")
        return []
    finally:
        conn.close()

def get_cache_info():
    """دریافت اطلاعات کش"""
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT COUNT(*) as count, MAX(last_sync) as last_sync, SUM(sync_count) as total_syncs 
            FROM projects_cache
        ''').fetchone()
        
        return {
            'count': result['count'] if result else 0,
            'last_sync': result['last_sync'] if result else None,
            'total_syncs': result['total_syncs'] if result else 0
        }
    except Exception as e:
        print(f"❌ خطا در دریافت اطلاعات کش: {str(e)}")
        return {'count': 0, 'last_sync': None, 'total_syncs': 0}
    finally:
        conn.close()

def get_users_cache_info():
    """دریافت اطلاعات کش کاربران"""
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT COUNT(*) as count, MAX(last_sync) as last_sync, SUM(sync_count) as total_syncs 
            FROM users_cache
        ''').fetchone()
        
        return {
            'count': result['count'] if result else 0,
            'last_sync': result['last_sync'] if result else None,
            'total_syncs': result['total_syncs'] if result else 0
        }
    except Exception as e:
        print(f"❌ خطا در دریافت اطلاعات کش کاربران: {str(e)}")
        return {'count': 0, 'last_sync': None, 'total_syncs': 0}
    finally:
        conn.close()

def save_project_progress(project_id, percentage_done, work_package_id=None):
    """ذخیره درصد پیشرفت پروژه"""
    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO project_progress 
            (project_id, percentage_done, work_package_id, last_updated) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (project_id, percentage_done, work_package_id))
        conn.commit()
        print(f"✅ پیشرفت پروژه {project_id} ذخیره شد: {percentage_done}%")
    except Exception as e:
        print(f"❌ خطا در ذخیره پیشرفت پروژه {project_id}: {str(e)}")
        raise e
    finally:
        conn.close()

def get_project_progress(project_id):
    """دریافت درصد پیشرفت پروژه"""
    conn = get_db_connection()
    try:
        result = conn.execute('''
            SELECT percentage_done, last_updated 
            FROM project_progress 
            WHERE project_id = ?
        ''', (project_id,)).fetchone()
        
        if result:
            return {
                'percentage_done': result['percentage_done'],
                'last_updated': result['last_updated']
            }
        return None
    except Exception as e:
        print(f"❌ خطا در دریافت پیشرفت پروژه {project_id}: {str(e)}")
        return None
    finally:
        conn.close()

# ==================== کاربان API ====================

class OpenProjectAPI:
    def __init__(self, base_url):
        self.base_url = base_url
    
    def get_authorization_url(self, client_id, redirect_uri):
        """دریافت URL برای احراز هویت"""
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': 'api_v3 bcf_v2_1'
        }
        return f"{self.base_url}/oauth/authorize?{urllib.parse.urlencode(params)}"
    
    def get_token_with_code(self, code, client_id, client_secret, redirect_uri):
        """دریافت توکن با authorization code"""
        token_url = f"{self.base_url}/oauth/token"
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri
        }
        
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(token_url, data=data, headers=headers, verify=False)
        return response
    
    def get_user_info(self, access_token):
        """دریافت اطلاعات کاربر"""
        url = f"{self.base_url}/api/v3/users/me"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers, verify=False)
        return response
    
    def get_user_details(self, access_token, user_id):
        """دریافت اطلاعات کامل کاربر از کاربان"""
        url = f"{self.base_url}/api/v3/users/{user_id}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers, verify=False)
        return response
    
    def get_projects_page(self, access_token, page_size=1000, offset=1):
        """دریافت یک صفحه از پروژه‌ها"""
        url = f"{self.base_url}/api/v3/projects"
        params = {
            'pageSize': page_size,
            'offset': offset,
            'sortBy': '[["name", "asc"]]'
        }
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=headers, params=params, verify=False)
        return response
    
    def get_all_projects(self, access_token):
        """دریافت تمام پروژه‌ها از کاربان"""
        print("🚀 شروع دریافت تمام پروژه‌ها از کاربان...")
        
        page_size = 1000
        offset = 1
        
        response = self.get_projects_page(access_token, page_size, offset)
        
        if response.status_code == 200:
            data = response.json()
            projects = data.get('_embedded', {}).get('elements', [])
            
            print(f"✅ {len(projects)} پروژه از API دریافت شد")
            
            # دریافت اطلاعات کامل هر پروژه برای فیلدهای سفارشی
            enhanced_projects = []
            for i, project in enumerate(projects):
                try:
                    project_id = project.get('id')
                    project_name = project.get('name', 'بدون نام')
                    
                    if project_id:
                        # دریافت اطلاعات کامل پروژه
                        detail_response = self.get_project_details(access_token, project_id)
                        if detail_response.status_code == 200:
                            project_details = detail_response.json()
                            # استخراج فیلدهای سفارشی قبل از ادغام
                            custom_fields = extract_custom_fields(project_details)
                            print(f"   ✅ جزئیات پروژه {project_id} دریافت شد - {len(custom_fields)} فیلد سفارفی")
                            
                            # ادغام اطلاعات پایه با اطلاعات کامل
                            project.update(project_details)
                    
                    enhanced_projects.append(project)
                    
                except Exception as e:
                    print(f"   ❌ خطا در پردازش پروژه {project.get('id')}: {str(e)}")
                    enhanced_projects.append(project)
            
            return enhanced_projects
        else:
            print(f"❌ خطا در دریافت پروژه‌ها: {response.status_code}")
            print(f"متن پاسخ: {response.text}")
            return []
    
    def get_project_details(self, access_token, project_id):
        """دریافت اطلاعات کامل یک پروژه"""
        url = f"{self.base_url}/api/v3/projects/{project_id}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        response = requests.get(url, headers=headers, verify=False)
        return response

    def get_work_packages(self, access_token, project_id):
        """دریافت Work Packageهای یک پروژه"""
        url = f"{self.base_url}/api/v3/projects/{project_id}/work_packages"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        print(f"🔍 دریافت Work Packageهای پروژه {project_id}")
        response = requests.get(url, headers=headers, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            work_packages = data.get('_embedded', {}).get('elements', [])
            print(f"✅ {len(work_packages)} Work Package برای پروژه {project_id} دریافت شد")
            return work_packages
        else:
            print(f"❌ خطا در دریافت Work Packageهای پروژه {project_id}: {response.status_code}")
            return []

    def get_main_work_package_progress(self, access_token, project_id):
        """دریافت درصد پیشرفت از Work Package اصلی پروژه"""
        try:
            work_packages = self.get_work_packages(access_token, project_id)
            
            if not work_packages:
                print(f"⚠️ هیچ Work Packageی برای پروژه {project_id} یافت نشد")
                return None
            
            main_wp = None
            
            # جستجوی Work Package از نوع "Project"
            for wp in work_packages:
                wp_type = wp.get('_embedded', {}).get('type', {})
                if wp_type.get('name') == 'Project':
                    main_wp = wp
                    print(f"✅ Work Package اصلی (نوع Project) برای پروژه {project_id} یافت شد")
                    break
            
            # اگر Work Package از نوع Project پیدا نشد، اولین Work Package بدون parent
            if not main_wp:
                for wp in work_packages:
                    parent = wp.get('_embedded', {}).get('parent')
                    if not parent:
                        main_wp = wp
                        print(f"✅ Work Package اصلی (بدون parent) برای پروژه {project_id} یافت شد")
                        break
            
            # اگر باز هم پیدا نشد، اولین Work Package
            if not main_wp and work_packages:
                main_wp = work_packages[0]
                print(f"✅ اولین Work Package برای پروژه {project_id} انتخاب شد")
            
            if main_wp:
                percentage_done = main_wp.get('percentageDone', 0)
                wp_id = main_wp.get('id')
                wp_subject = main_wp.get('subject', 'بدون موضوع')
                
                print(f"📊 پیشرفت Work Package {wp_id} ('{wp_subject}'): {percentage_done}%")
                return percentage_done
            
            return None
            
        except Exception as e:
            print(f"❌ خطا در دریافت پیشرفت Work Package پروژه {project_id}: {str(e)}")
            return None

# ایجاد نمونه API
op_api = OpenProjectAPI(OP_BASE_URL)

def get_all_users(access_token):
    """دریافت لیست تمام کاربران از OpenProject"""
    try:
        url = f"{OP_BASE_URL}/api/v3/users"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        print("🚀 شروع دریافت کاربران از کاربان...")
        response = requests.get(url, headers=headers, verify=False)
        
        if response.status_code == 200:
            data = response.json()
            users = data.get('_embedded', {}).get('elements', [])
            
            print(f"✅ {len(users)} کاربر از API دریافت شد")
            
            # دریافت اطلاعات کامل هر کاربر
            enhanced_users = []
            for i, user in enumerate(users):
                try:
                    user_id = user.get('id')
                    user_name = user.get('name', 'بدون نام')
                    
                    if user_id:
                        # دریافت اطلاعات کامل کاربر
                        user_profile = get_complete_user_profile(access_token, user_id)
                        if user_profile:
                            # ادغام اطلاعات پایه با اطلاعات کامل
                            user.update(user_profile)
                            print(f"   ✅ جزئیات کاربر {user_id} دریافت شد")
                    
                    enhanced_users.append(user)
                    
                except Exception as e:
                    print(f"   ❌ خطا در پردازش کاربر {user.get('id')}: {str(e)}")
                    enhanced_users.append(user)
            
            return enhanced_users
        else:
            print(f"❌ خطا در دریافت کاربران: {response.status_code}")
            print(f"متن پاسخ: {response.text}")
            return []
    
    except Exception as e:
        print(f"❌ خطا در دریافت کاربران: {str(e)}")
        return []

def get_excel_data_for_project(project_id):
    """دریافت داده‌های اکسل برای پروژه"""
    return {}

def update_projects_progress(access_token):
    """به‌روزرسانی درصد پیشرفت تمام پروژه‌ها"""
    try:
        projects_data = get_projects_cache()
        updated_count = 0
        
        for project in projects_data:
            project_id = project.get('id')
            project_name = project.get('name', 'بدون نام')
            
            if project_id:
                print(f"🔍 به‌روزرسانی پیشرفت پروژه: {project_name} (ID: {project_id})")
                
                # دریافت درصد پیشرفت از Work Package اصلی
                percentage_done = op_api.get_main_work_package_progress(access_token, project_id)
                
                if percentage_done is not None:
                    # ذخیره در دیتابیس
                    save_project_progress(project_id, percentage_done)
                    updated_count += 1
                    print(f"✅ پیشرفت پروژه {project_id} به‌روزرسانی شد: {percentage_done}%")
                else:
                    print(f"⚠️ نتوانستیم پیشرفت پروژه {project_id} را دریافت کنیم")
        
        print(f"✅ به‌روزرسانی پیشرفت پروژه‌ها کامل شد: {updated_count} پروژه به‌روزرسانی شد")
        return updated_count
        
    except Exception as e:
        print(f"❌ خطا در به‌روزرسانی پیشرفت پروژه‌ها: {str(e)}")
        return 0

# ==================== Context Processor ====================

@app.context_processor
def utility_processor():
    """اضافه کردن توابع به context تمام templateها"""
    return dict(
        get_user_avatar=get_user_avatar,
        get_user_display_avatar=get_user_display_avatar,
        OP_BASE_URL=OP_BASE_URL,
        clean_html_description=clean_html_description,
        extract_custom_fields=extract_custom_fields,
        get_custom_field_value=get_custom_field_value,
        convert_to_jalali=convert_to_jalali,
        format_sync_date=format_sync_date,
        get_column_settings=get_column_settings,
        get_project_progress=get_project_progress
    )

# ==================== Routes ====================

@app.before_request
def before_request():
    """بررسی session timeout قبل از هر درخواست"""
    try:
        init_db_safe()
    except Exception as e:
        print(f"⚠️ خطا در بررسی دیتابیس: {str(e)}")
    
    if 'user_id' in session:
        session.permanent = True
        try:
            app.permanent_session_lifetime = timedelta(minutes=int(get_setting('session_timeout', 30)))
        except:
            app.permanent_session_lifetime = timedelta(minutes=30)
        
        last_activity = session.get('last_activity')
        if last_activity:
            try:
                last_activity = datetime.fromisoformat(last_activity)
                session_timeout = int(get_setting('session_timeout', 30))
                if datetime.now() - last_activity > timedelta(minutes=session_timeout):
                    session.clear()
                    flash('Session شما منقضی شده است. لطفاً مجدداً وارد شوید.', 'info')
                    return redirect('/')
            except:
                pass
        
        session['last_activity'] = datetime.now().isoformat()

@app.route('/')
def index():
    """صفحه اصلی"""
    try:
        init_db_safe()
    except Exception as e:
        print(f"⚠️ خطا در راه‌اندازی سیستم: {str(e)}")
        flash('خطا در راه‌اندازی سیستم. لطفاً با پشتیبانی تماس بگیرید.', 'error')
    
    code = request.args.get('code')
    
    if code:
        return process_callback(code)
    
    if 'user_id' in session:
        return redirect('/dashboard')
    
    settings = get_all_settings()
    return render_template('login.html', settings=settings)

def process_callback(code):
    """پردازش callback کاربان"""
    try:
        print(f"🎯 Processing callback with code: {code}")
        
        token_response = op_api.get_token_with_code(
            code, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI
        )
        
        print(f"🔐 Token response status: {token_response.status_code}")
        
        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            
            if access_token:
                print(f"✅ Access token received: {access_token[:20]}...")
                
                user_response = op_api.get_user_info(access_token)
                print(f"👤 User info response status: {user_response.status_code}")
                
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    username = user_data.get('login', '')
                    user_name = user_data.get('name', username)
                    user_id = user_data.get('id')
                    
                    print(f"✅ User data received: {user_name} (ID: {user_id})")
                    
                    if not username:
                        flash('خطا: اطلاعات کاربر نامعتبر است', 'error')
                        return redirect('/')
                    
                    is_locked, locked_until = check_user_lock(username)
                    if is_locked:
                        flash(f'حساب شما تا {locked_until.strftime("%H:%M")} قفل شده است', 'error')
                        return redirect('/')
                    
                    reset_login_attempts(username)
                    
                    session['user_id'] = user_id
                    session['username'] = username
                    session['email'] = user_data.get('email', '')
                    session['full_name'] = user_name
                    session['access_token'] = access_token
                    session['is_authenticated'] = True
                    session['is_admin'] = user_data.get('admin', False)  # استفاده از مقدار واقعی از OpenProject
                    session['status'] = user_data.get('status', 'active')  # ذخیره وضعیت کاربر
                    session['last_activity'] = datetime.now().isoformat()
                    session['first_login'] = get_persian_datetime()
                    
                    try:
                        user_profile = get_complete_user_profile(access_token, user_id)
                        if user_profile:
                            session['avatar_url'] = user_profile.get('avatar')
                            session['user_role'] = user_profile.get('user_role_custom', 'user')
                            # استفاده از position واقعی از OpenProject
                            session['position'] = user_profile.get('position', 'عضو')
                            session['department'] = user_profile.get('department', 'فناوری اطلاعات')
                            session['team'] = user_profile.get('team', '')
                            session['custom_fields'] = user_profile.get('custom_fields', {})
                            session['access_level'] = user_profile.get('access_level', 'کاربر عادی')
                            print(f"✅ User profile loaded successfully")
                        else:
                            print(f"⚠️ Could not load user profile")
                    except Exception as e:
                        print(f"⚠️ Error loading user profile: {str(e)}")
                    
                    print(f"✅ Login successful for: {username}")
                    print(f"🔐 User admin status: {session['is_admin']}")
                    print(f"👤 User position: {session['position']}")
                    print(f"📊 User status: {session['status']}")
                    flash('ورود موفقیت‌آمیز بود!', 'success')
                    return redirect('/dashboard')
                else:
                    error_msg = user_response.json().get('message', 'خطا در دریافت اطلاعات کاربر')
                    print(f"❌ User info error: {error_msg}")
                    flash(f'خطا: {error_msg}', 'error')
            else:
                print("❌ No access token in response")
                flash('خطا: توکن دسترسی دریافت نشد', 'error')
        else:
            error_data = token_response.json()
            error_msg = error_data.get('error_description', 'خطا در دریافت توکن')
            print(f"❌ Token error: {error_msg}")
            
            if 'username' in session:
                increment_login_attempt(session['username'])
            
            flash(f'خطا: {error_msg}', 'error')
            
    except Exception as e:
        print(f"❌ Callback exception: {str(e)}")
        flash(f'خطا در ارتباط با سرور: {str(e)}', 'error')
    
    return redirect('/')

@app.route('/auth/start')
def auth_start():
    """شروع فرآیند OAuth"""
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    auth_url = op_api.get_authorization_url(CLIENT_ID, REDIRECT_URI)
    print(f"🔗 Redirecting to کاربان: {auth_url}")
    return redirect(auth_url)

@app.route('/login')
def login():
    """صفحه لاگین"""
    if 'user_id' in session:
        return redirect('/dashboard')
    
    settings = get_all_settings()
    return render_template('login.html', settings=settings)

@app.route('/dashboard')
def dashboard():
    """صفحه داشبورد"""
    if 'user_id' not in session:
        flash('لطفاً ابتدا وارد شوید', 'error')
        return redirect('/')
    
    settings = get_all_settings()
    
    user_info = {
        'name': session.get('full_name', 'کاربر'),
        'username': session.get('username', ''),
        'email': session.get('email', ''),
        'role': session.get('user_role', 'کاربر'),
        'avatar': session.get('avatar_url', ''),
        'is_admin': session.get('is_admin', False)
    }
    
    try:
        projects_data = get_projects_cache()
        projects_count = len(projects_data)
        active_projects = len([p for p in projects_data if p.get('active', False)])
        public_projects = len([p for p in projects_data if p.get('public', False)])
        
        # آمار وضعیت پروژه‌ها
        status_stats = {
            'on_track': len([p for p in projects_data if p.get('status') == 'on_track']),
            'at_risk': len([p for p in projects_data if p.get('status') == 'at_risk']),
            'off_track': len([p for p in projects_data if p.get('status') == 'off_track']),
        }
    except:
        projects_count = 0
        active_projects = 0
        public_projects = 0
        status_stats = {}
    
    return render_template('dashboard.html', 
                         settings=settings, 
                         user_info=user_info,
                         projects_count=projects_count,
                         active_projects=active_projects,
                         public_projects=public_projects,
                         status_stats=status_stats)

@app.route('/user/profile')
def user_profile():
    """صفحه پروفایل کاربر"""
    if 'user_id' not in session:
        flash('لطفاً ابتدا وارد شوید', 'error')
        return redirect('/')
    
    settings = get_all_settings()
    
    # اولویت با آواتار آپلود شده توسط کاربر است
    uploaded_avatar = get_user_avatar(session['user_id'])
    has_custom_avatar = uploaded_avatar is not None
    
    # دریافت اطلاعات واقعی از session
    user_is_admin = session.get('is_admin', False)
    user_position = session.get('position', 'عضو')
    user_status = session.get('status', 'active')  # دریافت وضعیت از session
    
    user_info = {
        'name': session.get('full_name', 'کاربر'),
        'username': session.get('username', ''),
        'email': session.get('email', ''),
        'role': session.get('user_role', 'کاربر'),
        'avatar': uploaded_avatar or session.get('avatar_url', ''),  # اولویت با آواتار آپلود شده
        'is_admin': user_is_admin,  # استفاده از مقدار واقعی از session
        'user_id': session.get('user_id', ''),
        'login_method': 'کاربان',
        'company': 'جابون',
        'position': user_position,  # استفاده از مقدار واقعی از session
        'first_login': session.get('first_login', get_persian_datetime()),
        'department': session.get('department', 'فناوری اطلاعات'),
        'user_role_custom': session.get('user_role', 'کاربر'),
        'team': session.get('team', ''),
        'custom_fields': session.get('custom_fields', {}),
        'has_custom_avatar': has_custom_avatar,
        'status': user_status,  # اضافه کردن وضعیت
        'access_level': session.get('access_level', 'کاربر عادی')  # اضافه کردن سطح دسترسی
    }
    
    return render_template('profile.html', settings=settings, user_info=user_info)

@app.route('/user/upload_avatar', methods=['POST'])
def upload_avatar():
    """آپلود آواتار کاربر"""
    if 'user_id' not in session:
        return redirect('/')
    
    try:
        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename:
            # ذخیره فایل آپلود شده
            avatar_path = save_uploaded_file(avatar_file, 'avatars')
            if avatar_path:
                # ذخیره در دیتابیس
                save_user_avatar(session['user_id'], avatar_path)
                flash('آواتار با موفقیت آپلود شد', 'success')
            else:
                flash('خطا در آپلود آواتار', 'error')
        else:
            flash('لطفاً یک فایل انتخاب کنید', 'error')
            
    except Exception as e:
        flash(f'خطا در آپلود آواتار: {str(e)}', 'error')
    
    return redirect('/user/profile')

@app.route('/user/remove_avatar', methods=['POST'])
def remove_avatar():
    """حذف آواتار آپلود شده و بازگشت به تصویر OpenProject"""
    if 'user_id' not in session:
        return redirect('/')
    
    try:
        # حذف آواتار از دیتابیس
        conn = get_db_connection()
        conn.execute('DELETE FROM user_avatars WHERE user_id = ?', (session['user_id'],))
        conn.commit()
        conn.close()
        
        flash('آواتار با موفقیت حذف شد و به تصویر اصلی کاربان بازگشتید', 'success')
        
    except Exception as e:
        flash(f'خطا در حذف آواتار: {str(e)}', 'error')
    
    return redirect('/user/profile')

@app.route('/user/refresh_profile')
def refresh_profile():
    """بروزرسانی اطلاعات پروفایل از کاربان"""
    if 'user_id' not in session or 'access_token' not in session:
        return redirect('/')
    
    try:
        user_profile = get_complete_user_profile(session['access_token'], session['user_id'])
        
        if user_profile:
            session['full_name'] = user_profile.get('name', session.get('full_name', ''))
            session['email'] = user_profile.get('email', session.get('email', ''))
            session['user_role'] = user_profile.get('user_role_custom', session.get('user_role', 'user'))
            session['avatar_url'] = user_profile.get('avatar', session.get('avatar_url', ''))
            session['position'] = user_profile.get('position', session.get('position', 'عضو'))
            session['department'] = user_profile.get('department', session.get('department', 'فناوری اطلاعات'))
            session['team'] = user_profile.get('team', session.get('team', ''))
            session['custom_fields'] = user_profile.get('custom_fields', session.get('custom_fields', {}))
            session['status'] = user_profile.get('status', session.get('status', 'active'))  # به روزرسانی وضعیت
            session['access_level'] = user_profile.get('access_level', session.get('access_level', 'کاربر عادی'))  # به روزرسانی سطح دسترسی
            
            flash('اطلاعات پروفایل با موفقیت بروزرسانی شد', 'success')
        else:
            flash('خطا در دریافت اطلاعات پروفایل از کاربان', 'error')
            
    except Exception as e:
        flash(f'خطا در بروزرسانی پروفایل: {str(e)}', 'error')
    
    return redirect('/user/profile')

@app.route('/admin/settings')
def admin_settings():
    """صفحه تنظیمات ادمین"""
    if 'user_id' not in session or not session.get('is_admin'):
        flash('دسترسی غیر مجاز', 'error')
        return redirect('/dashboard')
    
    settings = get_all_settings()
    column_settings = get_column_settings()
    return render_template('admin_settings.html', settings=settings, column_settings=column_settings)

@app.route('/admin/save_settings', methods=['POST'])
def save_settings():
    """ذخیره تنظیمات"""
    if 'user_id' not in session or not session.get('is_admin'):
        flash('دسترسی غیر مجاز', 'error')
        return redirect('/dashboard')
    
    try:
        settings_to_save = {
            'system_name': request.form.get('system_name'),
            'header_color': request.form.get('header_color'),
            'header_text_color': request.form.get('header_text_color'),
            'background_color': request.form.get('background_color'),
            'login_width': request.form.get('login_width'),
            'login_height': request.form.get('login_height'),
            'login_position_x': request.form.get('login_position_x'),
            'login_position_y': request.form.get('login_position_y'),
            'max_login_attempts': request.form.get('max_login_attempts'),
            'lockout_time': request.form.get('lockout_time'),
            'flash_timeout': request.form.get('flash_timeout'),
            'session_timeout': request.form.get('session_timeout'),
            'login_button_text': request.form.get('login_button_text'),
            'login_button_icon': request.form.get('login_button_icon'),
            'login_text_1': request.form.get('login_text_1'),
            'login_icon_1': request.form.get('login_icon_1'),
            'login_text_2': request.form.get('login_text_2'),
            'login_icon_2': request.form.get('login_icon_2'),
            'login_text_3': request.form.get('login_text_3'),
            'login_icon_3': request.form.get('login_icon_3'),
            'copyright_text': request.form.get('copyright_text')
        }
        
        for key, value in settings_to_save.items():
            if value is not None:
                save_setting(key, value)
        
        # ذخیره تنظیمات ستون‌ها
        column_settings = {}
        column_names = [
            'row_number', 'avatar', 'id', 'name', 'identifier', 'project_code',
            'voltage_level', 'panel_type', 'panel_count', 'cell_count', 'department',
            'team_leader', 'team', 'equipment_date', 'urgent', 'status', 'active',
            'public', 'created_at', 'updated_at', 'link', 'description', 'progress_percentage'
        ]
        
        for column_name in column_names:
            visible = request.form.get(f'column_{column_name}') == 'on'
            order = int(request.form.get(f'order_{column_name}', 0))
            column_settings[column_name] = {
                'visible': visible,
                'order': order
            }
        
        if column_settings:
            save_column_settings(column_settings)
            print(f"✅ تنظیمات {len(column_settings)} ستون ذخیره شد")
        
        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            logo_path = save_uploaded_file(logo_file, 'logo')
            if logo_path:
                save_setting('logo_path', logo_path)
        
        background_file = request.files.get('background')
        if background_file and background_file.filename:
            background_path = save_uploaded_file(background_file, 'background')
            if background_path:
                save_setting('background_path', background_path)
        
        flash('تنظیمات با موفقیت ذخیره شد', 'success')
        
    except Exception as e:
        flash(f'خطا در ذخیره تنظیمات: {str(e)}', 'error')
        print(f"❌ خطا در ذخیره تنظیمات: {str(e)}")
    
    return redirect('/admin/settings')

@app.route('/projects')
def projects():
    """صفحه پروژه‌ها"""
    if 'user_id' not in session:
        flash('لطفاً ابتدا وارد شوید', 'error')
        return redirect('/')
    
    settings = get_all_settings()
    column_settings = get_column_settings()
    
    projects_data = []
    cache_info = None
    
    try:
        if 'access_token' in session:
            projects_data = get_projects_cache()
            cache_info = get_cache_info()
            
            print(f"📁 Loaded {len(projects_data)} projects from cache")
            
            if not projects_data:
                print("🔄 Cache is empty, fetching from API...")
                projects_data = op_api.get_all_projects(session['access_token'])
                
                if projects_data:
                    save_projects_cache(projects_data)
                    cache_info = get_cache_info()
                    print(f"✅ Saved {len(projects_data)} projects to cache")
        else:
            print("⚠️ No access token in session")
            
    except Exception as e:
        print(f"❌ Error loading projects: {str(e)}")
        projects_data = get_projects_cache()
        cache_info = get_cache_info()
    
    # محاسبه آمار پروژه‌ها
    stats = {
        'total': len(projects_data),
        'active': len([p for p in projects_data if p.get('active', False)]),
        'not_started': len([p for p in projects_data if p.get('status') == 'not_started']),
        'on_track': len([p for p in projects_data if p.get('status') == 'on_track']),
        'at_risk': len([p for p in projects_data if p.get('status') == 'at_risk']),
        'off_track': len([p for p in projects_data if p.get('status') == 'off_track']),
    }
    
    return render_template('projects.html',
                         settings=settings, 
                         projects=projects_data,
                         cache_info=cache_info,
                         stats=stats,
                         column_settings=column_settings)

@app.route('/projects/refresh')
def refresh_projects():
    """به‌روزرسانی لیست پروژه‌ها از API"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'لطفاً ابتدا وارد شوید'})
    
    try:
        if 'access_token' in session:
            projects_data = op_api.get_all_projects(session['access_token'])
            
            if projects_data:
                save_projects_cache(projects_data)
                
                print(f"✅ Refreshed {len(projects_data)} projects from کاربان")
                flash(f'لیست پروژه‌ها با موفقیت به‌روزرسانی شد ({len(projects_data)} پروژه)', 'success')
                return jsonify({
                    'success': True, 
                    'message': f'لیست پروژه‌ها با موفقیت به‌روزرسانی شد ({len(projects_data)} پروژه)',
                    'count': len(projects_data)
                })
            else:
                return jsonify({'success': False, 'message': 'هیچ پروژه‌ای دریافت نشد'})
        else:
            return jsonify({'success': False, 'message': 'توکن دسترسی معتبر نیست'})
            
    except Exception as e:
        error_msg = f'خطا در به‌روزرسانی پروژه‌ها: {str(e)}'
        print(f"❌ {error_msg}")
        return jsonify({'success': False, 'message': error_msg})

@app.route('/projects/refresh_progress')
def refresh_progress():
    """به‌روزرسانی درصد پیشرفت پروژه‌ها"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'لطفاً ابتدا وارد شوید'})
    
    try:
        if 'access_token' in session:
            updated_count = update_projects_progress(session['access_token'])
            
            if updated_count > 0:
                message = f'پیشرفت {updated_count} پروژه با موفقیت به‌روزرسانی شد'
                flash(message, 'success')
                return jsonify({
                    'success': True, 
                    'message': message,
                    'updated_count': updated_count
                })
            else:
                return jsonify({'success': False, 'message': 'هیچ پروژه‌ای به‌روزرسانی نشد'})
        else:
            return jsonify({'success': False, 'message': 'توکن دسترسی معتبر نیست'})
            
    except Exception as e:
        error_msg = f'خطا در به‌روزرسانی پیشرفت پروژه‌ها: {str(e)}'
        print(f"❌ {error_msg}")
        return jsonify({'success': False, 'message': error_msg})

@app.route('/projects/export')
def export_projects():
    """خروجی اکسل از پروژه‌ها"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'لطفاً ابتدا وارد شوید'})
    
    try:
        projects_data = get_projects_cache()
        
        # ایجاد داده‌های CSV با encoding فارسی
        output = io.StringIO()
        writer = csv.writer(output)
        
        # هدر به فارسی با BOM برای پشتیبانی از UTF-8
        headers = [
            'ردیف', 'ID', 'نام پروژه', 'شناسه', 
            'کد پروژه', 'سطح ولتاژ', 'نوع تابلو', 'تعداد تابلو', 'تعداد سلول',
            'دپارتمان', 'مسئول تیم', 'تیم', 'تاریخ لیست تجهیزات', 'پروژه فوری',
            'وضعیت', 'فعال', 'دسترسی', 
            'تاریخ ایجاد', 'آخرین بروزرسانی', 'لینک پروژه', 'توضیحات', 'پیشرفت (%)'
        ]
        writer.writerow(headers)
        
        # داده‌ها
        for index, project in enumerate(projects_data, 1):
            description = ''
            if project.get('description') and project['description'].get('html'):
                description = clean_html_description(project['description']['html'])
            
            # فیلدهای سفارشی
            project_code = get_custom_field_value(project, '1')
            voltage_level = get_custom_field_value(project, '16')
            panel_type = get_custom_field_value(project, '21')
            panel_count = get_custom_field_value(project, '4')
            cell_count = get_custom_field_value(project, '5')
            department = get_custom_field_value(project, '20')
            team_leader = get_custom_field_value(project, '18')
            team = get_custom_field_value(project, '17')
            equipment_date = get_custom_field_value(project, '8')
            urgent = get_custom_field_value(project, '10')
            
            # درصد پیشرفت
            progress = project.get('progress', {})
            percentage_done = progress.get('percentage_done', 0) if progress else 0
            
            # تبدیل وضعیت به فارسی
            status_fa = ''
            if project.get('status') == 'on_track':
                status_fa = 'در مسیر'
            elif project.get('status') == 'at_risk':
                status_fa = 'در خطر'
            elif project.get('status') == 'off_track':
                status_fa = 'متوقف شده'
            elif project.get('status') == 'not_started':
                status_fa = 'شروع نشده'
            elif project.get('status') == 'finished':
                status_fa = 'تمام شده'
            elif project.get('status') == 'discontinued':
                status_fa = 'رها شده'
            else:
                status_fa = project.get('status', '')
            
            active_fa = 'فعال' if project.get('active') else 'غیرفعال'
            public_fa = 'عمومی' if project.get('public') else 'خصوصی'
            
            # لینک پروژه
            project_link = ''
            if project.get('identifier'):
                project_link = f"{OP_BASE_URL}/projects/{project['identifier']}"
            
            # تبدیل تاریخ‌ها به شمسی
            created_at = convert_to_jalali(project.get('created_at', ''))
            updated_at = convert_to_jalali(project.get('updated_at', ''))
            equipment_date_jalali = convert_to_jalali(equipment_date)
            
            writer.writerow([
                index,
                project.get('id', ''),
                project.get('name', ''),
                project.get('identifier', ''),
                project_code,
                voltage_level,
                panel_type,
                panel_count,
                cell_count,
                department,
                team_leader,
                team,
                equipment_date_jalali,
                'فوری' if urgent == 'true' else 'عادی',
                status_fa,
                active_fa,
                public_fa,
                created_at,
                updated_at,
                project_link,
                description,
                percentage_done
            ])
        
        # ایجاد پاسخ با encoding فارسی
        response = Response(
            output.getvalue().encode('utf-8-sig'),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=projects_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "Content-Type": "text/csv; charset=utf-8-sig"
            }
        )
        
        print(f"✅ Excel export generated for {len(projects_data)} projects")
        return response
        
    except Exception as e:
        error_msg = f'خطا در تولید خروجی: {str(e)}'
        print(f"❌ {error_msg}")
        return jsonify({'success': False, 'message': error_msg})

@app.route('/project/<int:project_id>')
def project_detail(project_id):
    """صفحه جزئیات پروژه"""
    if 'user_id' not in session:
        flash('لطفاً ابتدا وارد شوید', 'error')
        return redirect('/')
    
    settings = get_all_settings()
    
    try:
        if 'access_token' in session:
            response = op_api.get_project_details(session['access_token'], project_id)
            
            if response.status_code == 200:
                project_data = response.json()
                return render_template('project_detail.html', 
                                     settings=settings, 
                                     project=project_data)
            else:
                flash('خطا در دریافت اطلاعات پروژه', 'error')
                return redirect('/projects')
        else:
            flash('توکن دسترسی معتبر نیست', 'error')
            return redirect('/projects')
            
    except Exception as e:
        flash(f'خطا در دریافت اطلاعات پروژه: {str(e)}', 'error')
        return redirect('/projects')

@app.route('/accounts')
def accounts():
    """صفحه حساب‌ها"""
    if 'user_id' not in session:
        flash('لطفاً ابتدا وارد شوید', 'error')
        return redirect('/')
    
    settings = get_all_settings()
    users_data = []
    cache_info = None
    
    try:
        if 'access_token' in session:
            users_data = get_users_cache()
            cache_info = get_users_cache_info()
            
            print(f"📁 Loaded {len(users_data)} users from cache")
            
            if not users_data:
                print("🔄 Cache is empty, fetching from API...")
                users_data = get_all_users(session['access_token'])
                
                if users_data:
                    save_users_cache(users_data)
                    cache_info = get_users_cache_info()
                    print(f"✅ Saved {len(users_data)} users to cache")
        else:
            print("⚠️ No access token in session")
            
    except Exception as e:
        print(f"❌ Error loading users: {str(e)}")
        users_data = get_users_cache()
        cache_info = get_users_cache_info()
    
    # محاسبه آمار کاربران
    stats = {
        'total': len(users_data),
        'active': len([u for u in users_data if u.get('status') == 'active']),
        'locked': len([u for u in users_data if u.get('status') == 'locked']),
        'admin': len([u for u in users_data if u.get('admin', False)]),
        'invited': len([u for u in users_data if u.get('status') == 'invited']),
    }
    
    return render_template('accounts.html', 
                         settings=settings, 
                         users=users_data, 
                         stats=stats,
                         cache_info=cache_info)

@app.route('/accounts/refresh')
def refresh_users():
    """به‌روزرسانی لیست کاربران از API"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'لطفاً ابتدا وارد شوید'})
    
    try:
        if 'access_token' in session:
            users_data = get_all_users(session['access_token'])
            
            if users_data:
                save_users_cache(users_data)
                
                print(f"✅ Refreshed {len(users_data)} users from کاربان")
                flash(f'لیست کاربران با موفقیت به‌روزرسانی شد ({len(users_data)} کاربر)', 'success')
                return jsonify({
                    'success': True, 
                    'message': f'لیست کاربران با موفقیت به‌روزرسانی شد ({len(users_data)} کاربر)',
                    'count': len(users_data)
                })
            else:
                return jsonify({'success': False, 'message': 'هیچ کاربری دریافت نشد'})
        else:
            return jsonify({'success': False, 'message': 'توکن دسترسی معتبر نیست'})
            
    except Exception as e:
        error_msg = f'خطا در به‌روزرسانی کاربران: {str(e)}'
        print(f"❌ {error_msg}")
        return jsonify({'success': False, 'message': error_msg})

@app.route('/reports')
def reports():
    """صفحه گزارش‌ها"""
    if 'user_id' not in session:
        flash('لطفاً ابتدا وارد شوید', 'error')
        return redirect('/')
    
    settings = get_all_settings()
    
    projects_data = get_projects_cache()
    total_projects = len(projects_data)
    active_projects = len([p for p in projects_data if p.get('active', False)])
    public_projects = len([p for p in projects_data if p.get('public', False)])
    
    return render_template('reports.html', 
                         settings=settings, 
                         total_projects=total_projects,
                         active_projects=active_projects,
                         public_projects=public_projects)

@app.route('/logout')
def logout():
    """خروج از سیستم"""
    session.clear()
    flash('خروج موفقیت‌آمیز بود. برای ورود مجدد لطفاً دوباره وارد شوید.', 'info')
    return redirect('/')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                             'favicon.ico', mimetype='image/vnd.microsoft.icon')

# ==================== API Routes ====================

@app.route('/api/projects/stats')
def api_projects_stats():
    """API برای دریافت آمار پروژه‌ها"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        projects_data = get_projects_cache()
        
        stats = {
            'total': len(projects_data),
            'active': len([p for p in projects_data if p.get('active', False)]),
            'public': len([p for p in projects_data if p.get('public', False)]),
            'on_track': len([p for p in projects_data if p.get('status') == 'on_track']),
            'at_risk': len([p for p in projects_data if p.get('status') == 'at_risk']),
            'off_track': len([p for p in projects_data if p.get('status') == 'off_track']),
            'cache_info': get_cache_info()
        }
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== Error Handlers ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html', settings=get_all_settings()), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html', settings=get_all_settings()), 500

if __name__ == '__main__':
    try:
        init_db_safe()
        print("✅ دیتابیس سیستم ایجاد شد")
    except Exception as e:
        print(f"❌ خطا در ایجاد دیتابیس: {str(e)}")
    
    print("🚀 سرور سیستم مدیریت پروژه‌های کاربان در حال اجرا...")
    print("📊 آدرس: http://127.0.0.1:5000")
    print("🔐 ورود از طریق کاربان فعال است")
    
    app.run(debug=True, port=5000)