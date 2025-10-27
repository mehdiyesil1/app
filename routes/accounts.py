[file name]: accounts.py
[file content begin]
from flask import Blueprint, render_template, session, redirect, jsonify, flash
from utils.database import get_all_settings
import requests
import json
from app import get_complete_user_profile, extract_user_custom_fields, get_user_custom_field_value, OP_BASE_URL

accounts_bp = Blueprint('accounts', __name__)

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

@accounts_bp.route('/accounts')
def accounts():
    """صفحه حساب‌ها"""
    if 'user_id' not in session:
        return redirect('/')
    
    settings = get_all_settings()
    users_data = []
    
    try:
        if 'access_token' in session:
            users_data = get_all_users(session['access_token'])
            print(f"📁 Loaded {len(users_data)} users from API")
        else:
            print("⚠️ No access token in session")
            
    except Exception as e:
        print(f"❌ Error loading users: {str(e)}")
    
    # محاسبه آمار کاربران
    stats = {
        'total': len(users_data),
        'active': len([u for u in users_data if u.get('status') == 'active']),
        'locked': len([u for u in users_data if u.get('status') == 'locked']),
        'admin': len([u for u in users_data if u.get('admin', False)]),
        'invited': len([u for u in users_data if u.get('status') == 'invited']),
    }
    
    return render_template('accounts.html', settings=settings, users=users_data, stats=stats)

@accounts_bp.route('/accounts/refresh')
def refresh_users():
    """به‌روزرسانی لیست کاربران از API"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'لطفاً ابتدا وارد شوید'})
    
    try:
        if 'access_token' in session:
            users_data = get_all_users(session['access_token'])
            
            if users_data:
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
[file content end]