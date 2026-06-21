import gzip

import pytest
import settings
import util

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_log_filename_cache():
    util._log_type_to_log_file_filenames.clear()
    yield
    util._log_type_to_log_file_filenames.clear()


def make_log_dir(tmp_path, prefix_name, log_type, filenames):
    prefix = tmp_path / prefix_name
    log_dir = tmp_path / f"{prefix_name}{log_type}"
    log_dir.mkdir()
    for filename in filenames:
        (log_dir / filename).write_text(filename)
    return str(prefix)


def test_get_log_file_filenames_collects_sorts_and_filters_timestamps(
    tmp_path,
    monkeypatch,
):
    prefix_a = make_log_dir(
        tmp_path,
        "logs_",
        "py",
        ["1700000002.gz", "1700000000", "1700000004"],
    )
    prefix_b = make_log_dir(tmp_path, "archive_", "py", ["1700000001", "1700000003.gz"])
    monkeypatch.setattr(
        settings,
        "util__get_log_file_filenames__path_prefixes",
        [prefix_a, prefix_b],
    )

    result = util.get_log_file_filenames("py", begin=1700000001, end=1700000003)

    assert result == [
        (1700000001, str(tmp_path / "archive_py" / "1700000001")),
        (1700000002, str(tmp_path / "logs_py" / "1700000002.gz")),
        (1700000003, str(tmp_path / "archive_py" / "1700000003.gz")),
    ]


def test_get_log_file_filenames_uses_cached_listing_for_same_log_type(
    tmp_path,
    monkeypatch,
):
    prefix = make_log_dir(tmp_path, "logs_", "py", ["1700000000"])
    monkeypatch.setattr(
        settings,
        "util__get_log_file_filenames__path_prefixes",
        [prefix],
    )

    first_result = util.get_log_file_filenames("py")
    (tmp_path / "logs_py" / "1700000001").write_text("new")
    second_result = util.get_log_file_filenames("py")

    assert first_result == [(1700000000, str(tmp_path / "logs_py" / "1700000000"))]
    assert second_result == first_result


def test_get_log_file_filenames_keeps_distinct_caches_per_log_type(
    tmp_path,
    monkeypatch,
):
    prefix = make_log_dir(tmp_path, "logs_", "py", ["1700000000"])
    make_log_dir(tmp_path, "logs_", "chat", ["1700000005"])
    monkeypatch.setattr(
        settings,
        "util__get_log_file_filenames__path_prefixes",
        [prefix],
    )

    assert util.get_log_file_filenames("py") == [
        (1700000000, str(tmp_path / "logs_py" / "1700000000"))
    ]
    assert util.get_log_file_filenames("chat") == [
        (1700000005, str(tmp_path / "logs_chat" / "1700000005"))
    ]


def test_open_possibly_gzipped_file_reads_plain_file(tmp_path):
    path = tmp_path / "1700000000"
    path.write_text("plain log\n")

    with util.open_possibly_gzipped_file(str(path)) as file:
        assert file.read() == "plain log\n"


def test_open_possibly_gzipped_file_reads_gzip_file(tmp_path):
    path = tmp_path / "1700000000.gz"
    with gzip.open(path, "wt") as file:
        file.write("gzipped log\n")

    with util.open_possibly_gzipped_file(str(path)) as file:
        assert file.read() == "gzipped log\n"
