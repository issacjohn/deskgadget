## DeskGadget 1.3.8-beta.3

The phone camera now shows up in Windows apps as a real camera.

### Camera

- **Resolution chips** — pick **1080p**, **720p** or **480p**. 720p is the
  default; 480p is the light option for weak Wi-Fi. Lens, torch and quality sit
  in one compact card.
- **Measured fps** on the SM-G980F: 21 fps at 720p, 23 fps at 1080p,
  24 fps at 480p (back lens).
- **Auto-reconnect** — if the server restarts or the network blips, the camera
  socket reopens on its own instead of showing `LIVE` with 0 fps.
- The preview is still exactly what the PC receives, including rotation.

### PC side

- **Virtual camera** — the feed appears as **Unity Video Capture** (UnityCapture,
  MIT). No OBS, no VB-Cable: pick it in Teams, Zoom, Discord, the Camera app.
- Output is **1280×720**. 16:9 sources scale edge to edge; 4:3 sources are
  letterboxed instead of stretched.
- `GET /api/camera/virtual` reports whether the device is running.

### Updater

- Switching **Beta builds** on now checks for updates immediately, so the beta
  channel is reachable without hunting for *Check for updates*.

### Install

- **Android:** `DeskGadget.apk` (`1.3.8-beta.3`, versionCode 13)
- **Windows:** run the server from the beta branch for now — the packaged
  build with the bundled virtual camera follows in the next beta.
