import sys

from werkzeug.security import generate_password_hash

hash = generate_password_hash(str(sys.argv[1]), method="pbkdf2:sha256", salt_length=8)
print(hash)
