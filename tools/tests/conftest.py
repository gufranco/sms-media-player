import pytest
from fmvcore import testing

FFMPEG_REQUIRED_ENV = "SMSGGMEDIA_FFMPEG_REQUIRED"
DECODERS = ("ffmpeg", "ffprobe")


def pytest_runtest_setup(item: pytest.Item) -> None:
    testing.require_tools(item, marker="ffmpeg", tools=DECODERS, required_env=FFMPEG_REQUIRED_ENV)
