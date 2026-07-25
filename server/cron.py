"""Compatibility entry point for :mod:`acquire.stats`.

Remove this wrapper in issue #111 after issue #110 installs the final project
scripts.
"""

import sys

from acquire import stats as _stats

if __name__ == "__main__":
    _stats.main()
else:
    sys.modules[__name__] = _stats
