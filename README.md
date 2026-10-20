# Sony Bravia Network Debloat & Performance Toolkit

An ADB-over-LAN debloating, launcher replacement, and runtime optimization toolkit for **Sony Bravia Android TV / Google TV** models (both Realtek `VU1/VU2` and MediaTek `ATV2/ATV3/UR1/VH2` platforms).

## Why Sony Bravia TVs Lag (and What This Fixes)

Many Sony Bravia Android/Google TV models ship with only **2 GB of RAM**, a 32-bit ARM `cortex-a7` / `cortex-a55` execution profile, and 600 MB of ZRAM swap. Out of the box, memory and UI responsiveness are bottlenecked by five factors:

1. **Bloated Stock Home Screen & Ad Daemons:** `com.google.android.tvlauncher` / `launcherx` and `com.google.android.tvrecommendations` (~42 MB RAM) continuously fetch video banners and recommendation rows.
   - **Fix:** Sideloads the latest release of **[Projectivy Launcher](https://github.com/spocky/miproja1)** (`com.spocky.projengmenu`), registers it as the native OS home activity (`cmd package set-home-activity`), and disables the stock launcher and recommendation engines.
2. **Always-Resident Background Daemons & Telemetry (`--user 0`):**
   - `com.google.android.tungsten.setupwraith` (**~74 MB RAM** — initial setup wizard daemon left running indefinitely)
   - `com.google.android.katniss` (**~58 MB RAM** — Google Assistant voice interactor daemon)
   - `com.android.settings.intelligence` (**~56 MB RAM** — background settings search indexer)
   - `tv.samba.ssm` (Samba Interactive TV Automatic Content Recognition screen-tracking spyware)
   - `com.sony.qrmt`, `com.sony.dtv.demo`, `android.autoinstalls.config.Sony.*`, `com.sony.dtv.smarthelp`, `com.sony.dtv.helpguidecontents` (Sony retail demos, telemetry, and help bloat)
   - **Fix:** Disables and uninstalls ~35–40 bloatware packages for `--user 0` while explicitly protecting **Chromecast Built-in** (`com.google.android.apps.mediashell`), **Over-the-Air / Coax Live TV & Realtek/MediaTek tuner HALs**, **HDMI/CEC**, and **Streaming Apps** (preserving Widevine L1 DRM).
3. **`InputDispatcher` & Accessibility D-Pad Latency:**
   - When `accessibility_enabled=1` (or `com.google.android.marvin.talkback` is active), Android routes every D-pad key event synchronously through `AccessibilityManagerService` (`filterKeyEvent`) and forces Leanback grids to serialize accessibility node trees on every tile focus change.
   - **Fix:** Since the stock launcher is disabled and Projectivy is set as the native system home activity, Accessibility interception is unnecessary—the script clears `enabled_accessibility_services`, sets `accessibility_enabled=0`, and disables `talkback`.
4. **Slow Focus Animators & D-Pad Key-Repeat Delay:**
   - **Fix:** Lowers `long_press_timeout` from `400ms` to `250ms` for faster hold-to-scroll initiation, and sets `window_animation_scale`, `transition_animation_scale`, and `animator_duration_scale` to `0.0` (which also terminates `INFINITE` `ValueAnimator` focus "breathing" loops on frame 1 so focused tiles display a clean static highlight with zero idle GPU redraws).
5. **On-the-Fly JIT Compilation & ZRAM Swap Thrashing:**
   - **Fix:** Caps `ActivityManager` `max_cached_processes=4` to stop background apps from thrashing ZRAM swap, and runs `cmd package compile -m speed` (`dex2oat` Ahead-of-Time native ARM compilation) across core system UI and installed streaming apps.

---

## Prerequisites

1. **Host Tools:** `adb` (`brew install --cask android-platform-tools` on macOS), `python3`, and `curl`.
2. **Enable ADB Debugging on the TV:**
   - On the Sony remote: **Settings $\rightarrow$ System (or Device Preferences) $\rightarrow$ About**.
   - Scroll to **Android TV OS build** and press **OK 7 times** to unlock Developer mode.
   - Go back one menu to **Developer options** and enable **USB debugging** (and **Network debugging** if listed).

---

## Quick Start

```bash
# 1. Auto-discover your Bravia TV on the LAN (mDNS + ARP MAC) and generate .bravia.env
./bravia-opt.sh init

# 2. Run the full pipeline (discover -> backup -> audit -> install Projectivy -> debloat -> tune)
./bravia-opt.sh all
```

> The first time `adb` connects, check **"Always allow from this computer"** on your TV screen and press **OK** on the remote.

---

## CLI Reference

```bash
./bravia-opt.sh init                      # Scan LAN via mDNS/ARP and write local .bravia.env
./bravia-opt.sh discover                  # Resolve TV IP (mDNS -> ARP MAC -> Fallback) & verify ADB
./bravia-opt.sh audit                     # Show RAM, /data storage, UI settings & active bloatware
./bravia-opt.sh backup                    # Save package & global settings snapshot to ./backups/
./bravia-opt.sh install-launcher          # Sideload Projectivy Launcher & disable stock launchers
./bravia-opt.sh debloat [--dry-run]       # Strip Sony bloat, Samba TV, SetupWraith, Katniss, etc.
./bravia-opt.sh tune                      # Apply D-pad latency, animation, process cap & AOT compilation
./bravia-opt.sh remote [port]             # Launch Web Remote & Control Center (Mac + Mobile PWA on port 8765)
./bravia-opt.sh restore [dir|package]     # Restore a single package or roll back an entire backup
```

---

## Configuration (`.bravia.env` & `packages.conf`)

- **`.bravia.env`** *(gitignored, generated by `./bravia-opt.sh init` from `.bravia.env.example`)*:
  Stores your TV's mDNS hostname (`TV_MDNS_HOST`), hardware MAC address (`TV_MAC` for DHCP IP changes), fallback IP (`TV_FALLBACK_IP`), and tuning parameters (`ANIMATION_SCALE`, `LONG_PRESS_TIMEOUT`, `MAX_CACHED_PROCESSES`).
  - *Tip:* If you prefer a gentle focus "breathing" animation instead of a static focus highlight, set `ANIMATION_SCALE="0.6"` in `.bravia.env` and run `./bravia-opt.sh tune`.
- **`packages.conf`**:
  Contains `PROTECTED_PACKAGES`, `SONY_BLOAT_PACKAGES`, `TELEMETRY_AND_GOOGLE_BLOAT`, and `STOCK_LAUNCHER_PACKAGES` (supports shell globs such as `android.autoinstalls.config.Sony.*` and `com.realtek.*`).

---

## Restoring Packages / Rollback

No packages are deleted from the read-only `/system` partition; all removals target `--user 0` and are logged to `backups/latest/removed_packages.log`.

```bash
# Re-enable a single package (e.g., restore Google Assistant voice search)
./bravia-opt.sh restore com.google.android.katniss

# Restore all removed packages and stock animation/timeout settings
./bravia-opt.sh restore latest
```
