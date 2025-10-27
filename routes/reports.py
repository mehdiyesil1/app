from flask import Blueprint, render_template, session, redirect
from utils.database import get_all_settings

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/reports')
def reports():
    """صفحه گزارش‌ها"""
    if 'user_id' not in session:
        return redirect('/')
    
    settings = get_all_settings()
    return render_template('reports.html', settings=settings)
