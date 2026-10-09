import datetime
from flask import Blueprint, request, jsonify
from ..db import get_db
from ..auth import require_admin
from ..keygen import generate_license_key

bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ---------- Dashboard stats ----------
@bp.route('/stats', methods=['GET'])
@require_admin
def stats():
    conn = get_db()
    total_customers = conn.execute('SELECT COUNT(*) n FROM customers').fetchone()['n']
    total_licenses = conn.execute('SELECT COUNT(*) n FROM licenses').fetchone()['n']
    active_licenses = conn.execute("SELECT COUNT(*) n FROM licenses WHERE status = 'active'").fetchone()['n']
    revoked_licenses = conn.execute("SELECT COUNT(*) n FROM licenses WHERE status = 'revoked'").fetchone()['n']
    expiring_soon = conn.execute(
        "SELECT COUNT(*) n FROM licenses WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at <= datetime('now', '+7 days')"
    ).fetchone()['n']
    total_activations = conn.execute('SELECT COUNT(*) n FROM activations WHERE revoked = 0').fetchone()['n']
    conn.close()

    return jsonify({
        'totalCustomers': total_customers,
        'totalLicenses': total_licenses,
        'activeLicenses': active_licenses,
        'revokedLicenses': revoked_licenses,
        'expiringSoon': expiring_soon,
        'totalActivations': total_activations,
    })


# ---------- Customers ----------
@bp.route('/customers', methods=['GET'])
@require_admin
def list_customers():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*, COUNT(l.id) AS license_count
        FROM customers c LEFT JOIN licenses l ON l.customer_id = c.id
        GROUP BY c.id ORDER BY c.created_at DESC
    """).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@bp.route('/customers', methods=['POST'])
@require_admin
def create_customer():
    data = request.get_json(silent=True) or {}
    name, email = data.get('name'), data.get('email')
    if not name or not email:
        return jsonify({'error': 'name and email are required'}), 400

    conn = get_db()
    try:
        cur = conn.execute(
            'INSERT INTO customers (name, email, phone, notes) VALUES (?, ?, ?, ?)',
            (name, email, data.get('phone'), data.get('notes'))
        )
        conn.commit()
        row = conn.execute('SELECT * FROM customers WHERE id = ?', (cur.lastrowid,)).fetchone()
        return jsonify(row_to_dict(row))
    except Exception as e:
        msg = 'Email already exists' if 'UNIQUE' in str(e) else str(e)
        return jsonify({'error': msg}), 400
    finally:
        conn.close()


@bp.route('/customers/<int:customer_id>', methods=['DELETE'])
@require_admin
def delete_customer(customer_id):
    conn = get_db()
    conn.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ---------- Licenses ----------
@bp.route('/licenses', methods=['GET'])
@require_admin
def list_licenses():
    conn = get_db()
    rows = conn.execute("""
        SELECT l.*, c.name AS customer_name, c.email AS customer_email,
          (SELECT COUNT(*) FROM activations a WHERE a.license_id = l.id AND a.revoked = 0) AS active_devices
        FROM licenses l JOIN customers c ON c.id = l.customer_id
        ORDER BY l.issued_at DESC
    """).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@bp.route('/licenses', methods=['POST'])
@require_admin
def create_license():
    data = request.get_json(silent=True) or {}
    customer_id = data.get('customer_id')
    if not customer_id:
        return jsonify({'error': 'customer_id is required'}), 400

    conn = get_db()
    customer = conn.execute('SELECT * FROM customers WHERE id = ?', (customer_id,)).fetchone()
    if not customer:
        conn.close()
        return jsonify({'error': 'Customer not found'}), 404

    key = generate_license_key()
    while conn.execute('SELECT 1 FROM licenses WHERE license_key = ?', (key,)).fetchone():
        key = generate_license_key()

    expires_in_days = data.get('expires_in_days')
    expires_at = None
    if expires_in_days:
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=float(expires_in_days))).isoformat()

    cur = conn.execute(
        'INSERT INTO licenses (license_key, customer_id, plan, max_devices, expires_at) VALUES (?, ?, ?, ?, ?)',
        (key, customer_id, data.get('plan', 'standard'), data.get('max_devices', 1), expires_at)
    )
    conn.commit()
    row = conn.execute('SELECT * FROM licenses WHERE id = ?', (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@bp.route('/licenses/<int:license_id>/revoke', methods=['POST'])
@require_admin
def revoke_license(license_id):
    conn = get_db()
    conn.execute("UPDATE licenses SET status = 'revoked' WHERE id = ?", (license_id,))
    conn.execute('INSERT INTO activity_log (license_id, event) VALUES (?, ?)', (license_id, 'admin_revoke'))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/licenses/<int:license_id>/reactivate', methods=['POST'])
@require_admin
def reactivate_license(license_id):
    conn = get_db()
    conn.execute("UPDATE licenses SET status = 'active' WHERE id = ?", (license_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@bp.route('/licenses/<int:license_id>/extend', methods=['POST'])
@require_admin
def extend_license(license_id):
    data = request.get_json(silent=True) or {}
    days = float(data.get('days', 30))

    conn = get_db()
    license_row = conn.execute('SELECT * FROM licenses WHERE id = ?', (license_id,)).fetchone()
    if not license_row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    now = datetime.datetime.utcnow()
    if license_row['expires_at']:
        current_expiry = datetime.datetime.fromisoformat(license_row['expires_at'])
        base = current_expiry if current_expiry > now else now
    else:
        base = now

    new_expiry = (base + datetime.timedelta(days=days)).isoformat()
    conn.execute('UPDATE licenses SET expires_at = ? WHERE id = ?', (new_expiry, license_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'expires_at': new_expiry})


@bp.route('/licenses/<int:license_id>', methods=['DELETE'])
@require_admin
def delete_license(license_id):
    conn = get_db()
    conn.execute('DELETE FROM licenses WHERE id = ?', (license_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ---------- Activations (devices) ----------
@bp.route('/licenses/<int:license_id>/activations', methods=['GET'])
@require_admin
def list_activations(license_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM activations WHERE license_id = ? ORDER BY activated_at DESC', (license_id,)
    ).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@bp.route('/activations/<int:activation_id>/revoke', methods=['POST'])
@require_admin
def revoke_activation(activation_id):
    conn = get_db()
    conn.execute('UPDATE activations SET revoked = 1 WHERE id = ?', (activation_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
