"""Print new private setup keys. Do not commit the output."""
import base64
import secrets
print('APP_ACCESS_KEY=' + secrets.token_urlsafe(36))
print('SETTINGS_ENCRYPTION_KEY=' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
