import os
import threading
import time
from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from .db import init_db, get_db
from .routes.license import bp as license_bp
from .routes.admin_auth import bp as admin_auth_bp
from .routes.admin import bp as admin_bp

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')


def sweep_expired():
    while True:
        try:
            conn = get_db()
            conn.execute(
                "UPDATE licenses SET status = 'expired' "
                "WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at < datetime('now')"
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print('sweep_expired error:', e)
        time.sleep(3600)  # hourly


def create_app():
    app = Flask(__name__, static_folder=None)
    CORS(app)

    app.register_blueprint(license_bp)
    app.register_blueprint(admin_auth_bp)
    app.register_blueprint(admin_bp)

    # Static site: download page (/) + admin dashboard (/admin) + installer downloads
    @app.route('/')
    def index():
        return send_from_directory(PUBLIC_DIR, 'index.html')

    @app.route('/admin/')
    @app.route('/admin')
    def admin_dashboard():
        return send_from_directory(os.path.join(PUBLIC_DIR, 'admin'), 'index.html')

    @app.route('/downloads/<path:filename>')
    def downloads(filename):
        return send_from_directory(os.path.join(PUBLIC_DIR, 'downloads'), filename)

    @app.route('/<path:filename>')
    def static_files(filename):
        return send_from_directory(PUBLIC_DIR, filename)

    return app


init_db()
app = create_app()

# Auto-expire licenses in the background, same as the hourly sweep in the Node version
threading.Thread(target=sweep_expired, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    print(f'Botmaster license server running on http://localhost:{port}')
    print(f'  Download page: http://localhost:{port}/')
    print(f'  Admin dashboard: http://localhost:{port}/admin')
    app.run(host='0.0.0.0', port=port, debug=False)
