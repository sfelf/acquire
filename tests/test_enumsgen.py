import hashlib
from pathlib import Path

import enumsgen
import pytest

from acquire.enums import CommandsToClient, GameModes, Options

pytestmark = pytest.mark.unit
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLIENT_SOURCE_ROOT = REPOSITORY_ROOT / "client" / "main" / "js"


@pytest.fixture
def client_source_root(tmp_path):
    root = tmp_path / "client" / "main" / "js"
    root.mkdir(parents=True)
    (root / "app.js").write_text("enums.PubSub.Client_Started\n")
    return root


def test_get_server_enums_returns_ordered_enum_values():
    server_enums = enumsgen.get_server_enums()

    assert server_enums["CommandsToClient"]["FatalError"] == CommandsToClient.FatalError.value
    assert server_enums["CommandsToClient"]["DestroyGame"] == CommandsToClient.DestroyGame.value
    assert server_enums["GameModes"]["Singles"] == GameModes.Singles.value


def test_get_pubsub_enums_includes_server_commands_and_client_events(
    tmp_path,
):
    client_js_dir = tmp_path / "client" / "main" / "js"
    client_js_dir.mkdir(parents=True)
    (client_js_dir / "main.js").write_text(
        "enums.PubSub.Ignored_Main\nenums.PubSub.Client_Started\n"
    )
    (client_js_dir / "alpha.js").write_text(
        "enums.PubSub.Client_Started\nenums.PubSub.Tile_Selected\nenums.PubSub.Server_SetTurn\n"
    )
    (client_js_dir / "beta.js").write_text("enums.PubSub.Chat_Message\n")
    pubsub = enumsgen.get_pubsub_enums(client_js_dir)

    assert pubsub["Server_FatalError"] == CommandsToClient.FatalError.value
    assert pubsub["Server_DestroyGame"] == CommandsToClient.DestroyGame.value
    next_index = CommandsToClient.DestroyGame.value + 1
    assert list(pubsub.items())[-4:] == [
        ("Chat_Message", next_index),
        ("Client_Started", next_index + 1),
        ("Tile_Selected", next_index + 2),
        ("Max", next_index + 3),
    ]
    assert "Ignored_Main" not in pubsub
    assert pubsub["Server_SetTurn"] == CommandsToClient.SetTurn.value


def test_generate_enums_js_development_outputs_all_enum_names():
    output = enumsgen.generate_enums_js("development", CLIENT_SOURCE_ROOT)
    assert output.startswith("module.exports = {\n")
    assert "\tGameModes: {\n\t\tSingles: 0," in output
    assert "\tOptions: {\n\t\tEnablePageTitleNotifications: 0," in output
    assert "\tPubSub: {" in output
    assert output.endswith("};\n")


def test_generate_enums_js_development_matches_migration_baseline():
    output = enumsgen.generate_enums_js("development", CLIENT_SOURCE_ROOT)

    assert hashlib.sha256(output.encode()).hexdigest() == (
        "9227dd668fa8d71c8c0c7d701d2031bbe36aa5222de4b4f240363d80a950a35f"
    )


def test_generate_enums_js_release_limits_output_to_referenced_classes(
    tmp_path,
):
    dist_js_dir = tmp_path / "dist" / "build" / "js"
    dist_js_dir.mkdir(parents=True)
    (dist_js_dir / "bundle.js").write_text("enums.GameModes enums.Options enums.CommandsToClient")
    output = enumsgen.generate_enums_js(
        "release",
        CLIENT_SOURCE_ROOT,
        dist_js_dir,
    )
    assert "\tCommandsToClient: {" in output
    assert "\tGameModes: {\n\t\tSingles: 0," in output
    assert "\tOptions: {\n\t\tEnablePageTitleNotifications: 0," in output
    assert "\tGameActions: {" not in output


def test_generate_enums_js_rejects_unknown_mode():
    with pytest.raises(ValueError, match="Invalid enum generation mode"):
        enumsgen.generate_enums_js("unknown", CLIENT_SOURCE_ROOT)


def test_generate_enums_js_requires_release_root_only_for_release():
    with pytest.raises(ValueError, match="requires a release source root"):
        enumsgen.generate_enums_js("release", CLIENT_SOURCE_ROOT)

    with pytest.raises(ValueError, match="does not accept a release source root"):
        enumsgen.generate_enums_js(
            "development",
            CLIENT_SOURCE_ROOT,
            CLIENT_SOURCE_ROOT,
        )


def test_generate_enums_js_requires_existing_client_source_root(tmp_path):
    with pytest.raises(FileNotFoundError, match="source root"):
        enumsgen.generate_enums_js(
            "development",
            tmp_path / "missing-client-source",
        )


def test_replace_enums_rewrites_enum_references_in_files(tmp_path):
    path = tmp_path / "source.js"
    path.write_text(
        "const start = enums.GameModes.Singles;\n"
        "const sound = enums.Options.Sound.value;\n"
        "const untouched = other.enums.Options.Sound;\n"
    )

    enumsgen.replace_enums([path], CLIENT_SOURCE_ROOT)

    assert path.read_text() == (
        f"const start = {GameModes.Singles.value};\n"
        f"const sound = {Options.Sound.value};\n"
        "const untouched = other.enums.Options.Sound;\n"
    )


def test_replace_enums_validates_all_inputs_before_mutation(tmp_path):
    first_path = tmp_path / "first.js"
    first_contents = "const mode = enums.GameModes.Singles;\n"
    first_path.write_text(first_contents)

    with pytest.raises(FileNotFoundError, match="replacement input"):
        enumsgen.replace_enums(
            [first_path, tmp_path / "missing.js"],
            CLIENT_SOURCE_ROOT,
        )

    assert first_path.read_text() == first_contents


def test_main_generates_development_output_to_stdout(client_source_root, capsys):
    result = enumsgen.main(
        [
            "js",
            "development",
            "--client-source-root",
            str(client_source_root),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == enumsgen.generate_enums_js(
        "development",
        client_source_root,
    )


def test_main_generates_release_output_file(client_source_root, tmp_path, capsys):
    release_source_root = tmp_path / "release"
    release_source_root.mkdir()
    (release_source_root / "bundle.js").write_text("enums.GameModes enums.Options")
    output_path = tmp_path / "generated.js"

    result = enumsgen.main(
        [
            "js",
            "release",
            "--client-source-root",
            str(client_source_root),
            "--release-source-root",
            str(release_source_root),
            "--output",
            str(output_path),
        ]
    )

    assert result == 0
    assert output_path.read_text() == enumsgen.generate_enums_js(
        "release",
        client_source_root,
        release_source_root,
    )
    assert capsys.readouterr().out == ""


def test_main_replaces_multiple_inputs(client_source_root, tmp_path):
    first_path = tmp_path / "first.js"
    second_path = tmp_path / "second.js"
    first_path.write_text("enums.GameModes.Singles")
    second_path.write_text("enums.Options.Sound.value")

    result = enumsgen.main(
        [
            "replace",
            "--client-source-root",
            str(client_source_root),
            str(first_path),
            str(second_path),
        ]
    )

    assert result == 0
    assert first_path.read_text() == str(GameModes.Singles.value)
    assert second_path.read_text() == str(Options.Sound.value)


@pytest.mark.parametrize(
    "arguments",
    [
        ["js", "invalid"],
        ["js", "release"],
        ["js", "development", "--release-source-root", "/private/release"],
        ["replace"],
        ["--unknown"],
    ],
)
def test_main_rejects_invalid_command_combinations(arguments, capsys):
    with pytest.raises(SystemExit) as exit_info:
        enumsgen.main(arguments)

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: invalid arguments\n"


@pytest.mark.parametrize(
    ("mode", "release_source_root"),
    [
        ("release", None),
        ("development", Path("/private/release")),
    ],
)
def test_main_rejects_invalid_mode_and_release_root_combination(
    client_source_root,
    mode,
    release_source_root,
    capsys,
):
    arguments = [
        "js",
        mode,
        "--client-source-root",
        str(client_source_root),
    ]
    if release_source_root is not None:
        arguments.extend(("--release-source-root", str(release_source_root)))

    with pytest.raises(SystemExit) as exit_info:
        enumsgen.main(arguments)

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: invalid arguments\n"


@pytest.mark.parametrize(
    "private_root",
    [
        "private/relative/root",
        r"private\/relative\/root",
        "private%2Frelative%2Froot",
        "private%252Frelative%252Froot",
    ],
)
def test_main_rejects_relative_paths_without_reflecting_them(
    private_root,
    capsys,
):
    with pytest.raises(SystemExit) as exit_info:
        enumsgen.main(
            [
                "js",
                "development",
                "--client-source-root",
                private_root,
            ]
        )

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""
    assert captured.err == "error: invalid arguments\n"
    assert private_root not in captured.err


def test_main_sanitizes_missing_input_failure(client_source_root, tmp_path, capsys):
    missing_path = tmp_path / "private-missing.js"

    result = enumsgen.main(
        [
            "replace",
            "--client-source-root",
            str(client_source_root),
            str(missing_path),
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err == "error: enum generation failed\n"
    assert str(missing_path) not in captured.err
