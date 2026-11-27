# Making a release

A release is a tagged commit of `main`: the tools and data that rebuild the disc from the player's
own discs. No game data, no built disc, ever ([README](../README.md): "This repository contains no game data").

## Before tagging

1. **The gate** on the commit to tag ([maintaining.md](maintaining.md)):
   ```
   python3 tools/build.py && python3 tools/play.py test --no-build --only 01_boot
   python3 tools/checks/allchecks.py        # every check passes
   python3 tools/build.py --32x --out "build/Eternal Kombat 32X" && python3 tools/checks/x32check.py --disc "build/Eternal Kombat 32X/Eternal Kombat.cue"
   python3 tools/dev/verify_fresh.py        # a fresh clone builds the identical disc
   ```
2. **Play it** (the checks drive fixed routes; a person finds what they don't):
   - a Contest from the start with an MK fighter, through Shang Tsung, Eternal and the Dark
     Champion to his ending;
   - a Duel with each MK fighter: specials, a throw, FINISH HIM and his fatality;
   - the 32X build (optional) with a 32X (PicoDrive or ares): the MK portraits on the select screen,
     twice (a match between).
3. **README:** the status list and the known issues match what's in the build.
4. **No game data in the tree:** `git ls-files` shows only tools, data (numbers), tests and docs;
   `git status --ignored` shows the discs, `extracted/` and `build/` ignored.
5. **The licence:** MIT (LICENSE; every Python file tagged: licensecheck.py in allchecks).

## Tagging

```
git tag -a v1.0 -m "Eternal Kombat 1.0"
```

Pushing the tag (and the repository) is the maintainer's step.

## Known limits to state with it

- Tested in emulators only (Genesis Plus GX; PicoDrive and ares for the 32X), not on hardware.
- The build needs the US Eternal Champions CD and MK CD (tools/checkinputs.py names the exact dumps).

## The app

The players' app (tools/launcher: a Windows .exe and a Linux AppImage) is built by GitHub's machines
from the same commit: pushing a `launcher-*` tag runs `.github/workflows/launcher.yml`, which packages
both, checks each starts, installs RetroArch as Play would, and publishes them as that tag's release.

```
git tag -a launcher-1.0 -m "Eternal Kombat app 1.0" && git push origin launcher-1.0
```

To try the files first: run the workflow by hand (Actions > Launcher > Run workflow); they are the
run's artifacts, seen only by the repository's owner.
