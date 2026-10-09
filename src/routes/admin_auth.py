import bcrypt
from flask import Blueprint, request, jsonify
from ..db import get_db
from ..auth import sign_admin_token

bp = Blueprint('admin_auth', __name__, url_prefix='/api/admin/auth')


@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Missing credentials'}), 400

    conn = get_db()
    admin = conn.execute('SELECT * FROM admins WHERE email = ?', (email,)).fetchone()
    conn.close()

    if not admin or not bcrypt.checkpw(password.encode(), admin['password_hash'].encode()):
        return jsonify({'error': 'Invalid email or password'}), 401

    return jsonify({'token': sign_admin_token(admin), 'email': admin['email']})
