"""Compatibility entry point for :mod:`acquire.migration.import_mysql_to_postgres`.

Remove this wrapper in issue #111 after issue #109 installs the migration
project script.
"""

import sys

from acquire.migration import import_mysql_to_postgres as _import_mysql_to_postgres

if __name__ == "__main__":
    raise SystemExit(_import_mysql_to_postgres.main())
else:
    sys.modules[__name__] = _import_mysql_to_postgres
