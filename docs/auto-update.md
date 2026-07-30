# WMT Desktop Auto Update

The app uses the official Tauri v2 updater.

## Update Endpoint

The current endpoint is configured in `src-tauri/tauri.conf.json`:

```text
https://wmt-updates.local/wmt-desktop/latest.json
```

Host this file on an internal IIS site with HTTPS trusted by all workstations.

## Signing Key

The updater private key was generated at:

```text
C:\wmt_desktop\wmt-desktop-updater.key
```

Keep this file private. Only the public key is stored in `tauri.conf.json`.

## Build A Signed Update

Before building, set the signing key:

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY = "C:\wmt_desktop\wmt-desktop-updater.key"
pnpm build:tauri
```

Every release must increment both versions:

```text
package.json
src-tauri/tauri.conf.json
src-tauri/Cargo.toml
```

Example: `1.0.0` to `1.0.1`.

## Release Channels

Production clients use:

```text
/api/updates/latest.json
```

Debug clients use:

```text
/api/updates/latest-debug.json
```

The debug build changes the app name and identifier to `WMT Desktop Debug`, so it can be installed side by side with the production app. This lets you validate updates on test machines before publishing to everyone.

Build production:

```powershell
.\scripts\build-and-release.ps1 -Channel prod -Type patch -BackendUrl "https://wmt.example.com"
```

Build debug:

```powershell
.\scripts\build-and-release.ps1 -Channel debug -Type patch -BackendUrl "https://wmt.example.com"
```

Install the debug MSI once on the validation machines. After that, only those machines will follow `latest-debug.json`; normal users keep following `latest.json`.

## Publish Files

After build, publish the NSIS installer and its `.sig` file from:

```text
src-tauri\target\release\bundle\nsis
```

Create or update `latest.json` on IIS:

```json
{
  "version": "1.0.1",
  "notes": "Backup page now uses the logged Windows account.",
  "pub_date": "2026-06-02T00:00:00Z",
  "platforms": {
    "windows-x86_64": {
      "signature": "CONTENT_OF_THE_SIG_FILE",
      "url": "https://wmt-updates.local/wmt-desktop/WMT_Desktop_1.0.1_x64-setup.exe"
    }
  }
}
```

The `signature` value must be the text inside the generated `.sig` file, not a path.

## Client Behavior

When WMT opens, React checks for an update through the Tauri updater plugin.
If a newer signed version is available, the user sees a persistent toast with an `Update now` action.

On Windows, install mode is `passive`, so the installer shows minimal progress and applies the update with little user interaction.
