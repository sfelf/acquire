# Game Log Fixtures

This directory stores small redacted log fixtures and expected parser output for golden regression tests.

- `sample_server.txt` is a synthetic fixture that exercises the current line parser without using production data.
- `sample_server.expected.json` is the expected normalized parser output.
- `sample_individual_game.expected.json` is the expected per-game batch extraction output.
- `redacted_real_server.txt` is a redacted log from an existing server.
- `redacted_real_server.summary.expected.json` is a compact expected summary for that real-server fixture.

Historical game logs can be added here in later PRs after sensitive data is redacted or replaced with representative samples.
