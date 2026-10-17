#!/usr/bin/env bash
set -euo pipefail

run=(uv --project tools run)

step() {
  echo "::group::$1"
}

done_step() {
  echo "::endgroup::"
}

step "Bake and build a synthetic Master System cartridge"
mkdir -p build
ffmpeg -y -loglevel error -f lavfi \
  -i "testsrc2=size=320x240:rate=30:duration=3" \
  -pix_fmt yuv420p build/ci-source.mp4
"${run[@]}" python -m smsggmedia.cartridge \
  build/ci-source.mp4 --duration 2 --fps 8 --bundle build/bundle
done_step

step "Static analysis of both consoles"
make analyse
done_step

step "Build a game from the Master System bundle"
make example
done_step

step "VDP write spacing in the Master System build"
"${run[@]}" python tools/scripts/check_vdp_timing.py --target sms
done_step

step "Bake and build a Game Gear cartridge"
"${run[@]}" python -m smsggmedia.cartridge \
  build/ci-source.mp4 --duration 2 --fps 8 --target gg --bundle build/bundle-gg
done_step

step "Build a game from the Game Gear bundle"
rm -rf examples/cutscene/build
make example EXAMPLE_FMV_DIR=../../build/bundle-gg
done_step

step "VDP write spacing in the Game Gear build"
"${run[@]}" python tools/scripts/check_vdp_timing.py --target gg
done_step

step "The player on a Z80, on both cartridges"
SMSGGMEDIA_ROM_REQUIRED=1 "${run[@]}" python -m pytest \
  tools/tests/test_replay_on_z80.py \
  tools/tests/test_player_on_z80.py \
  tools/tests/test_screen_on_z80.py \
  tools/tests/test_osd_on_z80.py \
  tools/tests/test_diag_on_z80.py \
  tools/tests/test_seek_on_z80.py \
  tools/tests/test_transport_on_z80.py \
  tools/tests/test_gg_build.py
done_step

step "Both headers carry their region and a correct checksum"
"${run[@]}" python tools/scripts/check_rom.py build/smsggmedia.sms build/smsggmedia.gg
done_step
