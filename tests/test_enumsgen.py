import enumsgen
import pytest
from enums import CommandsToClient, GameModes, Options

pytestmark = pytest.mark.unit


def test_get_server_enums_returns_ordered_enum_values():
    server_enums = enumsgen.get_server_enums()

    assert server_enums["CommandsToClient"]["FatalError"] == CommandsToClient.FatalError.value
    assert server_enums["CommandsToClient"]["DestroyGame"] == CommandsToClient.DestroyGame.value
    assert server_enums["GameModes"]["Singles"] == GameModes.Singles.value


def test_get_pubsub_enums_includes_server_commands_and_client_events(
    tmp_path,
    monkeypatch,
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
    monkeypatch.chdir(tmp_path)

    pubsub = enumsgen.get_pubsub_enums()

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


def test_generate_enums_js_development_outputs_all_enum_names(capsys):
    enumsgen.generate_enums_js("development")

    output = capsys.readouterr().out
    assert output.startswith("module.exports = {\n")
    assert "\tGameModes: {\n\t\tSingles: 0," in output
    assert "\tOptions: {\n\t\tEnablePageTitleNotifications: 0," in output
    assert "\tPubSub: {" in output
    assert output.endswith("};\n")


def test_generate_enums_js_release_limits_output_to_referenced_classes(
    tmp_path,
    monkeypatch,
    capsys,
):
    dist_js_dir = tmp_path / "dist" / "build" / "js"
    dist_js_dir.mkdir(parents=True)
    (dist_js_dir / "bundle.js").write_text("enums.GameModes enums.Options enums.CommandsToClient")
    monkeypatch.chdir(tmp_path)

    enumsgen.generate_enums_js("release")

    output = capsys.readouterr().out
    assert "\tCommandsToClient: {" in output
    assert "\tGameModes: {\n\t\tSingles: 0," in output
    assert "\tOptions: {\n\t\tEnablePageTitleNotifications: 0," in output
    assert "\tGameActions: {" not in output


def test_generate_enums_js_rejects_unknown_mode():
    with pytest.raises(Exception, match="invalid mode"):
        enumsgen.generate_enums_js("unknown")


def test_replace_enums_rewrites_enum_references_in_files(tmp_path):
    path = tmp_path / "source.js"
    path.write_text(
        "const start = enums.GameModes.Singles;\n"
        "const sound = enums.Options.Sound.value;\n"
        "const untouched = other.enums.Options.Sound;\n"
    )

    enumsgen.replace_enums([path])

    assert path.read_text() == (
        f"const start = {GameModes.Singles.value};\n"
        f"const sound = {Options.Sound.value};\n"
        "const untouched = other.enums.Options.Sound;\n"
    )
