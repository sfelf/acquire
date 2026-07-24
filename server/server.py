"""Compatibility entry point for :mod:`acquire.game_server`.

Remove this wrapper in issue #111 after all runtime and offline callers use the
installed package.
"""

import sys

from acquire import game_server as _game_server

if __name__ == "__main__":
    _game_server.main()
else:
    sys.modules[__name__] = _game_server
