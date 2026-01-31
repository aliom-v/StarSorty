import os
from slowapi import Limiter
from slowapi.util import get_remote_address

RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
RATE_LIMIT_ADMIN = os.getenv("RATE_LIMIT_ADMIN", "30/minute")
RATE_LIMIT_HEAVY = os.getenv("RATE_LIMIT_HEAVY", "10/minute")

limiter = Limiter(key_func=get_remote_address)
