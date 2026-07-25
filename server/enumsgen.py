"""Compatibility entry point for :mod:`acquire.enumsgen`.

Remove this wrapper in issue #111 after issue #110 migrates all enum-generation
callers to the installed project script.
"""

import sys

from acquire import enumsgen as _enumsgen

if __name__ == "__main__":
    raise SystemExit(_enumsgen.main())
else:
    sys.modules[__name__] = _enumsgen
