# Releasing DeskGadget

DeskGadget ships on two channels from one repository.

| Channel | Git branch | GitHub release | Who receives it |
| --- | --- | --- | --- |
| **Stable** | `main` | `vX.Y.Z` (Latest) | Everyone. The app checks `/releases/latest`. |
| **Beta** | `beta` | `vX.Y.Z-beta.N` (pre-release) | Only devices with **Beta builds** switched on. |

GitHub's `releases/latest` deliberately ignores pre-releases, so a beta never
reaches a stable user.

## Stable release

1. Merge the finished work into `main`.
2. Bump both values in `android/app/build.gradle.kts`:
   ```kotlin
   versionCode = 11          // always increases
   versionName = "1.4.0"
   ```
3. Build the artifacts:
   ```
   python packaging/build_exe.py
   gradle -p android assembleRelease
   ```
4. Copy the APK and publish the release:
   ```
   copy android\app\build\outputs\apk\release\app-release.apk dist\DeskGadget.apk
   gh release create v1.4.0 --title "DeskGadget 1.4.0" --notes-file notes.md ^
     dist\DeskGadget.apk dist\DeskGadget-Setup.exe dist\DeskGadget.exe docs\deskgadget-reel.mp4
   ```

Do **not** pass `--prerelease` for a stable build.

## Beta release

1. Work on the `beta` branch:
   ```
   git switch beta
   git merge main
   ```
2. Set a beta version name, with a `versionCode` higher than the previous
   build (beta and stable share the same counter):
   ```kotlin
   versionCode = 12
   versionName = "1.4.0-beta.1"
   ```
3. Build the APK as above.
4. Publish it as a pre-release:
   ```
   gh release create v1.4.0-beta.1 --prerelease --latest=false ^
     --title "DeskGadget 1.4.0-beta.1" --notes-file notes.md ^
     dist\DeskGadget.apk
   ```
5. Testers enable **Beta builds** in the app's support sheet (heart button)
   and use **Check for updates**.
6. When the beta is good, merge `beta` into `main`, drop the suffix, bump
   `versionCode`, and publish the stable release.

## How the app chooses a channel

- **Beta builds: OFF** → `https://api.github.com/repos/issacjohn/deskgadget/releases/latest`
- **Beta builds: ON** → `https://api.github.com/repos/issacjohn/deskgadget/releases?per_page=20`,
  newest non-draft release that has an APK, including pre-releases.
- `Updater.isNewer` is semver-aware:
  `1.4.0` > `1.4.0-beta.2`, and `1.4.0-beta.2` > `1.4.0-beta.1`.

## Version format

- Stable: `1.4.0` — `v1.4.0`
- Beta: `1.4.0-beta.1`, `1.4.0-beta.2` — `v1.4.0-beta.1`
- `versionCode` increases on every published build, beta or stable.

## Windows

The desktop app has no in-app updater yet. Beta Windows installers can be
attached to the pre-release with the same `--prerelease` flag; stable users
keep getting the installer from the latest stable release.
