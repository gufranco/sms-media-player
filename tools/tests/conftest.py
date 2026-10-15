import os
import shutil

import pytest

FFMPEG_REQUIRED_ENV = "SMSMEDIA_FFMPEG_REQUIRED"
DECODERS = ("ffmpeg", "ffprobe")


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("ffmpeg") is None:
        return
    missing = [tool for tool in DECODERS if shutil.which(tool) is None]
    if not missing:
        return
    reason = f"{', '.join(missing)} not on the path, and the decode path needs it"
    if os.environ.get(FFMPEG_REQUIRED_ENV) == "1":
        pytest.fail(reason)
    pytest.skip(reason)
