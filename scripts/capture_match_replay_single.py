from __future__ import annotations

import argparse
from pathlib import Path

from capture_match_replay_signature import capture_for_viewport


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    capture_for_viewport(args.width, args.height, args.label, Path(args.out))
    print("ok")


if __name__ == "__main__":
    main()
