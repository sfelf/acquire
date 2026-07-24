"""Store historical username-to-user-id mappings for replay tooling.

The mapping remains available to legacy replay tooling while foundational
modules migrate into the installed package.
"""

username_to_user_id: dict[str, int] = {}
