"""Compatibility entry point for :mod:`acquire.log_tools`.

Remove this wrapper in issue #111 after issue #110 installs the final project
scripts.
"""

import sys

from acquire import log_tools as _log_tools

if __name__ == "__main__":
    _log_tools.main()
else:
    sys.modules[__name__] = _log_tools
