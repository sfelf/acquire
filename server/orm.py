"""Compatibility alias for :mod:`acquire.orm`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

import sys

from acquire import orm as _orm

sys.modules[__name__] = _orm
