import secrets
import string

ALPHABET = string.ascii_uppercase + string.digits


def generate_license_key(prefix='IGNT'):
    groups = [''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4)]
    return f"{prefix}-{'-'.join(groups)}"
