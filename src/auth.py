import os
import jwt
from functools import wraps
from flask import request, jsonify, current_app, g

SECRET = os.environ.get('JWT_SECRET', 'change-this-secret-before-deploying')


def sign_admin_token(admin):
    import datetime
    payload = {
        'id': admin['id'],
        'email': admin['email'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=12)
    }
    return jwt.encode(payload, SECRET, algorithm='HS256')


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        token = header[7:] if header.startswith('Bearer ') else None
        if not token:
            return jsonify({'error': 'Missing token'}), 401
        try:
            g.admin = jwt.decode(token, SECRET, algorithms=['HS256'])
        except jwt.PyJWTError:
            return jsonify({'error': 'Invalid or expired token'}), 401
        return fn(*args, **kwargs)
    return wrapper



def require_app_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        app_key = request.headers.get('X-App-Key')
        expected = os.environ.get('APP_API_KEY')
        if not expected or app_key != expected:
            return jsonify({'error': 'Unauthorized client'}), 401
        return fn(*args, **kwargs)
    return wrapper
