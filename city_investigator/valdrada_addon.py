"""Install City Investigator's add-on into a local copy of Valdrada.

Valdrada (github.com/mkturkcan/valdrada) is a 3D city of New York. This copies one module,
cityInvestigator.js, into its client/src/city/ and adds a hook to client/src/main.js that loads it
at boot. The page's Valdrada 3D view passes ?scene=<url>, a run's scene (city_investigator.scene3d):
the flood records as water, buildings with a shed permit valid on the photo's date with Valdrada's
own shed model, scaffolding the photo shows, and unsafe façades, each labeled with its source.
Valdrada's randomly placed sheds are taken away, so every shed in view is a record or the photo.
Once Valdrada has loaded in the page, the module also takes the page's messages, so another place
moves the camera and swaps the scene instead of loading the city again. Running it again changes
nothing; it replaces an earlier version's hook and module.

Usage:
  python -m city_investigator.valdrada_addon G:\\Projects\\valdrada
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

MODULE = Path(__file__).parent / "valdrada" / "cityInvestigator.js"
EARLIER_MODULES = ("cityInvestigatorFlood.js",)
ANCHOR = "  bootMark('tile manifest');"
TAG = "added by city_investigator.valdrada_"  # on the first line of every version of the hook
HOOK = (
    f"  // City Investigator ({TAG}addon): a run's records and what its photo shows (?scene=<url>), and the page\n"
    "  // that frames Valdrada moving it to another place without loading the city again\n"
    "  import('./city/cityInvestigator.js')\n"
    "    .then((m) => m.connect({ scene: engine.scene, streamer, instancer, camera: () => controller }, Q.get('scene')))\n"
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
    for name in EARLIER_MODULES:
        earlier = valdrada / "client" / "src" / "city" / name
        if earlier.is_file():
            earlier.unlink()
            done.append(f"removed the earlier {name}")
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
