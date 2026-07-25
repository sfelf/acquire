"""Compatibility alias for :mod:`acquire.recreate_game`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

import sys

from acquire import recreate_game as _recreate_game

sys.modules[__name__] = _recreate_game
