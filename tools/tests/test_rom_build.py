import shutil
import subprocess
from pathlib import Path

import pytest
from fmvcore.testing import seeded

from smsmedia import cartridge, target

ROOT = Path(__file__).resolve().parents[2]
FAKE = seeded()
DOCKER_LOG = "docker.log"
MEDIA_TOOLS = ("ffmpeg", "ffprobe")
SYSTEM_PATH = ("/usr/bin", "/bin")
SMS_ROM = cartridge.rom_for(target.MASTER_SYSTEM)
MAKE_FAILED = 2
REFUSED = 2

pytestmark = pytest.mark.ffmpeg


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    path = tmp_path_factory.mktemp("clip") / "source.mp4"
    lavfi = "testsrc2=size=320x240:rate=30:duration=2"
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        lavfi,
        str(path),
    ]
    subprocess.run(command, check=True)
    return path


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    shutil.copyfile(ROOT / "Makefile", tmp_path / "Makefile")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def fake_docker(monkeypatch: pytest.MonkeyPatch, directory: Path, *, status: int = 0) -> Path:
    shim = directory / "shim"
    shim.mkdir()
    log = directory / DOCKER_LOG
    script = shim / "docker"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log}'\nexit {status}\n")
    script.chmod(0o755)
    for tool in MEDIA_TOOLS:
        (shim / tool).symlink_to(str(shutil.which(tool)))
    monkeypatch.setenv("PATH", ":".join([str(shim), *SYSTEM_PATH]))
    monkeypatch.delenv("DEVKITSMS", raising=False)
    return log


def baking(clip: Path, directory: Path, *extra: str) -> list[str]:
    return [
        str(clip),
        "--fps",
        "4",
        "--duration",
        "1",
        "--columns",
        "8",
        "--rows",
        "6",
        "--cap",
        "60",
        "--assets",
        str(directory / "assets"),
        "--generated",
        str(directory / "generated"),
        "--report",
        str(directory / "report.json"),
        *extra,
    ]


class TestTheRomBuild:
    def test_a_good_bake_is_built_through_make_rom(self, clip, checkout, monkeypatch, capsys):
        # Arrange
        log = fake_docker(monkeypatch, checkout)
        rom = checkout / SMS_ROM
        rom.parent.mkdir(parents=True)
        rom.write_bytes(bytes(FAKE.random_int(1, 64)))

        # Act
        code = cartridge.main(baking(clip, checkout))

        # Assert
        assert code == 0
        assert "make --no-print-directory rom" in log.read_text()
        assert f"{SMS_ROM}  {rom.stat().st_size} bytes" in capsys.readouterr().out

    def test_a_failed_build_returns_its_status(self, clip, checkout, monkeypatch, capsys):
        # Arrange
        fake_docker(monkeypatch, checkout, status=FAKE.random_int(1, 100))
        argv = baking(clip, checkout)

        # Act
        code = cartridge.main(argv)

        # Assert
        assert code == MAKE_FAILED
        assert str(SMS_ROM) not in capsys.readouterr().out

    def test_bake_only_stops_before_the_build(self, clip, checkout, monkeypatch, capsys):
        # Arrange
        log = fake_docker(monkeypatch, checkout)
        argv = baking(clip, checkout, "--bake-only")

        # Act
        code = cartridge.main(argv)

        # Assert
        assert code == 0
        assert not log.exists()
        assert f"baked into {checkout / 'assets'}" in capsys.readouterr().err

    def test_a_failed_bake_skips_the_build(self, clip, checkout, monkeypatch):
        # Arrange
        log = fake_docker(monkeypatch, checkout)
        argv = baking(clip, checkout, "--max-banks", "1", "--cap", "220", "--fps", "12")

        # Act
        code = cartridge.main(
            [
                *argv,
                "--columns",
                "32",
                "--rows",
                "18",
                "--reuse",
                "0.0",
            ]
        )

        # Assert
        assert code == REFUSED
        assert not log.exists()

    def test_the_rom_is_named_after_the_package(self):
        # Arrange
        makefile = (ROOT / "Makefile").read_text()

        # Act
        named = f"ROM_NAME     := {SMS_ROM.stem}\n" in makefile

        # Assert
        assert (named, SMS_ROM) == (True, Path("build") / "smsmedia.sms")
