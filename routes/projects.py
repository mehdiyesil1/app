from flask import Blueprint, render_template, session, redirect
from utils.database import get_all_settings

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/projects')
def projects():
    """صفحه پروژه‌ها"""
    if 'user_id' not in session:
        return redirect('/')
    
    settings = get_all_settings()
    return render_template('projects.html', settings=settings)
