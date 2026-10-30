"""Install City Investigator's flood overlay into a local copy of Valdrada.

Valdrada (github.com/mkturkcan/valdrada) has rain but no flood water. This copies one module,
cityInvestigatorFlood.js, into its client/src/city/ and adds one line to client/src/main.js that
loads it when the page is opened with ?flood=<url>. The page's Valdrada 3D view passes that URL
for flooding investigations: the city flood model's areas at their depth class and the nearest
sensor's deepest reading, drawn over Valdrada's ground. Running it again changes nothing.

Usage:
  python -m city_investigator.valdrada_flood G:\\Projects\\valdrada
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

MODULE = Path(__file__).parent / "valdrada" / "cityInvestigatorFlood.js"
ANCHOR = "  bootMark('tile manifest');"
MARKER = "City Investigator: a run's flood records"
HOOK = (
    f"  // {MARKER} over the ground (?flood=<url>; added by city_investigator.valdrada_flood)\n"
    "  if (Q.get('flood')) import('./city/cityInvestigatorFlood.js')\n"
    "    .then((m) => m.addFloodOverlay(engine.scene, streamer, Q.get('flood')))\n"
    "    .catch((e) => console.warn('flood overlay unavailable', e));\n"
)


def install(valdrada: Path) -> list[str]:
    """Copy the module and hook it into main.js; return what was done."""
    main = valdrada / "client" / "src" / "main.js"
    if not main.is_file():
        raise SystemExit(f"{main} not found: give the folder Valdrada was cloned into.")
    done = []
    target = valdrada / "client" / "src" / "city" / MODULE.name
    if not target.is_file() or target.read_bytes() != MODULE.read_bytes():
        shutil.copyfile(MODULE, target)
        done.append(f"copied {MODULE.name} to {target.parent}")
    text = main.read_bytes().decode("utf-8")
    if MARKER not in text:
        if text.count(ANCHOR) != 1:
            raise SystemExit("client/src/main.js has changed shape (no single tile-manifest line); the hook was not added.")
        newline = "\r\n" if "\r\n" in text else "\n"  # a Windows checkout may use CRLF
        end = text.index("\n", text.index(ANCHOR)) + 1
        main.write_bytes((text[:end] + HOOK.replace("\n", newline) + text[end:]).encode("utf-8"))
        done.append("added the flood hook to client/src/main.js")
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("valdrada", type=Path, help="the folder Valdrada was cloned into")
    done = install(parser.parse_args().valdrada)
    print("\n".join(done) or "Already installed; nothing changed.")
    if done:
        print("Restart Valdrada (Ctrl+C, then npm run dev in its client folder) to load it.")


if __name__ == "__main__":
    main()
