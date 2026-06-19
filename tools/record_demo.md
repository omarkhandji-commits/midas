# Recording the 15-second MIDAS demo GIF

This is the asset that multiplies README stars. Goal: show the
**plan → approve → execute → signed receipt** loop in one shot.

Target file: `docs/assets/midas-demo.gif`
Target size: ≤ 5 MB, ≤ 15 s, 1280×720, ~12 fps.

## What to capture

1. (00:00) Terminal with `midas init` → "Dashboard ready"
2. (00:03) Dashboard `/` Chat — type "Draft a launch email"
3. (00:06) Approval card appears in `/approvals` with the JSON payload + cost
4. (00:09) Click **Approve** → **Execute** appears → click it
5. (00:12) `/proofs` shows the new signed receipt + green Chain OK badge

## macOS (built-in)

```bash
# Open the dashboard, then:
brew install ffmpeg gifski
# Cmd+Shift+5, record screen region as Demo.mov (15 s)
ffmpeg -i Demo.mov -vf "fps=12,scale=1280:-1:flags=lanczos" -c:v png frames/%04d.png
gifski -o docs/assets/midas-demo.gif --fps 12 --width 1280 --quality 80 frames/*.png
```

## Windows (built-in via PowerToys)

1. Install [PowerToys](https://github.com/microsoft/PowerToys) → enable **Screen Ruler / Screen Recorder**.
2. Record the 15-s sequence as MP4.
3. Convert:
   ```powershell
   ffmpeg -i Demo.mp4 -vf "fps=12,scale=1280:-1:flags=lanczos" -c:v png frames\%04d.png
   gifski -o docs\assets\midas-demo.gif --fps 12 --width 1280 --quality 80 frames\*.png
   ```

## Linux

```bash
sudo apt install ffmpeg gifski peek
peek  # record region as GIF directly, or:
ffmpeg -video_size 1280x720 -framerate 12 -f x11grab -i :0.0 -t 15 demo.mp4
ffmpeg -i demo.mp4 -vf "fps=12,scale=1280:-1:flags=lanczos" -c:v png frames/%04d.png
gifski -o docs/assets/midas-demo.gif --fps 12 --width 1280 --quality 80 frames/*.png
```

## Sanity checks before commit

- [ ] File size ≤ 5 MB (GitHub README will render it inline up to ~10 MB but smaller = faster)
- [ ] Duration ≤ 15 s
- [ ] No secret token visible in the address bar or terminal
- [ ] No personal email / API key visible

Commit:

```bash
git add docs/assets/midas-demo.gif
git commit -m "docs: add 15s demo GIF"
git push
```
