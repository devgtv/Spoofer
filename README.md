# System ID Spoofer — Windows 11

A lightweight Python tool to spoof hardware and software identifiers on Windows 11.

## Features

| # | Spoof Target | Description |
|---|---|---|
| 1 | **HWID** | Hardware Profile GUID |
| 2 | **MAC Address** | Network adapter MAC (Ethernet / Wi-Fi) |
| 3 | **Machine GUID** | `MachineGuid` in `SOFTWARE\Microsoft\Cryptography` |
| 4 | **Computer Name** | Hostname across all registry locations |
| 5 | **Windows Product ID** | Product ID in `CurrentVersion` keys |
| 6 | **Install Date** | Windows installation timestamp |
| 7 | **Disk IDs** | Disk and CD-ROM enumeration strings |
| 8 | **GPU ID** | Display adapter registry identifiers |
| 9 | **SMBIOS / BIOS** | Baseboard serial, system serial, BIOS version |
| 10 | **Peripheral Drivers** | Auto-detect connected peripherals and replace driver info with generic names |
| 11 | **TPM Reset** | Clear TPM-derived keys and registry cache (EK is hardware-bound) |
| 12 | **Spoof ALL** | Run all of the above in one go |

## Requirements

- **Windows 11** (also works on Windows 10 22H2+)
- **Python 3.10+**
- **Administrator privileges** (the program will request elevation automatically)
- No external dependencies — uses only the Python standard library

## Usage

```
python spoofer.py
```

Or run the prebuilt `spoofer.exe` as Administrator.

## Logging

All changes are saved to `spoofer_log.json` with timestamps and old/new values, so you can review what was modified.

## Important Notes

- **Run as Administrator.** The program auto-requests elevation if needed.
- **Disable Windows Defender / antivirus** if it flags a false positive (the tool modifies registry keys, which can trigger heuristic detections).
- Some changes (Computer Name, Peripherals, TPM Reset, certain SMBIOS entries) **require a restart** to take effect.
- Disk firmware serial numbers and the TPM Endorsement Key (EK) cannot be changed via software alone.
- **TPM Reset** will invalidate BitLocker, Windows Hello, and any credentials stored in the TPM. You will be asked to confirm before proceeding.

## Contact

Questions, issues, or suggestions:
- **Discord:** gtvdev
- **Twitter:** @gtvdev_fialho
