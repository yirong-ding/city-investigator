"""Install City Investigator's flood overlay into a local copy of Valdrada.

Valdrada (github.com/mkturkcan/valdrada) has rain but no flood water. This copies one module,
cityInvestigatorFlood.js, into its client/src/city/ and adds a hook to client/src/main.js that
loads it at boot. The page's Valdrada 3D view passes ?flood=<url> for flooding investigations: the
city flood model's areas at their depth class and the nearest sensor's deepest reading, drawn over
Valdrada's ground. Once Valdrada has loaded in the page, the module also takes the page's messages,
so another place moves the camera and swaps the records instead of loading the city again.
Running it again changes nothing; it replaces an earlier version's hook.

Usage:
  python -m city_investigator.valdrada_flood G:\\Projects\\valdrada
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

MODULE = Path(__file__).parent / "valdrada" / "cityInvestigatorFlood.js"
ANCHOR = "  bootMark('tile manifest');"
TAG = "added by city_investigator.valdrada_flood"  # on the first line of every version of the hook
HOOK = (
    f"  // City Investigator ({TAG}): a run's flood records over the ground (?flood=<url>), and the page that\n"
    "  // frames Valdrada moving it to another place without loading the city again\n"
    "  import('./city/cityInvestigatorFlood.js')\n"
    "    .then((m) => m.connect(engine.scene, streamer, () => controller, Q.get('flood')))\n"
    "    .catch((e) => console.warn('City Investigator add-on unavailable', e));\n"
)


def without_hook(text: str) -> str:
    """main.js without an installed hook: from its tagged first line through its .catch line."""
    lines = text.splitlines(keepends=True)
    start = next((n for n, line in enumerate(lines) if TAG in line), None)
    if start is None:
        return text
    end = next(n for n in range(start, len(lines)) if ".catch(" in lines[n])
    return "".join(lines[:start] + lines[end + 1:])


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
    newline = "\r\n" if "\r\n" in text else "\n"  # a Windows checkout may use CRLF
    hook = HOOK.replace("\n", newline)
    if hook not in text:
        earlier = TAG in text
        text = without_hook(text)
        if text.count(ANCHOR) != 1:
            raise SystemExit("client/src/main.js has changed shape (no single tile-manifest line); the hook was not added.")
        end = text.index("\n", text.index(ANCHOR)) + 1
        main.write_bytes((text[:end] + hook + text[end:]).encode("utf-8"))
        done.append(f"{'updated' if earlier else 'added'} the City Investigator hook in client/src/main.js")
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
