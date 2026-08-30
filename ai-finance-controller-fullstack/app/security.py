"""
Real server-side authentication: Werkzeug's scrypt-based password hashing
(not a demo stub), Flask's signed session cookie for login state, and a
login_required decorator that protects routes at the SERVER — unlike the
earlier client-only build, a user can't just flip a sessionStorage flag in
devtools to bypass this, because the check happens before any protected
page or API response is ever sent.
"""
import re
from functools import wraps
from flask import session, redirect, url_for, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def validate_registration(email, username, password):
    """Returns a list of error strings; empty list means valid."""
    errors = []
    if not email or not EMAIL_RE.match(email):
        errors.append('Enter a valid email address.')
    if not username or len(username.strip()) < 3:
        errors.append('Username must be at least 3 characters.')
    if not password or len(password) < 8:
        errors.append('Password must be at least 8 characters.')
    return errors


def login_user(user_row):
    session.clear()
    session['user_id'] = user_row['id']
    session['username'] = user_row['username']


def logout_user():
    session.clear()


def current_user_id():
    return session.get('user_id')


def is_logged_in():
    return 'user_id' in session


def login_required(view_func):
    """Protects an HTML page route — redirects to the login page if not signed in."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('pages.login_page', next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


def api_login_required(view_func):
    """Protects a JSON API route — returns 401 instead of redirecting."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not is_logged_in():
            return jsonify({'error': 'Not authenticated'}), 401
        return view_func(*args, **kwargs)
    return wrapped
