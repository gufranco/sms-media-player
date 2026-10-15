from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smsmedia import vdptiming


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_vdp_timing")
    parser.add_argument("listings", nargs="*", type=Path)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--root", type=Path, default=vdptiming.ROOT)
    args = parser.parse_args(argv)

    listings = args.listings or vdptiming.built_listings(args.root)
    unusable = _unusable(listings, root=args.root)
    if unusable is not None:
        print(unusable, file=sys.stderr)
        return 2
    reports = vdptiming.check_program({path.name: path.read_text() for path in listings})
    if vdptiming.data_intervals(reports) == 0:
        print(
            "no interval touching the VDP data port was measured, so the transfer loop "
            "was not seen and nothing was checked",
            file=sys.stderr,
        )
        return 2
    failed = sum(
        _report(path, report, quiet=args.quiet)
        for path, report in zip(listings, reports, strict=True)
    )
    return _verdict(failed)


def _unusable(listings: list[Path], *, root: Path) -> str | None:
    if not listings:
        return "no listings to check; run `make rom` first"
    stale = vdptiming.stale_listings(listings, root)
    if stale:
        names = ", ".join(path.name for path in stale)
        return f"listings older than their source: {names}; run `make rom` first"
    return None


def _report(path: Path, report: vdptiming.Report, *, quiet: bool) -> int:
    for violation in report.violations:
        print(f"TOO FAST  {violation.describe()}", file=sys.stderr)
    for setup in report.unguarded:
        print(
            f"UNGUARDED {path.name}: control write at 0x{setup.address:04X} "
            "can start a vertical-blank copy without reading the V counter",
            file=sys.stderr,
        )
    if not quiet:
        tightest = min((gap.cycles for gap in report.gaps), default=0)
        print(f"{path.name}: {len(report.gaps)} intervals, tightest {tightest} T-states")
    return len(report.violations) + len(report.unguarded)


def _verdict(failed: int) -> int:
    if failed:
        print(
            f"\n{failed} write pairs are closer than {vdptiming.MINIMUM_INTERVAL} T-states. "
            "The real VDP drops those writes during active display and the picture shreds; "
            "no emulator here reports it.",
            file=sys.stderr,
        )
        return 1
    print(
        f"\nevery VDP write pair clears {vdptiming.MINIMUM_INTERVAL} T-states, "
        f"or {vdptiming.VBLANK_INTERVAL} inside the guarded vertical-blank copy"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
