"""Compatibility exports for :mod:`acquire.settings`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

from acquire.settings import util__get_log_file_filenames__path_prefixes

__all__ = ["util__get_log_file_filenames__path_prefixes"]
