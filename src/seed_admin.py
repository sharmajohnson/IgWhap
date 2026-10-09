# Creates (or resets) the first admin login for the dashboard.
# Usage: python -m src.seed_admin admin@example.com "StrongPassword123"
import sys
import bcrypt
from dotenv import load_dotenv
from .db import get_db, init_db

load_dotenv()


def main():
    if len(sys.argv) < 3:
        print('Usage: python -m src.seed_admin <email> <password>')
        sys.exit(1)

    email, password = sys.argv[1], sys.argv[2]
    init_db()

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_db()
    existing = conn.execute('SELECT id FROM admins WHERE email = ?', (email,)).fetchone()

    if existing:
        conn.execute('UPDATE admins SET password_hash = ? WHERE email = ?', (password_hash, email))
        print(f'Password updated for {email}')
    else:
        conn.execute('INSERT INTO admins (email, password_hash) VALUES (?, ?)', (email, password_hash))
        print(f'Admin created: {email}')

    conn.commit()
    conn.close()


if __name__ == '__main__':
    main()
