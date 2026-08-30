import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

from .db import get_db, now_iso
from .security import validate_registration, login_user, logout_user, current_user_id, is_logged_in
from .email_stub import send_reset_email

bp = Blueprint('auth', __name__, url_prefix='/api/auth')

RESET_TOKEN_TTL_MINUTES = 30


@bp.post('/register')
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    errors = validate_registration(email, username, password)
    if errors:
        return jsonify({'errors': errors}), 400

    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE email = ? OR username = ?', (email, username)).fetchone()
    if existing:
        db.close()
        return jsonify({'errors': ['An account with that email or username already exists.']}), 409

    password_hash = generate_password_hash(password)
    cur = db.execute(
        'INSERT INTO users (email, username, password_hash, created_at) VALUES (?, ?, ?, ?)',
        (email, username, password_hash, now_iso()),
    )
    db.commit()
    user_id = cur.lastrowid
    user_row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    db.close()

    login_user(user_row)
    return jsonify({'username': username, 'email': email})


@bp.post('/login')
def login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get('username') or data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not identifier or not password:
        return jsonify({'errors': ['Enter your username/email and password.']}), 400

    db = get_db()
    user_row = db.execute(
        'SELECT * FROM users WHERE lower(email) = ? OR lower(username) = ?', (identifier, identifier)
    ).fetchone()
    db.close()

    if not user_row or not check_password_hash(user_row['password_hash'], password):
        return jsonify({'errors': ['Incorrect username/email or password.']}), 401

    login_user(user_row)
    return jsonify({'username': user_row['username'], 'email': user_row['email']})


@bp.post('/logout')
def logout():
    logout_user()
    return jsonify({'ok': True})


@bp.get('/me')
def me():
    if not is_logged_in():
        return jsonify({'authenticated': False})
    db = get_db()
    user_row = db.execute('SELECT username, email FROM users WHERE id = ?', (current_user_id(),)).fetchone()
    db.close()
    if not user_row:
        logout_user()
        return jsonify({'authenticated': False})
    return jsonify({'authenticated': True, 'username': user_row['username'], 'email': user_row['email']})


@bp.post('/forgot-password')
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()

    db = get_db()
    user_row = db.execute('SELECT * FROM users WHERE lower(email) = ?', (email,)).fetchone()

    # Always return the same generic response whether or not the email
    # exists — this prevents using "forgot password" to discover which
    # emails have accounts (a real, if small, product security practice).
    generic_response = {'message': 'If an account exists for that email, a reset link has been generated.'}

    if not user_row:
        db.close()
        return jsonify(generic_response)

    raw_token = secrets.token_urlsafe(32)
    token_hash = generate_password_hash(raw_token)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)).isoformat()

    db.execute(
        'INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, used, created_at) VALUES (?, ?, ?, 0, ?)',
        (user_row['id'], token_hash, expires_at, now_iso()),
    )
    db.commit()
    db.close()

    reset_url = f'/reset-password?token={raw_token}&uid={user_row["id"]}'
    send_reset_email(email, reset_url)

    # Demo-only: also return the link directly since no real SMTP is
    # configured (see app/email_stub.py for the honesty note on this).
    generic_response['demo_reset_link'] = reset_url
    return jsonify(generic_response)


@bp.post('/reset-password')
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get('token') or ''
    user_id = data.get('uid')
    new_password = data.get('password') or ''

    if not token or not user_id:
        return jsonify({'errors': ['Invalid or missing reset link.']}), 400
    if len(new_password) < 8:
        return jsonify({'errors': ['Password must be at least 8 characters.']}), 400

    db = get_db()
    rows = db.execute(
        'SELECT * FROM password_reset_tokens WHERE user_id = ? AND used = 0 ORDER BY id DESC', (user_id,)
    ).fetchall()

    matching_row = None
    for row in rows:
        if check_password_hash(row['token_hash'], token):
            matching_row = row
            break

    if not matching_row:
        db.close()
        return jsonify({'errors': ['This reset link is invalid or has already been used.']}), 400

    expires_at = datetime.fromisoformat(matching_row['expires_at'])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        db.close()
        return jsonify({'errors': ['This reset link has expired. Request a new one.']}), 400

    new_hash = generate_password_hash(new_password)
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user_id))
    db.execute('UPDATE password_reset_tokens SET used = 1 WHERE id = ?', (matching_row['id'],))
    db.commit()
    db.close()

    return jsonify({'ok': True})


@bp.post('/change-password')
def change_password():
    if not is_logged_in():
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''

    if len(new_password) < 8:
        return jsonify({'errors': ['New password must be at least 8 characters.']}), 400

    db = get_db()
    user_row = db.execute('SELECT * FROM users WHERE id = ?', (current_user_id(),)).fetchone()
    if not user_row or not check_password_hash(user_row['password_hash'], current_password):
        db.close()
        return jsonify({'errors': ['Current password is incorrect.']}), 400

    new_hash = generate_password_hash(new_password)
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user_row['id']))
    db.commit()
    db.close()

    return jsonify({'ok': True})
