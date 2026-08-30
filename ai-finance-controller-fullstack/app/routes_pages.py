from flask import Blueprint, render_template, redirect, url_for, request

from .security import login_required, is_logged_in

bp = Blueprint('pages', __name__)


@bp.get('/')
def home():
    return render_template('home.html')


@bp.get('/register')
def register_page():
    if is_logged_in():
        return redirect(url_for('pages.dashboard_page'))
    return render_template('register.html')


@bp.get('/login')
def login_page():
    if is_logged_in():
        return redirect(url_for('pages.dashboard_page'))
    next_path = request.args.get('next', '')
    return render_template('login.html', next_path=next_path)


@bp.get('/forgot-password')
def forgot_password_page():
    return render_template('forgot_password.html')


@bp.get('/reset-password')
def reset_password_page():
    token = request.args.get('token', '')
    uid = request.args.get('uid', '')
    return render_template('reset_password.html', token=token, uid=uid)


@bp.get('/dashboard')
@login_required
def dashboard_page():
    return render_template('dashboard.html')


@bp.get('/reconciliation')
@login_required
def reconciliation_page():
    return render_template('reconciliation.html')


@bp.get('/history')
@login_required
def history_page():
    return render_template('history.html')


@bp.get('/settings')
@login_required
def settings_page():
    return render_template('settings.html')
