# roms/

Your own disc rips go here, as BIN/CUE (raw 2352-byte sectors, as Redump dumps are), one folder per
disc, any folder and file names:

```
roms/Eternal Champions - Challenge from the Dark Side (USA)/   (.cue + its .bin files)   required
roms/Mortal Kombat (USA)/                                      (.cue + its .bin files)   required
```

`python3 tools/checkinputs.py` finds them and checks they are the right dumps. Nothing in this folder
but this file is ever committed. See the main README, "This repository contains no game data".
