from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version

DISTRIBUTION_NAME = "a-share-announcement"
UNKNOWN_VERSION = "0.0.0+unknown"


def get_version() -> str:
    try:
        return metadata_version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return UNKNOWN_VERSION


__version__ = get_version()

__all__ = [
    "DISTRIBUTION_NAME",
    "UNKNOWN_VERSION",
    "__version__",
    "get_version",
]
