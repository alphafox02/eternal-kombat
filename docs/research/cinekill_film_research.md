# Cinekill restoration: first experiment

An experiment in cleaning up EC's finisher movies (Larcen's Cinekill): preview videos made from an
emulator capture, compared side by side with two strengths of cleanup; they changed nothing in the
game and have since been deleted. Kept for what it found about the movie format, which EC's intro movie
(`ZZ00.BIN`) shares.

## What was verified

- The disc's `ZK.*`, `ZB.*` and `ZE.*` files identify as early Sega FILM/CPK.
  `ZK.9` is mapped to Larcen's Cinekill in the fighter-to-movie table at
  SUB.BIN $72EC (fighter id 3). Its header declares codec `SEGA`, 256×208,
  timescale 600. Its 156 interleaved records comprise 144 video and 12 audio
  records; all video durations are 50 ticks, nominally 12 frames/s. This is
  container metadata, not a decoded-frame accuracy or audible-quality claim.
- The installed FFmpeg recognises the container but rejects this early variant.
  The format interleaves a 16-byte record before each media sample and has an
  abbreviated FDSC; its `SEGA` video codec is not proven to be standard Cinepak.
  References: [early Sega FILM description](https://wiki.multimedia.cx/index.php/Sega_FILM)
  and [FFmpeg's FILM demuxer](https://www.ffmpeg.org/doxygen/trunk/segafilm_8c_source.html).
- An isolated emulator run triggered an actual Larcen Cinekill from the current
  disc. The test set both round wins and power-combo flag in emulator RAM,
  set Larcen's health to 20, then had his task call EC's own finisher check;
  it did not change the game files. The Dark Champion appears in the arena as
  part of that sequence, before the movie.
- The game switches its output from 320×224 to 256×224 for video. The existing
  `finishvideo.Rec` drops frames of a different size, so the isolated recorder
  padded smaller frames into the same 320×224 canvas instead. The comparison
  crops the 256×208 picture at x=32, y=0 from that canvas; the unmodified
  centre/bottom screen layout and cropping should be checked when improving the
  capture pipeline. The movie portion was approximately seconds 17.06–27.65 in
  this particular capture. Source audio and video were captured together.
- The first comparison was made with FFmpeg temporal denoising, Lanczos
  enlargement and modest brightness/sharpening. The stronger version adds a
  small spatial blur. These are offline post-processing experiments; details
  may be softened, and no missing source detail is recovered. No machine-learning
  upscaler was used. An earlier variant compared only two versions.

## Remaining work

1. Decode the early FILM record stream and its `SEGA` codec directly from the
   disc; compare against the game's rendering and audio at original frame
   rate. The 144 frames versus approximately 10.6 s captured visible content
   needs explanation before claiming a complete direct extraction.
2. Evaluate better temporally consistent de-dithering/upscaling, using the
   original as a visual check; avoid hallucinated faces or changing animation.
3. Establish a 32X CD boot/graphics path and a video playback codec under its
   frame-buffer, CPU, disc-bandwidth and audio limits. Encoding a preview on a
   desktop is not evidence it will run on a 32X. Test one clip, actual audio
   synchronization and transitions on real hardware and accurate emulators.
4. Keep the regular Sega CD disc reproducible and unmodified. The game's current
   Cinekill filter blocks MK fighters as victims because the original movies
   show EC characters. Improving EC scenes does not make MK-victim videos.

The exploration scripts and the full capture were temporary and are not kept.
All game-disc files remained untouched. Screenshot and video previews were
generated local assets, not needed by the build.

The three-way preview uses `crop=256:208:32:0` from the padded capture. Original
uses 2× nearest-neighbor. The subtle side uses
`hqdn3d=2:2:4:4,scale=512:416:flags=lanczos,unsharp=5:5:0.25:5:5:0,eq=gamma=1.12:contrast=1.03`;
the stronger side uses
`hqdn3d=3:2:5:4,gblur=sigma=0.6,scale=512:416:flags=lanczos,unsharp=5:5:0.5:5:5:0,eq=gamma=1.25:contrast=1.03`.
Both were encoded in H.264 at CRF 17 with the captured audio re-encoded to AAC.
