"""Compatibility exports for :mod:`acquire.util`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

from acquire.util import (
    _log_type_to_log_file_filenames,
    get_log_file_filenames,
    open_possibly_gzipped_file,
    re_gzip_filename,
    re_timestamp_in_path,
)

__all__ = [
    "_log_type_to_log_file_filenames",
    "get_log_file_filenames",
    "open_possibly_gzipped_file",
    "re_gzip_filename",
    "re_timestamp_in_path",
]
