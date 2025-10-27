from flask import Blueprint, render_template, session, redirect
from utils.database import get_all_settings

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
def dashboard():
    """صفحه داشبورد"""
    if 'user_id' not in session:
        return redirect('/')
    
    settings = get_all_settings()
    return render_template('dashboard.html', settings=settings)
