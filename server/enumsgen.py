"""Generate and inline JavaScript enum definitions from Python enum values.

This module is part of the legacy Python runtime and replay tooling.
"""

import collections
import glob
import inspect
import re
import sys

import enums


def get_server_enums():
    """Return enum values declared by the Python server.

    Returns:
        Ordered mappings from enum class name to member name/value pairs.
    """
    lookups = {}

    for class_name in [obj[0] for obj in inspect.getmembers(enums) if inspect.isclass(obj[1])]:
        class_obj = getattr(enums, class_name)
        lookup = collections.OrderedDict()
        for name, member in class_obj.__members__.items():
            lookup[name] = member.value
        lookups[class_name] = lookup

    return lookups


def get_pubsub_enums():
    """Return client PubSub enum values inferred from JavaScript sources.

    Server command names are reserved under the `Server_` prefix. Client-side
    names are discovered by scanning legacy client JavaScript files, so this
    helper assumes those files exist in the checkout and still reference
    `enums.PubSub` directly.

    Returns:
        Ordered PubSub member name/value pairs.
    """
    lookup = collections.OrderedDict()

    for name, member in enums.CommandsToClient.__members__.items():
        lookup["Server_" + name] = member.value

    names = set()
    for filename in glob.glob("client/main/js/*.js"):
        if filename != "client/main/js/main.js":
            with open(filename) as f:
                contents = f.read()
            for match in re.finditer(
                r"(?<![A-Za-z0-9])enums\.PubSub\.([A-Za-z0-9]+)_([A-Za-z0-9]+)(?![A-Za-z0-9])",
                contents,
            ):
                if match.group(1) != "Server":
                    names.add(match.group(1) + "_" + match.group(2))

    for name in sorted(names):
        lookup[name] = len(lookup)

    lookup["Max"] = len(lookup)

    return lookup


def get_all_enums():
    """Return every enum mapping needed by client generation.

    Returns:
        Mapping from enum class name to ordered member name/value pairs.
    """
    lookups = get_server_enums()
    lookups["PubSub"] = get_pubsub_enums()
    return lookups


def generate_enums_js(mode):
    """Print a CommonJS enum module for the requested build mode.

    Development mode emits all Python and PubSub enums. Release mode scans the
    built JavaScript bundle and emits only enum classes that are referenced
    there, which keeps the generated release asset smaller.

    Args:
        mode: Either `development` or `release`.
    """
    if mode == "release":
        class_names_set = set()
        for filename in glob.glob("dist/build/js/*.js"):
            with open(filename) as f:
                contents = f.read()
            for match in re.finditer(
                r"(?<![A-Za-z0-9])enums\.([A-Za-z0-9]+)(?![A-Za-z0-9])", contents
            ):
                class_names_set.add(match.group(1))
        class_names = sorted(class_names_set)
        class_names_include_str_to_int = {"GameModes", "Options"}
    elif mode == "development":
        class_names_set = {obj[0] for obj in inspect.getmembers(enums) if inspect.isclass(obj[1])}
        class_names_set.add("PubSub")
        class_names = sorted(class_names_set)
        class_names_include_str_to_int = class_names_set
    else:
        raise Exception("invalid mode")

    parts = []

    all_enums = get_all_enums()

    for class_name in class_names:
        lookups = []
        for name, value in all_enums[class_name].items():
            if class_name in class_names_include_str_to_int:
                lookups.append(f"\t\t{name}: {value}")
            lookups.append(f"\t\t{value}: '{name}'")
        parts.append("\t" + class_name + ": {\n" + ",\n".join(lookups) + "\n\t}")

    print("module.exports = {")
    print(",\n".join(parts))
    print("};")


def replace_enums(pathnames):
    """Inline Python enum references in generated JavaScript files.

    This mutates files in place and is intended for release output, not source
    files. The replacement deliberately avoids object-property expressions such
    as `other.enums.X` so only global enum references are rewritten.

    Args:
        pathnames: JavaScript files to rewrite.
    """
    all_enums = get_all_enums()
    for pathname in pathnames:
        with open(pathname) as f:
            contents = f.read()
        contents = re.sub(
            r"(?<![A-Za-z0-9_.])enums\.([A-Za-z0-9]+)\.([A-Za-z0-9_]+)(?:\.value)?(?![A-Za-z0-9])",
            lambda match: str(all_enums[match.group(1)][match.group(2)]),
            contents,
        )
        with open(pathname, "w") as f:
            f.write(contents)


if __name__ == "__main__":
    if sys.argv[1] == "js":
        generate_enums_js(sys.argv[2])
    elif sys.argv[1] == "replace":
        replace_enums(sys.argv[2:])
