import json
import datetime
from flask import Blueprint, request, jsonify
from ..db import get_db
from ..auth import require_app_key

bp = Blueprint('license', __name__, url_prefix='/api/license')


def get_license_by_key(conn, key):
    return conn.execute('SELECT * FROM licenses WHERE license_key = ?', (key,)).fetchone()


def is_expired(license_row):
    if not license_row['expires_at']:
        return False
    return datetime.datetime.fromisoformat(license_row['expires_at']) < datetime.datetime.utcnow()


def log(conn, license_id, event, detail=None):
    conn.execute(
        'INSERT INTO activity_log (license_id, event, detail) VALUES (?, ?, ?)',
        (license_id, event, json.dumps(detail) if detail else None)
    )


@bp.route('/activate', methods=['POST'])
@require_app_key
def activate():
    data = request.get_json(silent=True) or {}
    license_key = data.get('license_key')
    device_id = data.get('device_id')
    device_name = data.get('device_name')

    if not license_key or not device_id:
        return jsonify({'ok': False, 'reason': 'missing_fields'}), 400

    conn = get_db()
    license_row = get_license_by_key(conn, license_key)
    if not license_row:
        conn.close()
        return jsonify({'ok': False, 'reason': 'not_found'}), 404
    if license_row['status'] == 'revoked':
        conn.close()
        return jsonify({'ok': False, 'reason': 'revoked'}), 403
    if is_expired(license_row):
        conn.close()
        return jsonify({'ok': False, 'reason': 'expired'}), 403

    existing = conn.execute(
        'SELECT * FROM activations WHERE license_id = ? AND device_id = ?',
        (license_row['id'], device_id)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE activations SET last_seen_at = datetime('now'), revoked = 0, device_name = ? WHERE id = ?",
            (device_name or existing['device_name'], existing['id'])
        )
        log(conn, license_row['id'], 'reactivate', {'device_id': device_id})
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'status': 'already_activated', 'expires_at': license_row['expires_at']})

    active_count = conn.execute(
        'SELECT COUNT(*) AS n FROM activations WHERE license_id = ? AND revoked = 0',
        (license_row['id'],)
    ).fetchone()['n']

    if active_count >= license_row['max_devices']:
        log(conn, license_row['id'], 'activate_blocked_device_limit', {'device_id': device_id, 'activeCount': active_count})
        conn.commit()
        conn.close()
        return jsonify({'ok': False, 'reason': 'device_limit_reached', 'max_devices': license_row['max_devices']}), 403

    conn.execute(
        'INSERT INTO activations (license_id, device_id, device_name) VALUES (?, ?, ?)',
        (license_row['id'], device_id, device_name)
    )
    log(conn, license_row['id'], 'activate', {'device_id': device_id, 'device_name': device_name})
    conn.commit()
    conn.close()

    return jsonify({'ok': True, 'status': 'activated', 'expires_at': license_row['expires_at'], 'plan': license_row['plan']})


@bp.route('/validate', methods=['POST'])
@require_app_key
def validate():
    data = request.get_json(silent=True) or {}
    license_key = data.get('license_key')
    device_id = data.get('device_id')

    if not license_key or not device_id:
        return jsonify({'ok': False, 'reason': 'missing_fields'}), 400

    conn = get_db()
    license_row = get_license_by_key(conn, license_key)
    if not license_row:
        conn.close()
        return jsonify({'ok': False, 'reason': 'not_found'}), 404

    activation = conn.execute(
        'SELECT * FROM activations WHERE license_id = ? AND device_id = ?',
        (license_row['id'], device_id)
    ).fetchone()

    if not activation or activation['revoked']:
        conn.close()
        return jsonify({'ok': False, 'reason': 'device_not_activated'}), 403
    if license_row['status'] == 'revoked':
        conn.close()
        return jsonify({'ok': False, 'reason': 'revoked'}), 403
    if is_expired(license_row):
        conn.close()
        return jsonify({'ok': False, 'reason': 'expired'}), 403

    conn.execute("UPDATE activations SET last_seen_at = datetime('now') WHERE id = ?", (activation['id'],))
    conn.execute("UPDATE licenses SET last_checked_at = datetime('now') WHERE id = ?", (license_row['id'],))
    conn.commit()
    conn.close()

    return jsonify({'ok': True, 'status': 'valid', 'expires_at': license_row['expires_at'], 'plan': license_row['plan']})
