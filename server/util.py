import gzip
import os
import os.path
import re

import settings

_log_type_to_log_file_filenames = {}
re_timestamp_in_path = re.compile(r"([^/]*?)(\.gz)?$")


def get_log_file_filenames(log_type, begin=None, end=None):
    global _log_type_to_log_file_filenames

    if log_type in _log_type_to_log_file_filenames:
        timestamps_and_filenames = _log_type_to_log_file_filenames[log_type]
    else:
        filenames = []
        for path_prefix in settings.util__get_log_file_filenames__path_prefixes:
            path = path_prefix + log_type
            for filename in os.listdir(path):
                filenames.append(os.path.join(path, filename))

        timestamps_and_filenames = []
        for filename in filenames:
            match = re_timestamp_in_path.search(filename)
            assert match is not None
            timestamps_and_filenames.append((int(match.group(1)), filename))

        _log_type_to_log_file_filenames[log_type] = timestamps_and_filenames

    if begin:
        timestamps_and_filenames = filter(lambda x: x[0] >= begin, timestamps_and_filenames)

    if end:
        timestamps_and_filenames = filter(lambda x: x[0] <= end, timestamps_and_filenames)

    return sorted(timestamps_and_filenames)


re_gzip_filename = re.compile(r".*\.gz$")


def open_possibly_gzipped_file(filename):
    f = gzip.open(filename, "rt") if re_gzip_filename.match(filename) else open(filename)  # noqa: SIM115
    return f
