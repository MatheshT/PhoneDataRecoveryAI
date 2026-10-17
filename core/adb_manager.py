import os
import sys
import shutil
import zipfile
import subprocess
import requests
from pathlib import Path

GOOGLE_ADB_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"

class ADBManager:
    def __init__(self, base_dir=None):
        if base_dir is None:
            self.base_dir = Path(__file__).resolve().parent.parent
        else:
            self.base_dir = Path(base_dir)
        self.bin_dir = self.base_dir / "bin"
        self.adb_exe = self._locate_adb()

    def _locate_adb(self):
        # 1. Check system PATH
        adb_path = shutil.which("adb")
        if adb_path:
            return Path(adb_path)

        # 2. Check local project bin folder
        local_adb = self.bin_dir / "platform-tools" / "adb.exe"
        if local_adb.exists():
            return local_adb

        # 3. Check Android SDK default path
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            sdk_adb = Path(local_appdata) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
            if sdk_adb.exists():
                return sdk_adb

        return None

    def ensure_adb(self, progress_callback=None):
        """Downloads official Google Platform Tools if adb is not found."""
        if self.adb_exe and self.adb_exe.exists():
            return True, f"ADB found at: {self.adb_exe}"

        self.bin_dir.mkdir(parents=True, exist_ok=True)
        zip_path = self.bin_dir / "platform-tools.zip"

        if progress_callback:
            progress_callback("ADB not found. Downloading Google Android Platform-Tools...")

        try:
            response = requests.get(GOOGLE_ADB_URL, stream=True, timeout=30)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            if progress_callback:
                progress_callback("Extracting ADB binaries...")

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.bin_dir)

            if zip_path.exists():
                zip_path.unlink()

            target_exe = self.bin_dir / "platform-tools" / "adb.exe"
            if target_exe.exists():
                self.adb_exe = target_exe
                return True, f"ADB successfully installed at: {self.adb_exe}"
            else:
                return False, "Extraction completed but adb.exe was not found."

        except Exception as e:
            return False, f"Failed to download ADB: {str(e)}"

    def run_cmd(self, args, timeout=30, binary=False):
        """Runs an ADB command and returns (success, output)."""
        if not self.adb_exe:
            return False, "ADB executable not configured."

        cmd = [str(self.adb_exe)] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                check=False
            )
            if binary:
                return (result.returncode == 0), result.stdout
            else:
                stdout_str = result.stdout.decode('utf-8', errors='ignore')
                stderr_str = result.stderr.decode('utf-8', errors='ignore')
                if result.returncode == 0:
                    return True, stdout_str.strip()
                return False, stderr_str.strip() or stdout_str.strip()
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s: {' '.join(args)}"
        except Exception as e:
            return False, f"Execution error: {str(e)}"

    def get_connected_devices(self):
        """Returns list of connected devices with status."""
        success, out = self.run_cmd(["devices", "-l"])
        if not success:
            return []

        devices = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                status = parts[1]
                details = " ".join(parts[2:]) if len(parts) > 2 else ""
                devices.append({
                    "serial": serial,
                    "status": status,
                    "details": details
                })
        return devices

    def get_device_info(self, serial=None):
        """Retrieves manufacturer, model, and Android version."""
        prefix = ["-s", serial] if serial else []
        info = {}
        props = [
            ("model", "ro.product.model"),
            ("manufacturer", "ro.product.manufacturer"),
            ("android_version", "ro.build.version.release"),
            ("sdk_version", "ro.build.version.sdk")
        ]
        for key, prop in props:
            success, val = self.run_cmd(prefix + ["shell", "getprop", prop])
            info[key] = val if success else "Unknown"
        return info

    def get_advanced_device_info(self, serial=None):
        """Retrieves in-depth forensic hardware, battery, storage, and carrier details."""
        prefix = ["-s", serial] if serial else []
        info = self.get_device_info(serial)

        # 1. Battery status
        info["battery_level"] = "Unknown"
        info["battery_status"] = "Unknown"
        success, bat_out = self.run_cmd(prefix + ["shell", "dumpsys", "battery"])
        if success:
            for line in bat_out.splitlines():
                if "level:" in line:
                    info["battery_level"] = line.split(":")[-1].strip() + "%"
                elif "status:" in line:
                    st = line.split(":")[-1].strip()
                    info["battery_status"] = "Charging" if st == "2" else ("Discharging" if st == "3" else "Normal")

        # 2. Storage space
        info["storage_internal"] = "Unknown"
        info["storage_sdcard"] = "Unknown"
        success, df_out = self.run_cmd(prefix + ["shell", "df", "-h", "/data", "/sdcard"])
        if success:
            for line in df_out.splitlines():
                if "/data" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        info["storage_internal"] = f"Used {parts[2]} of {parts[1]} ({parts[4]} full)"
                elif "/sdcard" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        info["storage_sdcard"] = f"Used {parts[2]} of {parts[1]} ({parts[4]} full)"

        # 3. Carrier & Network
        success, op1 = self.run_cmd(prefix + ["shell", "getprop", "gsm.sim.operator.alpha"])
        success2, op2 = self.run_cmd(prefix + ["shell", "getprop", "gsm.operator.alpha"])
        info["carrier"] = op1 or op2 or "Unknown Carrier"

        # 4. Root status
        success, su_check = self.run_cmd(prefix + ["shell", "which", "su"])
        info["root_status"] = "Rooted (Superuser Available)" if (success and "su" in su_check) else "Standard / Unrooted (Non-Privileged)"

        # 5. Screen Resolution
        success, res = self.run_cmd(prefix + ["shell", "wm", "size"])
        if success and "Physical size:" in res:
            info["resolution"] = res.split(":")[-1].strip()
        else:
            info["resolution"] = "Standard Display"

        # 6. Uptime
        success, up = self.run_cmd(prefix + ["shell", "uptime"])
        info["uptime"] = up if success else "Unknown"

        return info

