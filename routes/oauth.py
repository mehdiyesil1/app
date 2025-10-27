from flask import Blueprint, redirect, request, session, flash, render_template
from utils.openproject import op_api, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI
from utils.database import check_user_lock, increment_login_attempt, reset_login_attempts, get_all_settings
import secrets

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login')
def login():
    """صفحه لاگین"""
    settings = get_all_settings()
    return render_template('login.html', settings=settings)

@auth_bp.route('/auth/start')
def auth_start():
    """شروع فرآیند OAuth"""
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    
    auth_url = op_api.get_authorization_url(CLIENT_ID, REDIRECT_URI)
    print(f"🔗 Redirecting to OpenProject: {auth_url}")
    return redirect(auth_url)

@auth_bp.route('/')
def index():
    """صفحه اصلی - پردازش callback"""
    code = request.args.get('code')
    
    if code:
        return process_callback(code)
    
    if 'user_id' in session:
        return redirect('/dashboard')
    
    settings = get_all_settings()
    return render_template('login.html', settings=settings)

def process_callback(code):
    """پردازش callback OpenProject"""
    try:
        print(f"🎯 Processing callback with code: {code}")
        
        # دریافت access token
        token_response = op_api.get_token_with_code(
            code, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI
        )
        
        print(f"🔐 Token response status: {token_response.status_code}")
        
        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token')
            
            if access_token:
                print(f"✅ Access token received: {access_token[:20]}...")
                
                # دریافت اطلاعات کاربر
                user_response = op_api.get_user_info(access_token)
                print(f"👤 User info response status: {user_response.status_code}")
                
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    username = user_data.get('login', '')
                    user_name = user_data.get('name', username)
                    
                    print(f"✅ User data received: {user_name} (ID: {user_data.get('id')})")
                    
                    if not username:
                        flash('خطا: اطلاعات کاربر نامعتبر است', 'error')
                        return redirect('/')
                    
                    # بررسی قفل بودن کاربر
                    is_locked, locked_until = check_user_lock(username)
                    if is_locked:
                        flash(f'حساب شما تا {locked_until.strftime("%H:%M")} قفل شده است', 'error')
                        return redirect('/')
                    
                    # ریست کردن تلاش‌های ناموفق
                    reset_login_attempts(username)
                    
                    # ذخیره اطلاعات در session
                    session['user_id'] = user_data.get('id')
                    session['username'] = username
                    session['email'] = user_data.get('email', '')
                    session['full_name'] = user_name
                    session['access_token'] = access_token
                    session['is_authenticated'] = True
                    session['is_admin'] = True  # برای تست
                    
                    print(f"✅ Login successful for: {username}")
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
            
            # افزایش تعداد تلاش‌های ناموفق
            if 'username' in session:
                increment_login_attempt(session['username'])
            
            flash(f'خطا: {error_msg}', 'error')
            
    except Exception as e:
        print(f"❌ Callback exception: {str(e)}")
        flash(f'خطا در ارتباط با سرور: {str(e)}', 'error')
    
    return redirect('/')

@auth_bp.route('/logout')
def logout():
    """خروج از سیستم"""
    session.clear()
    flash('خروج موفقیت‌آمیز بود', 'info')
    return redirect('/')
