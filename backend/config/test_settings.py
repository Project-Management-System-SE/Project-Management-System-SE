"""Settings used only when running the test suite.

Production keeps Django's default PBKDF2 password hasher (hundreds of thousands
of iterations, deliberately slow). Tests create hundreds of users, so they use
a fast hasher instead: this cuts the suite from ~10 minutes to ~20 seconds.
Never use this module to serve the application.
"""

from .settings import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
