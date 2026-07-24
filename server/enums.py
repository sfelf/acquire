"""Compatibility exports for :mod:`acquire.enums`.

Remove this wrapper in issue #111 after all callers use the installed package.
"""

from acquire.enums import (
    CommandsToClient,
    CommandsToServer,
    Errors,
    GameActions,
    GameBoardTypes,
    GameHistoryMessages,
    GameModes,
    GameStates,
    Notifications,
    Options,
    ScoreSheetIndexes,
    ScoreSheetRows,
)

__all__ = [
    "CommandsToClient",
    "CommandsToServer",
    "Errors",
    "GameActions",
    "GameBoardTypes",
    "GameHistoryMessages",
    "GameModes",
    "GameStates",
    "Notifications",
    "Options",
    "ScoreSheetIndexes",
    "ScoreSheetRows",
]
