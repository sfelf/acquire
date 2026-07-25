"""Compatibility entry point for :mod:`acquire.http_server`.

Remove this wrapper in issue #111 after issue #110 moves startup commands to an
installed project script.
"""

import sys

from acquire import http_server as _http_server

if __name__ == "__main__":
    raise SystemExit(_http_server.main())
else:
    sys.modules[__name__] = _http_server
