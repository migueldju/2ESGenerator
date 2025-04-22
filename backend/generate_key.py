import secrets

secret_key = secrets.token_hex(32)
print(f"SECRET_KEY={secret_key}")