"""Compatibility alias for :mod:`acquire.auth`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

import sys

from acquire import auth as _auth

sys.modules[__name__] = _auth
