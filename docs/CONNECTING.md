# Connecting the phone to the PC

DeskGadget supports three routes. All of them end at the same WebSocket
(`/ws`) on TCP port `8787`; the phone picks whichever one is available and
reconnects automatically when it changes.

| Route | Needs | Discovery | Best for |
|---|---|---|---|
| **Wi-Fi** | Phone and PC on the same network | automatic (mDNS + UDP beacon) | normal desk use |
| **USB tethering** | The phone's *USB tethering* toggle | automatic (UDP beacon on the cable link) | no Wi-Fi, or a locked-down router |
| **USB + adb** | USB debugging enabled once | automatic (`127.0.0.1` via `adb reverse`) | no Wi-Fi and no tethering |

The phone remembers each transport separately, so unplugging the cable or
leaving the Wi-Fi network never leaves it pointed at a dead address.

---

## Wi-Fi

1. Start DeskGadget on the PC. The dashboard prints the address, e.g.
   `http://192.168.0.250:8787`.
2. Put the phone on the same network.
3. Open the app. The PC appears in the list within a second or two; tap it, or
   let it connect on its own when it is the only server found.

Discovery works two ways at once — mDNS (`_deskgadget._tcp`) and a UDP probe on
port `8787`. If a router blocks one, the other usually still answers.

**If nothing appears:**

- Windows firewall: allow **TCP 8787** and **UDP 8787** (the installer adds a
  program rule for `deskgadget.exe`, so a normal install needs no change).
- Set the Wi-Fi network profile to **Private**, not Public.
- Disable client isolation / "AP isolation" on the router, or move off a guest
  network.
- Turn off any VPN on the phone while connecting.
- Worst case, type the PC address shown in the dashboard into **PC ADDRESS**.

---

## USB tethering (no adb, no developer options)

This turns the cable into a small network. Nothing needs to be enabled on the
phone except the tethering toggle.

1. Plug in a **data-capable** cable.
2. On the phone: **Settings → Connections → Mobile Hotspot and Tethering →
   USB tethering** (or the quick-settings tile). A "no internet" warning is
   fine — the local link still works.
3. Open the app. The PC appears tagged **USB** at `192.168.42.x` and connects.

### Why it works

Android gives the PC an address on the phone's tethering subnet
(`192.168.42.0/24`). The server's beacon answers on that link, and the app
**trusts the source address of the reply** rather than the address the PC
advertises — a PC with both Wi-Fi and a cable would otherwise advertise its
Wi-Fi IP, which is unroutable from the cable.

The app also classifies interfaces (`rndis`, `usb`, `ncm`, `eth`, `enx`) so it
knows a cable is present and prefers that address at startup.

### Notes

- The tethering toggle resets when the cable is unplugged; flip it again next time.
- Android does not let an app enable tethering itself — it is a user-only
  toggle, by design.
- Windows may route internet through the phone while tethering is on. That does
  not affect the local socket.

---

## USB + adb

Use this when tethering is unavailable but USB debugging can be enabled.

1. Phone: unlock **Developer options** (tap *Build number* seven times), then
   enable **USB debugging**.
2. Plug in; accept the **Allow USB debugging?** prompt (tick *Always allow*).
3. The server runs `adb reverse tcp:8787 tcp:8787` for every attached device, so
   `127.0.0.1:8787` on the phone reaches the PC.
4. Open the app — it finds the server at `127.0.0.1` and connects.

The installer bundles `adb.exe`, so platform-tools do not need to be installed
separately. Check with:

```powershell
adb devices          # must say "device", not "unauthorized"
adb reverse --list   # tcp:8787 tcp:8787
```

If `adb devices` is empty, the cable is charge-only or USB debugging is off. If
it says `unauthorized`, accept the prompt on the phone.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "No server found automatically" | firewall, Public network profile, AP isolation, VPN |
| PC listed but "Can't reach the PC" | address changed; wait for rediscovery or retype it |
| Works on Wi-Fi, not on the cable | USB tethering is off, or the cable is charge-only |
| Works until the cable is pulled | expected: it reconnects over Wi-Fi if that transport was saved |
| `418`/timeout on a corporate network | client isolation; use tethering or adb |

The dashboard header always shows the current address, and
`%LOCALAPPDATA%\DeskGadget\data\server.log` records every connect and
disconnect.
