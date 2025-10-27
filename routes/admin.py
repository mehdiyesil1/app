from flask import Blueprint, render_template, request, flash, redirect, session
from utils.database import get_all_settings, save_setting

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/settings')
def admin_settings():
    """صفحه تنظیمات ادمین"""
    if 'user_id' not in session or not session.get('is_admin'):
        flash('دسترسی غیر مجاز', 'error')
        return redirect('/dashboard')
    
    settings = get_all_settings()
    return render_template('admin_settings.html', settings=settings)

@admin_bp.route('/admin/save_settings', methods=['POST'])
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
            'login_position_x': request.form.get('login_position_x'),
            'login_position_y': request.form.get('login_position_y'),
            'max_login_attempts': request.form.get('max_login_attempts'),
            'lockout_time': request.form.get('lockout_time'),
            'flash_timeout': request.form.get('flash_timeout')
        }
        
        for key, value in settings_to_save.items():
            if value:
                save_setting(key, value)
        
        flash('تنظیمات با موفقیت ذخیره شد', 'success')
        
    except Exception as e:
        flash(f'خطا در ذخیره تنظیمات: {str(e)}', 'error')
    
    return redirect('/admin/settings')
