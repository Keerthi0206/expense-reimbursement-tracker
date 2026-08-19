import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# off in tests -- 100+ login calls across the suite would trip a real limit
rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"], enabled=rate_limit_enabled)
