"""Compatibility entry point for :mod:`acquire.migration.validate_import_reports`.

Remove this wrapper in issue #111 after migration callers use installed package
paths.
"""

import sys

from acquire.migration import validate_import_reports as _validate_import_reports

if __name__ == "__main__":
    raise SystemExit(_validate_import_reports.main())
else:
    sys.modules[__name__] = _validate_import_reports
