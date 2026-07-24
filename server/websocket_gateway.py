"""Compatibility alias for :mod:`acquire.realtime`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

import sys

from acquire import realtime as _realtime

sys.modules[__name__] = _realtime
