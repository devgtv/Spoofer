import uuid
import subprocess
import random
import winreg
import ctypes
import sys
import os
import string
import json
from datetime import datetime


# ===============================
# Admin check
# ===============================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_admin():
    """Re-launch the script with elevated privileges."""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )


# ===============================
# Utility helpers
# ===============================
LOG_FILE = "spoofer_log.json"

# ===============================
# Generic peripheral replacements
# ===============================
GENERIC_DEVICES = {
    "mice": [
        ("USB Optical Mouse", "HID-0001"),
        ("Standard USB Mouse", "HID-0002"),
        ("HID-compliant mouse", "HID-0003"),
    ],
    "keyboards": [
        ("Standard 101/102-Key Keyboard", "HID-1001"),
        ("USB Keyboard Device", "HID-1002"),
        ("HID Keyboard Device", "HID-1003"),
    ],
    "headsets": [
        ("USB Audio Device", "USB-AUD-001"),
        ("High Definition Audio Device", "USB-AUD-002"),
    ],
    "controllers": [
        ("USB Gamepad", "HID-GP-001"),
        ("HID-compliant game controller", "HID-GP-002"),
    ],
}
GENERIC_MANUFACTURER = "(Standard system devices)"


def generate_random_mac():
    """Generate a valid locally-administered unicast MAC address."""
    mac = [random.randint(0x00, 0xFF) for _ in range(6)]
    mac[0] = (mac[0] & 0xFE) | 0x02  # unicast + locally administered
    return ":".join(f"{b:02X}" for b in mac)


def generate_random_serial(length=16):
    """Generate a random alphanumeric serial number."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def generate_random_computer_name(prefix="DESKTOP-"):
    """Generate a random computer name in Windows 11 style."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
    return f"{prefix}{suffix}"


def powershell(cmd, capture=True):
    """Run a PowerShell command and return the result."""
    args = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", cmd,
    ]
    result = subprocess.run(args, capture_output=capture, text=True)
    return result


def log_change(category, old_value, new_value):
    """Append a change record to the JSON log file."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "old_value": str(old_value),
        "new_value": str(new_value),
    }
    log = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r") as f:
                log = json.load(f)
        except Exception:
            log = []
    log.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=4)


def read_reg_value(hive, key_path, value_name):
    """Safely read a registry value, returns None on failure."""
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return val
    except OSError:
        return None


def set_reg_value(hive, key_path, value_name, value, reg_type=winreg.REG_SZ):
    """Safely set a registry value. Returns True on success."""
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, value_name, 0, reg_type, value)
        winreg.CloseKey(key)
        return True
    except OSError as e:
        print(f"  [!] Registry error ({key_path}\\{value_name}): {e}")
        return False


# ===============================
# SystemSpoofer class
# ===============================
class SystemSpoofer:
    def __init__(self):
        if not is_admin():
            print("[!] This program must be run as Administrator!")
            sys.exit(1)

    # ---- HWID (Hardware Profile GUID) ----
    def spoof_hwid(self):
        """Spoof the Hardware Profile GUID used by Windows 11."""
        print("\n[*] Spoofing HWID...")
        new_hwid = str(uuid.uuid4())

        paths = [
            r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\0001",
            r"SYSTEM\CurrentControlSet\Control\IDConfigDB\Hardware Profiles\Current",
        ]

        success = False
        for path in paths:
            old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, path, "HwProfileGuid")
            if set_reg_value(
                winreg.HKEY_LOCAL_MACHINE, path, "HwProfileGuid", f"{{{new_hwid}}}"
            ):
                log_change("HWID", old, new_hwid)
                print(f"  [+] {path} -> {new_hwid}")
                success = True

        if not success:
            print("  [-] Failed to spoof HWID")
        return new_hwid if success else None

    # ---- Machine GUID ----
    def spoof_guid(self):
        """Spoof the Machine GUID."""
        print("\n[*] Spoofing Machine GUID...")
        new_guid = str(uuid.uuid4())
        path = r"SOFTWARE\Microsoft\Cryptography"

        old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, path, "MachineGuid")
        if set_reg_value(winreg.HKEY_LOCAL_MACHINE, path, "MachineGuid", new_guid):
            log_change("MachineGuid", old, new_guid)
            print(f"  [+] New Machine GUID: {new_guid}")
            return new_guid

        print("  [-] Failed to spoof Machine GUID")
        return None

    # ---- MAC Address ----
    def spoof_mac(self, adapter_name=None):
        """
        Spoof the MAC address of a network adapter.
        Uses PowerShell Get-NetAdapter for reliable adapter discovery on Win11.
        Uses PowerShell Restart-NetAdapter for toggling (netsh is unreliable on Win11).
        """
        print("\n[*] Spoofing MAC Address...")

        # List available adapters if none specified
        if not adapter_name:
            print("  [i] Detecting network adapters...")
            result = powershell(
                "Get-NetAdapter | Select-Object -Property Name, InterfaceDescription, MacAddress, Status "
                "| Format-Table -AutoSize | Out-String -Width 200"
            )
            if result.returncode == 0 and result.stdout.strip():
                print(result.stdout)
            adapter_name = input("  Enter adapter name (e.g. Ethernet, Wi-Fi): ").strip()
            if not adapter_name:
                adapter_name = "Ethernet"

        new_mac = generate_random_mac()
        new_mac_no_sep = new_mac.replace(":", "")

        # Find the adapter in registry
        base_path = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}"
        found = False

        for i in range(1000):
            subkey_path = f"{base_path}\\{i:04d}"
            desc = read_reg_value(winreg.HKEY_LOCAL_MACHINE, subkey_path, "DriverDesc")
            if desc is None:
                continue
            if adapter_name.lower() in desc.lower():
                old_mac = read_reg_value(
                    winreg.HKEY_LOCAL_MACHINE, subkey_path, "NetworkAddress"
                )
                if set_reg_value(
                    winreg.HKEY_LOCAL_MACHINE,
                    subkey_path,
                    "NetworkAddress",
                    new_mac_no_sep,
                ):
                    found = True
                    log_change("MAC", old_mac, new_mac)
                    print(f"  [+] Registry updated for '{desc}'")

                    # Restart adapter via PowerShell (works on Win11)
                    print(f"  [*] Restarting adapter '{adapter_name}'...")
                    powershell(
                        f"Restart-NetAdapter -Name '{adapter_name}' -Confirm:$false"
                    )
                    print(f"  [+] New MAC: {new_mac}")
                break

        if not found:
            print(f"  [-] Adapter '{adapter_name}' not found in registry")
            return None

        return new_mac

    # ---- Computer Name ----
    def spoof_computer_name(self):
        """Spoof the computer name (Windows 11 stores it in multiple places)."""
        print("\n[*] Spoofing Computer Name...")
        new_name = generate_random_computer_name()

        paths_and_values = [
            (r"SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName", "ComputerName"),
            (r"SYSTEM\CurrentControlSet\Control\ComputerName\ActiveComputerName", "ComputerName"),
            (r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "Hostname"),
            (r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters", "NV Hostname"),
        ]

        success = False
        for path, val_name in paths_and_values:
            old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, path, val_name)
            if set_reg_value(winreg.HKEY_LOCAL_MACHINE, path, val_name, new_name):
                log_change("ComputerName", old, new_name)
                print(f"  [+] {val_name} -> {new_name}")
                success = True

        if success:
            print(f"  [+] New Computer Name: {new_name}")
            print("  [!] A restart is required for the name change to take effect.")
        else:
            print("  [-] Failed to spoof Computer Name")
        return new_name if success else None

    # ---- Windows Product ID ----
    def spoof_product_id(self):
        """Spoof the Windows Product ID stored in the registry."""
        print("\n[*] Spoofing Windows Product ID...")

        # Format: XXXXX-XXX-XXXXXXX-XXXXX
        parts = [
            "".join(random.choices(string.digits, k=5)),
            "".join(random.choices(string.digits, k=3)),
            "".join(random.choices(string.digits, k=7)),
            "".join(random.choices(string.digits, k=5)),
        ]
        new_product_id = "-".join(parts)

        paths = [
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            r"SOFTWARE\Microsoft\Windows\CurrentVersion",
        ]

        success = False
        for path in paths:
            old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, path, "ProductId")
            if set_reg_value(winreg.HKEY_LOCAL_MACHINE, path, "ProductId", new_product_id):
                log_change("ProductId", old, new_product_id)
                print(f"  [+] {path} -> {new_product_id}")
                success = True

        if not success:
            print("  [-] Failed to spoof Product ID")
        return new_product_id if success else None

    # ---- Windows Install Date ----
    def spoof_install_date(self):
        """Randomize the Windows installation date."""
        print("\n[*] Spoofing Install Date...")

        # Random date between 2022 and now
        now_ts = int(datetime.now().timestamp())
        min_ts = int(datetime(2022, 1, 1).timestamp())
        new_ts = random.randint(min_ts, now_ts)

        path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, path, "InstallDate")
        if set_reg_value(
            winreg.HKEY_LOCAL_MACHINE, path, "InstallDate", new_ts, winreg.REG_DWORD
        ):
            log_change("InstallDate", old, new_ts)
            new_date_str = datetime.fromtimestamp(new_ts).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  [+] New Install Date: {new_date_str}")
            return new_ts

        print("  [-] Failed to spoof Install Date")
        return None

    # ---- Disk / Volume Serial ----
    def spoof_disk_ids(self):
        """
        Spoof disk-related identifiers in the registry.
        Note: Actual disk firmware serials cannot be changed via software alone;
        this covers the registry-based identifiers that Win11 exposes.
        """
        print("\n[*] Spoofing Disk IDs...")

        # MountedDevices contains volume serial info
        # We randomize the boot volume GUID
        new_vol_guid = str(uuid.uuid4())

        paths = [
            (
                r"SYSTEM\CurrentControlSet\Services\disk\Enum",
                "0",
                f"SCSI\\Disk&Ven_SPOOFED&Prod_{generate_random_serial(8)}\\{generate_random_serial(12)}",
            ),
            (
                r"SYSTEM\CurrentControlSet\Services\cdrom\Enum",
                "0",
                f"SCSI\\CdRom&Ven_SPOOFED&Prod_{generate_random_serial(8)}\\{generate_random_serial(12)}",
            ),
        ]

        success = False
        for path, val_name, new_val in paths:
            old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, path, val_name)
            if set_reg_value(winreg.HKEY_LOCAL_MACHINE, path, val_name, new_val):
                log_change("DiskID", old, new_val)
                print(f"  [+] {val_name} -> {new_val[:60]}...")
                success = True

        if not success:
            print("  [-] Failed to spoof Disk IDs (some may require deeper access)")
        return success

    # ---- Display / GPU ID ----
    def spoof_gpu_id(self):
        """Spoof GPU-related registry identifiers."""
        print("\n[*] Spoofing GPU ID...")
        base_path = r"SYSTEM\CurrentControlSet\Enum\PCI"

        new_serial = generate_random_serial(20)
        success = False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, base_path, 0, winreg.KEY_READ
            )
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    if "VEN_" in subkey_name.upper() and "DEV_" in subkey_name.upper():
                        sub_path = f"{base_path}\\{subkey_name}"
                        try:
                            sub_key = winreg.OpenKey(
                                winreg.HKEY_LOCAL_MACHINE, sub_path, 0, winreg.KEY_READ
                            )
                            j = 0
                            while True:
                                try:
                                    instance = winreg.EnumKey(sub_key, j)
                                    instance_path = f"{sub_path}\\{instance}"
                                    old = read_reg_value(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        instance_path,
                                        "Driver",
                                    )
                                    # Only log what we find -- direct GPU driver
                                    # spoofing is limited without kernel-level access
                                    j += 1
                                except OSError:
                                    break
                            winreg.CloseKey(sub_key)
                        except OSError:
                            pass
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError as e:
            print(f"  [!] Could not enumerate PCI devices: {e}")

        # Spoof display device identifiers
        display_path = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E968-E325-11CE-BFC1-08002BE10318}\0000"
        old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, display_path, "ProviderName")
        if set_reg_value(
            winreg.HKEY_LOCAL_MACHINE,
            display_path,
            "UserModeDriverGUID",
            str(uuid.uuid4()),
        ):
            log_change("GPU_ID", "previous", new_serial)
            print(f"  [+] GPU registry identifiers spoofed")
            success = True

        if not success:
            print("  [-] GPU spoofing is limited without kernel-level drivers")
        return success

    # ---- SMBIOS Serial (via registry) ----
    def spoof_smbios(self):
        """
        Spoof SMBIOS-related data in the registry.
        Win11 reads System BIOS info from these keys.
        """
        print("\n[*] Spoofing SMBIOS / BIOS identifiers...")

        bios_path = r"HARDWARE\DESCRIPTION\System\BIOS"
        entries = {
            "BaseBoardSerialNumber": generate_random_serial(12),
            "SystemSerialNumber": generate_random_serial(12),
            "BIOSVersion": f"SPOOFED.{random.randint(100, 999)}",
            "SystemProductName": f"System Product Name {generate_random_serial(4)}",
            "SystemFamily": "Default",
        }

        success = False
        for val_name, new_val in entries.items():
            old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, bios_path, val_name)
            if set_reg_value(winreg.HKEY_LOCAL_MACHINE, bios_path, val_name, new_val):
                log_change("SMBIOS", old, f"{val_name}={new_val}")
                print(f"  [+] {val_name} -> {new_val}")
                success = True

        if not success:
            print("  [-] SMBIOS spoofing requires elevated access or firmware tools")
        return success

    # ---- TPM Reset ----
    def reset_tpm(self, skip_confirm=False):
        """
        Reset the TPM (Trusted Platform Module).
        This clears all TPM-derived keys (SRK) and regenerates them on next boot.

        WARNING: This will invalidate BitLocker, Windows Hello PINs/biometrics,
        and any app that stores credentials in the TPM.

        The Endorsement Key (EK) is hardware-burned and cannot be changed,
        but clearing the TPM resets all derived identifiers that software can see.
        """
        print("\n[*] TPM Reset...")
        print("  ┌──────────────────────────────────────────────┐")
        print("  │            !! IMPORTANT WARNING !!           │")
        print("  │                                              │")
        print("  │  Clearing the TPM will:                      │")
        print("  │   - Reset all TPM-derived keys               │")
        print("  │   - Invalidate BitLocker encryption          │")
        print("  │   - Remove Windows Hello PIN/biometrics      │")
        print("  │   - Break apps using TPM-stored credentials  │")
        print("  │   - Require a restart to take effect         │")
        print("  │                                              │")
        print("  │  The TPM Endorsement Key (EK) is burned in   │")
        print("  │  hardware and CANNOT be changed. However,    │")
        print("  │  all derived keys will be regenerated fresh. │")
        print("  └──────────────────────────────────────────────┘")

        if not skip_confirm:
            confirm = input("\n  Type 'YES' to confirm TPM reset: ").strip()
            if confirm != "YES":
                print("  [i] TPM reset cancelled.")
                return False

        success = False

        # Step 1: Disable TPM auto-provisioning (prevents Windows from
        # re-provisioning with old derived data before we clear)
        print("\n  [*] Step 1/4: Disabling TPM auto-provisioning...")
        result = powershell("Disable-TpmAutoProvisioning -OnlyForNextRestart")
        if result.returncode == 0:
            print("  [+] Auto-provisioning disabled for next restart")
        else:
            print(f"  [!] Could not disable auto-provisioning: {result.stderr.strip()}")

        # Step 2: Clear the TPM
        print("  [*] Step 2/4: Clearing TPM...")
        result = powershell("Clear-Tpm")
        if result.returncode == 0:
            print("  [+] TPM cleared successfully")
            log_change("TPM", "previous_keys", "cleared")
            success = True
        else:
            # Some systems need the owner auth, try with Initialize-Tpm
            print(f"  [!] Clear-Tpm failed: {result.stderr.strip()}")
            print("  [*] Trying alternative method...")
            result = powershell("Initialize-Tpm -AllowClear -AllowPhysicalPresence")
            if result.returncode == 0:
                print("  [+] TPM initialized with clear flag")
                log_change("TPM", "previous_keys", "cleared_via_initialize")
                success = True
            else:
                print(f"  [!] Alternative method failed: {result.stderr.strip()}")

        # Step 3: Clean up TPM-related registry entries that cache identifiers
        print("  [*] Step 3/4: Cleaning TPM registry cache...")
        tpm_reg_paths = [
            (r"SYSTEM\CurrentControlSet\Services\TPM\WMI", "WindowsAIKHash"),
            (r"SYSTEM\CurrentControlSet\Services\TPM\WMI", "PlatformId"),
        ]
        for path, val_name in tpm_reg_paths:
            old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, path, val_name)
            if old is not None:
                new_val = generate_random_serial(32)
                if set_reg_value(winreg.HKEY_LOCAL_MACHINE, path, val_name, new_val):
                    log_change("TPM_Registry", old, f"{val_name}={new_val}")
                    print(f"  [+] {val_name} -> {new_val}")

        # Randomize EK certificate registry cache (not the actual EK,
        # just what Windows cached from it)
        ek_cert_path = r"SYSTEM\CurrentControlSet\Services\TPM\ODMS\OpcTpmData"
        for val in ["EkCertificatePresent", "RecommendedDeniedByEk"]:
            old = read_reg_value(winreg.HKEY_LOCAL_MACHINE, ek_cert_path, val)
            if old is not None:
                set_reg_value(
                    winreg.HKEY_LOCAL_MACHINE, ek_cert_path, val,
                    0, winreg.REG_DWORD,
                )
                log_change("TPM_Registry", old, f"{val}=0")

        # Step 4: Re-enable auto-provisioning so TPM gets fresh keys on reboot
        print("  [*] Step 4/4: Re-enabling TPM auto-provisioning...")
        result = powershell("Enable-TpmAutoProvisioning")
        if result.returncode == 0:
            print("  [+] Auto-provisioning re-enabled")
        else:
            print(f"  [!] Could not re-enable: {result.stderr.strip()}")

        if success:
            print("\n  [+] TPM reset complete!")
            print("  [!] A RESTART IS REQUIRED for changes to take effect.")
            print("  [i] On reboot, Windows will generate fresh TPM-derived keys.")
            print("  [i] You will need to re-setup Windows Hello and re-enable BitLocker.")
        else:
            print("\n  [-] TPM reset failed.")
            print("  [i] Some systems require clearing the TPM from BIOS/UEFI settings.")
            print("  [i] Restart -> BIOS -> Security -> TPM -> Clear TPM")

        return success

    # ---- Peripheral Drivers ----
    def spoof_peripherals(self):
        """
        Detect real peripheral devices (mouse, keyboard, headset, controller)
        and replace their driver descriptions with generic names.
        """
        print("\n[*] Spoofing Peripheral Drivers...")
        print("  [i] Detecting connected peripherals and masking with generic drivers...")

        success_count = 0

        # HID devices (mice, keyboards)
        hid_base = r"SYSTEM\CurrentControlSet\Enum\HID"
        success_count += self._spoof_hid_devices(hid_base)

        # USB devices (headsets, controllers, general USB peripherals)
        usb_base = r"SYSTEM\CurrentControlSet\Enum\USB"
        success_count += self._spoof_usb_devices(usb_base)

        # USB Audio (headsets)
        success_count += self._spoof_usb_audio()

        # HID class driver descriptions
        hid_class_paths = [
            (r"SYSTEM\CurrentControlSet\Control\Class\{4D36E96F-E325-11CE-BFC1-08002BE10318}", "mice"),
            (r"SYSTEM\CurrentControlSet\Control\Class\{4D36E96B-E325-11CE-BFC1-08002BE10318}", "keyboards"),
            (r"SYSTEM\CurrentControlSet\Control\Class\{745A17A0-74D3-11D0-B6FE-00A0C90F57DA}", "mice"),
        ]

        for class_path, device_type in hid_class_paths:
            success_count += self._spoof_class_driver(class_path, device_type)

        if success_count > 0:
            print(f"\n  [+] Successfully spoofed {success_count} peripheral entries")
            print("  [+] All peripherals masked as generic devices")
            print("  [!] A restart is required for all changes to take effect.")
        else:
            print("  [-] No peripheral entries were modified")
            print("  [i] This can happen if no HID/USB peripherals are enumerated yet")

        return success_count > 0

    def _spoof_hid_devices(self, hid_base):
        """Enumerate HID subkeys and replace real device info with generic."""
        count = 0
        try:
            base_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, hid_base, 0,
                winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS
            )
            i = 0
            while True:
                try:
                    vid_pid = winreg.EnumKey(base_key, i)
                    vid_path = f"{hid_base}\\{vid_pid}"
                    try:
                        vid_key = winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE, vid_path, 0,
                            winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS
                        )
                        j = 0
                        while True:
                            try:
                                instance = winreg.EnumKey(vid_key, j)
                                instance_path = f"{vid_path}\\{instance}"

                                current_desc = read_reg_value(
                                    winreg.HKEY_LOCAL_MACHINE, instance_path, "DeviceDesc"
                                )
                                dtype = self._detect_device_type(current_desc)

                                if dtype and GENERIC_DEVICES.get(dtype):
                                    fake_name, fake_id = random.choice(GENERIC_DEVICES[dtype])
                                    old_desc = current_desc

                                    set_reg_value(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        instance_path, "DeviceDesc",
                                        f"@input.inf,%{fake_id}%;{fake_name}",
                                    )
                                    set_reg_value(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        instance_path, "Mfg",
                                        f"@input.inf,%mfg%;{GENERIC_MANUFACTURER}",
                                    )
                                    set_reg_value(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        instance_path, "FriendlyName",
                                        fake_name,
                                    )
                                    log_change(f"Peripheral_HID_{dtype}", old_desc, fake_name)
                                    print(f"  [+] HID {dtype}: {old_desc} -> {fake_name}")
                                    count += 1
                                j += 1
                            except OSError:
                                break
                        winreg.CloseKey(vid_key)
                    except OSError:
                        pass
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(base_key)
        except OSError:
            pass
        return count

    def _spoof_usb_devices(self, usb_base):
        """Enumerate USB subkeys and replace real peripheral info with generic."""
        count = 0
        try:
            base_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, usb_base, 0,
                winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS
            )
            i = 0
            while True:
                try:
                    vid_pid = winreg.EnumKey(base_key, i)
                    if "VID_" not in vid_pid.upper():
                        i += 1
                        continue
                    vid_path = f"{usb_base}\\{vid_pid}"
                    try:
                        vid_key = winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE, vid_path, 0,
                            winreg.KEY_READ | winreg.KEY_ENUMERATE_SUB_KEYS
                        )
                        j = 0
                        while True:
                            try:
                                instance = winreg.EnumKey(vid_key, j)
                                instance_path = f"{vid_path}\\{instance}"

                                current_desc = read_reg_value(
                                    winreg.HKEY_LOCAL_MACHINE, instance_path, "DeviceDesc"
                                )
                                dtype = self._detect_device_type(current_desc)

                                if dtype and GENERIC_DEVICES.get(dtype):
                                    fake_name, fake_id = random.choice(GENERIC_DEVICES[dtype])

                                    set_reg_value(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        instance_path, "DeviceDesc",
                                        f"@input.inf,%{fake_id}%;{fake_name}",
                                    )
                                    set_reg_value(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        instance_path, "Mfg",
                                        f"@input.inf,%mfg%;{GENERIC_MANUFACTURER}",
                                    )
                                    set_reg_value(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        instance_path, "FriendlyName",
                                        fake_name,
                                    )
                                    log_change(f"Peripheral_USB_{dtype}", current_desc, fake_name)
                                    print(f"  [+] USB {dtype}: {current_desc} -> {fake_name}")
                                    count += 1
                                j += 1
                            except OSError:
                                break
                        winreg.CloseKey(vid_key)
                    except OSError:
                        pass
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(base_key)
        except OSError:
            pass
        return count

    def _spoof_usb_audio(self):
        """Replace real USB audio device descriptions with generic."""
        count = 0
        audio_class = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E96C-E325-11CE-BFC1-08002BE10318}"

        for idx in range(20):
            subkey_path = f"{audio_class}\\{idx:04d}"
            desc = read_reg_value(winreg.HKEY_LOCAL_MACHINE, subkey_path, "DriverDesc")
            if desc is None:
                continue
            desc_lower = desc.lower()
            if any(kw in desc_lower for kw in ["usb", "audio", "headset", "headphone", "microphone"]):
                fake_name, _ = random.choice(GENERIC_DEVICES["headsets"])
                old = desc
                set_reg_value(
                    winreg.HKEY_LOCAL_MACHINE, subkey_path,
                    "DriverDesc", fake_name,
                )
                set_reg_value(
                    winreg.HKEY_LOCAL_MACHINE, subkey_path,
                    "ProviderName", GENERIC_MANUFACTURER,
                )
                log_change("Peripheral_Audio", old, fake_name)
                print(f"  [+] Audio: {old} -> {fake_name}")
                count += 1
        return count

    def _spoof_class_driver(self, class_path, device_type):
        """Replace real driver descriptions with generic inside a device class."""
        count = 0
        device_list = GENERIC_DEVICES.get(device_type, [])
        if not device_list:
            return 0

        for idx in range(30):
            subkey_path = f"{class_path}\\{idx:04d}"
            desc = read_reg_value(winreg.HKEY_LOCAL_MACHINE, subkey_path, "DriverDesc")
            if desc is None:
                continue
            fake_name, _ = random.choice(device_list)
            old = desc
            set_reg_value(
                winreg.HKEY_LOCAL_MACHINE, subkey_path,
                "DriverDesc", fake_name,
            )
            set_reg_value(
                winreg.HKEY_LOCAL_MACHINE, subkey_path,
                "ProviderName", GENERIC_MANUFACTURER,
            )
            log_change(f"Peripheral_Class_{device_type}", old, fake_name)
            print(f"  [+] Class {device_type}: {old} -> {fake_name}")
            count += 1
        return count

    @staticmethod
    def _detect_device_type(description):
        """Detect peripheral type from a registry device description string."""
        if not description:
            return None
        desc = description.lower()
        if any(kw in desc for kw in ["mouse", "pointing", "trackball", "trackpad"]):
            return "mice"
        if any(kw in desc for kw in ["keyboard", "keyman", "kbd"]):
            return "keyboards"
        if any(kw in desc for kw in ["audio", "headset", "headphone", "microphone", "speaker"]):
            return "headsets"
        if any(kw in desc for kw in ["gamepad", "controller", "joystick", "xinput"]):
            return "controllers"
        return None

    # ---- Spoof All ----
    def spoof_all(self):
        """Run all available spoof methods."""
        print("\n" + "=" * 50)
        print("  SPOOFING ALL IDENTIFIERS")
        print("=" * 50)

        results = {
            "HWID": self.spoof_hwid(),
            "Machine GUID": self.spoof_guid(),
            "MAC Address": self.spoof_mac("Ethernet"),
            "Computer Name": self.spoof_computer_name(),
            "Product ID": self.spoof_product_id(),
            "Install Date": self.spoof_install_date(),
            "Disk IDs": self.spoof_disk_ids(),
            "GPU ID": self.spoof_gpu_id(),
            "SMBIOS": self.spoof_smbios(),
            "Peripherals": self.spoof_peripherals(),
            "TPM Reset": self.reset_tpm(skip_confirm=True),
        }

        print("\n" + "=" * 50)
        print("  RESULTS SUMMARY")
        print("=" * 50)
        for name, result in results.items():
            status = "OK" if result else "FAILED"
            print(f"  [{status:>6}] {name}: {result if result else 'N/A'}")
        print("=" * 50)

        return results


# ===============================
# Main menu
# ===============================
def main():
    if not is_admin():
        request_admin()
        return

    spoofer = SystemSpoofer()

    while True:
        print("\n" + "=" * 40)
        print("  SYSTEM ID SPOOFER - Windows 11")
        print("=" * 40)
        print("  1.  Spoof HWID")
        print("  2.  Spoof MAC Address")
        print("  3.  Spoof Machine GUID")
        print("  4.  Spoof Computer Name")
        print("  5.  Spoof Windows Product ID")
        print("  6.  Spoof Install Date")
        print("  7.  Spoof Disk IDs")
        print("  8.  Spoof GPU ID")
        print("  9.  Spoof SMBIOS / BIOS Serials")
        print("  10. Spoof Peripheral Drivers")
        print("  11. Reset TPM")
        print("  12. Spoof ALL")
        print("  0.  Exit")
        print("=" * 40)

        choice = input("\nSelect an option: ").strip()

        if choice == "1":
            spoofer.spoof_hwid()
        elif choice == "2":
            spoofer.spoof_mac()
        elif choice == "3":
            spoofer.spoof_guid()
        elif choice == "4":
            spoofer.spoof_computer_name()
        elif choice == "5":
            spoofer.spoof_product_id()
        elif choice == "6":
            spoofer.spoof_install_date()
        elif choice == "7":
            spoofer.spoof_disk_ids()
        elif choice == "8":
            spoofer.spoof_gpu_id()
        elif choice == "9":
            spoofer.spoof_smbios()
        elif choice == "10":
            spoofer.spoof_peripherals()
        elif choice == "11":
            spoofer.reset_tpm()
        elif choice == "12":
            spoofer.spoof_all()
        elif choice == "0":
            print("\n[*] Exiting. Some changes may require a restart.")
            break
        else:
            print("[!] Invalid option!")

        input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()
