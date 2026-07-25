"""Compatibility entry point for :mod:`acquire.setup_database`.

Remove this wrapper in issue #111 after issue #110 moves callers to the
installed database-setup project script.
"""

import sys

from acquire import setup_database as _setup_database

if __name__ == "__main__":
    raise SystemExit(_setup_database.main())
else:
    sys.modules[__name__] = _setup_database
