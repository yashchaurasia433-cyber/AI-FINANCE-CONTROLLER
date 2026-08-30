import os
import secrets
from flask import Flask

from .db import init_db


def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, 'templates'),
        static_folder=os.path.join(base_dir, 'static'),
    )

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024  # 25MB upload ceiling

    # Change this to your real repo URL once you push to GitHub (or set
    # the GITHUB_URL environment variable) — it's read once here and
    # injected into every template via the context processor below, so
    # there's exactly one place to update it rather than eight.
    app.config['GITHUB_URL'] = os.environ.get('GITHUB_URL', 'https://github.com/yashchaurasia433-cyber/ai-finance-controller')

    init_db()

    from . import routes_pages, routes_auth, routes_api
    app.register_blueprint(routes_pages.bp)
    app.register_blueprint(routes_auth.bp)
    app.register_blueprint(routes_api.bp)

    @app.context_processor
    def inject_github_url():
        return {'github_url': app.config['GITHUB_URL']}

    return app
