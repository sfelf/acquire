"""Compatibility exports for :mod:`acquire.username_to_user_id`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

from acquire.username_to_user_id import username_to_user_id

__all__ = ["username_to_user_id"]
