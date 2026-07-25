"""Generate and inline JavaScript enum definitions from Python enum values."""

from __future__ import annotations

import argparse
import collections
import inspect
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never

from acquire import enums

EnumLookup = collections.OrderedDict[str, int]
EnumLookups = dict[str, EnumLookup]
VALID_MODES = ("development", "release")


def get_server_enums() -> EnumLookups:
    """Return enum values declared by the Python server.

    Returns:
        Ordered mappings from enum class name to member name/value pairs.
    """
    lookups: EnumLookups = {}

    for class_name in [obj[0] for obj in inspect.getmembers(enums) if inspect.isclass(obj[1])]:
        class_obj = getattr(enums, class_name)
        lookup: EnumLookup = collections.OrderedDict()
        for name, member in class_obj.__members__.items():
            lookup[name] = member.value
        lookups[class_name] = lookup

    return lookups


def _javascript_files(source_root: Path) -> list[Path]:
    """Return JavaScript inputs from an existing source directory.

    Args:
        source_root: Directory whose direct JavaScript children should be read.

    Returns:
        Sorted JavaScript file paths.

    Raises:
        FileNotFoundError: The source root is not an existing directory.
    """
    if not source_root.is_dir():
        raise FileNotFoundError("JavaScript source root is unavailable")
    return sorted(source_root.glob("*.js"))


def get_pubsub_enums(client_source_root: Path) -> EnumLookup:
    """Return client PubSub enum values inferred from JavaScript sources.

    Server command names are reserved under the `Server_` prefix. Client-side
    names are discovered from the explicit client source root. The generated
    bundle named `main.js` is excluded so source discovery does not depend on a
    previous build.

    Args:
        client_source_root: Directory containing client JavaScript source files.

    Returns:
        Ordered PubSub member name/value pairs.
    """
    lookup: EnumLookup = collections.OrderedDict()

    for name, member in enums.CommandsToClient.__members__.items():
        lookup["Server_" + name] = member.value

    names = set()
    for filename in _javascript_files(client_source_root):
        if filename.name != "main.js":
            contents = filename.read_text()
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


def get_all_enums(client_source_root: Path) -> EnumLookups:
    """Return every enum mapping needed by client generation.

    Args:
        client_source_root: Directory containing client JavaScript source files.

    Returns:
        Mapping from enum class name to ordered member name/value pairs.
    """
    lookups = get_server_enums()
    lookups["PubSub"] = get_pubsub_enums(client_source_root)
    return lookups


def generate_enums_js(
    mode: str,
    client_source_root: Path,
    release_source_root: Path | None = None,
) -> str:
    """Return a CommonJS enum module for the requested build mode.

    Development mode emits all Python and PubSub enums. Release mode scans the
    explicit built-JavaScript root and emits only referenced enum classes,
    preserving the legacy minimized release output.

    Args:
        mode: Either `development` or `release`.
        client_source_root: Directory containing client JavaScript source files.
        release_source_root: Built JavaScript input directory for release mode.

    Returns:
        Generated CommonJS module text, including its final newline.

    Raises:
        ValueError: The mode or release-root combination is invalid.
        FileNotFoundError: A required input directory is unavailable.
    """
    if mode == "release":
        if release_source_root is None:
            raise ValueError("Release generation requires a release source root")
        class_names_set = set()
        for filename in _javascript_files(release_source_root):
            contents = filename.read_text()
            for match in re.finditer(
                r"(?<![A-Za-z0-9])enums\.([A-Za-z0-9]+)(?![A-Za-z0-9])",
                contents,
            ):
                class_names_set.add(match.group(1))
        class_names = sorted(class_names_set)
        class_names_include_str_to_int = {"GameModes", "Options"}
    elif mode == "development":
        if release_source_root is not None:
            raise ValueError("Development generation does not accept a release source root")
        class_names_set = {obj[0] for obj in inspect.getmembers(enums) if inspect.isclass(obj[1])}
        class_names_set.add("PubSub")
        class_names = sorted(class_names_set)
        class_names_include_str_to_int = class_names_set
    else:
        raise ValueError("Invalid enum generation mode")

    parts = []
    all_enums = get_all_enums(client_source_root)

    for class_name in class_names:
        lookups = []
        for name, value in all_enums[class_name].items():
            if class_name in class_names_include_str_to_int:
                lookups.append(f"\t\t{name}: {value}")
            lookups.append(f"\t\t{value}: '{name}'")
        parts.append("\t" + class_name + ": {\n" + ",\n".join(lookups) + "\n\t}")

    return "module.exports = {\n" + ",\n".join(parts) + "\n};\n"


def replace_enums(pathnames: Sequence[Path], client_source_root: Path) -> None:
    """Inline Python enum references in generated JavaScript files.

    All replacement inputs are validated before any file is mutated, preventing
    a missing later input from leaving an earlier file partially processed.
    Object-property expressions such as `other.enums.X` remain untouched.

    Args:
        pathnames: JavaScript files to rewrite.
        client_source_root: Directory containing client JavaScript source files.

    Raises:
        FileNotFoundError: A replacement input is not an existing file.
    """
    if not pathnames or not all(pathname.is_file() for pathname in pathnames):
        raise FileNotFoundError("Enum replacement input is unavailable")

    all_enums = get_all_enums(client_source_root)
    replacements: list[tuple[Path, str]] = []
    for pathname in pathnames:
        contents = pathname.read_text()
        contents = re.sub(
            r"(?<![A-Za-z0-9_.])enums\.([A-Za-z0-9]+)\.([A-Za-z0-9_]+)(?:\.value)?(?![A-Za-z0-9])",
            lambda match: str(all_enums[match.group(1)][match.group(2)]),
            contents,
        )
        replacements.append((pathname, contents))

    for pathname, contents in replacements:
        pathname.write_text(contents)


class EnumArgumentParser(argparse.ArgumentParser):
    """Parse enum commands without reflecting operator-controlled paths.

    Input and output paths can contain private identifiers. Invalid arguments
    therefore use a fixed diagnostic that never includes argparse's generated
    message or the supplied value.
    """

    def error(self, message: str) -> Never:
        """Exit with a fixed invalid-argument diagnostic.

        Args:
            message: Argparse-generated error text, intentionally ignored.
        """
        self.exit(2, "error: invalid arguments\n")


def _require_absolute(parser: EnumArgumentParser, paths: Sequence[Path | None]) -> None:
    """Reject configured paths that are not absolute.

    Args:
        parser: Owning parser used to emit the fixed diagnostic.
        paths: Required or optional path values to validate.
    """
    if any(path is not None and not path.is_absolute() for path in paths):
        parser.error("paths must be absolute")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse and validate the installed enum-generator arguments.

    Generation requires an explicit client source root; release generation also
    requires its built-source root, while development generation rejects that
    option. Replacement requires one or more inputs. Every configured path must
    be absolute before the command performs filesystem work.

    Args:
        argv: Arguments to parse, or `None` to use process arguments.

    Returns:
        Validated argparse namespace for generation or replacement.
    """
    parser = EnumArgumentParser(
        prog="acquire-generate-enums",
        description="Generate or replace JavaScript enum definitions.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)

    js_parser = subparsers.add_parser("js", allow_abbrev=False)
    js_parser.add_argument("mode", choices=VALID_MODES)
    js_parser.add_argument("--client-source-root", required=True, type=Path)
    js_parser.add_argument("--release-source-root", type=Path)
    js_parser.add_argument("--output", type=Path)

    replace_parser = subparsers.add_parser("replace", allow_abbrev=False)
    replace_parser.add_argument("--client-source-root", required=True, type=Path)
    replace_parser.add_argument("pathnames", nargs="+", type=Path)

    args = parser.parse_args(argv)
    configured_paths = [args.client_source_root]
    if args.operation == "js":
        configured_paths.extend((args.release_source_root, args.output))
        if (args.mode == "release") != (args.release_source_root is not None):
            parser.error("invalid mode and release root combination")
    else:
        configured_paths.extend(args.pathnames)
    _require_absolute(parser, configured_paths)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run the installed enum-generator command.

    Successful generation writes to stdout unless an explicit output file is
    supplied. Invalid arguments exit with status 2. Missing inputs, read/write
    failures, and unknown enum references return status 1 with a fixed
    diagnostic that excludes paths and source contents.

    Args:
        argv: Arguments to parse, or `None` to use process arguments.

    Returns:
        `0` on success or `1` after an operational failure.
    """
    args = parse_args(argv)
    try:
        if args.operation == "js":
            contents = generate_enums_js(
                args.mode,
                args.client_source_root,
                args.release_source_root,
            )
            if args.output is None:
                sys.stdout.write(contents)
            else:
                args.output.write_text(contents)
        else:
            replace_enums(args.pathnames, args.client_source_root)
    except Exception:
        print("error: enum generation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
