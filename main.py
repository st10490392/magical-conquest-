"""Entry point for the Magical Conquest Pygame prototype."""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SAVE = PROJECT_ROOT / "data" / "saves" / "savegame.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Magical Conquest prototype")
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE, help="save file path")
    parser.add_argument("--frames", type=int, default=None, help="exit after N frames (smoke testing)")
    args = parser.parse_args()

    # Imported here so --help works even without Pygame installed.
    from game.presentation.pygame_app import run

    run(args.save, max_frames=args.frames)


if __name__ == "__main__":
    main()
