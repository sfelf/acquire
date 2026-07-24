"""Compatibility alias for :mod:`acquire.settings`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

import sys

from acquire import settings as _settings

sys.modules[__name__] = _settings
