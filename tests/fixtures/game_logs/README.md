# Game Log Fixtures

This directory stores small redacted log fixtures and expected parser output for golden regression tests.

- `sample_server.txt` is a synthetic fixture that exercises the current line parser without using production data.
- `sample_server.expected.json` is the expected normalized parser output.
- `sample_individual_game.expected.json` is the expected per-game batch extraction output.
- `sample_server.replay.expected.json` is the expected `LogProcessor` replay summary for the synthetic fixture.
- `sample_server.final_state.expected.json` is the expected final-state replay snapshot for the synthetic fixture.
- `redacted_real_server.txt` is a redacted log from an existing server.
- `redacted_real_server.summary.expected.json` is a compact expected summary for that real-server fixture.
- `redacted_real_server.replay.expected.json` is the expected `LogProcessor` replay summary for the real-server fixture.
- `redacted_real_server.final_state.expected.json` is a compact final-state replay snapshot covering board rows, score sheets, tile racks, action boundaries, and history boundaries.

Historical game logs can be added here in later PRs after sensitive data is redacted or replaced with representative samples.
