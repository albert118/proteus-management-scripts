# vdiff

A tool to help validate video stream re-encode quality without manually checking them by eye. This check the given video stream for issues using a few strategies. It works for lossy re-encodes by checking the result against a snapshot of the original file.

This calculates the following stats:

- [Netflix's VMAF](https://en.wikipedia.org/wiki/Video_Multimethod_Assessment_Fusion)
- PSNR (peak signal to noise ratio)
- Structural Similarity Index Measure (SSIM)
The (VMAF) score of is betwen [0, 100]
- 93 - 95 is imperceptible to the human eye
- 100 is perfect (unlikely).

The PSNR is decible scale
higher is better

- relies on MSE
- a standard, 8-bit, image with a "good" score would be ~[30, 50] db

SSIM compares some other common visuals,

- luminance, contrast, and structure
- not captured by other stats
- [0.0, 1.0] range. 1.0 is identical to original, and 0.0 is no similarity

This script uses ffmpeg to calculate the various stats that factor into the VMAF score. This in turn relise on having the libvmaf filter compiled with it.
This is not standard typically! However, there are other precompiled binaries that can be used.

```sh
wget https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz
tar -xf ffmpeg-git-amd64-static.tar.xz
cd ffmpeg-*-amd64-static/
# test if the filter is available
./ffmpeg -filters | grep vmaf
```

## TODO

- [ ] confirm linear fallback mode
- [ ] confirm parallel processing isn't skipping frames (test batch splitting)
- [ ] cancelling parallel processing leaves hanging ffmpeg processes!!! Need to clean these up correctly
- [ ] test with different number of workers provisioned
- [ ] TQDM fallback/disable within docker containers
- [ ] time container alignment to reduce processing overhead
- [ ] add tests
