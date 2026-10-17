import os
import re
import json
from datetime import datetime
from pathlib import Path

AUDIO_DIRS = [
    "/sdcard/Call",
    "/sdcard/Recordings",
    "/sdcard/VoiceRecorder",
    "/sdcard/Sounds",
    "/sdcard/Audio",
    "/sdcard/WhatsApp/Media/WhatsApp Audio",
    "/sdcard/WhatsApp/Media/WhatsApp Voice Notes",
    "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Audio",
    "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Voice Notes"
]

class AudioRecovery:
    def __init__(self, adb_manager, output_dir=None):
        self.adb = adb_manager
        if output_dir is None:
            self.output_dir = Path(__file__).resolve().parent.parent / "recovered_data" / "audio"
        else:
            self.output_dir = Path(output_dir) / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_recordings(self, serial=None):
        """
        Scans device storage for call recordings and voice notes, pulls them,
        and parses metadata from file names.
        """
        prefix = ["-s", serial] if serial else []
        recordings = []

        # 1. Scan storage folders
        for remote_dir in AUDIO_DIRS:
            cmd = prefix + ["shell", "find", remote_dir, "-type", "f", 
                           "\\(", "-name", "*.m4a", "-o", "-name", "*.amr", "-o", "-name", "*.mp3", "-o", "-name", "*.wav", "-o", "-name", "*.opus", "\\)", 
                           "2>/dev/null"]
            success, out = self.adb.run_cmd(cmd, timeout=20)
            if success and out.strip():
                for remote_path in out.strip().splitlines():
                    remote_path = remote_path.strip()
                    if not remote_path:
                        continue
                    file_name = Path(remote_path).name
                    local_dest = self.output_dir / file_name

                    # Pull audio file
                    if not local_dest.exists() or local_dest.stat().st_size == 0:
                        pull_ok, _ = self.adb.run_cmd(prefix + ["pull", remote_path, str(local_dest)], timeout=30)
                        if not pull_ok:
                            continue

                    # Parse metadata
                    info = self._parse_audio_metadata(local_dest, remote_path)
                    recordings.append(info)

        # 2. Also check if files already exist locally in recovered_data/audio
        for f in self.output_dir.glob("*.*"):
            if f.suffix.lower() in [".m4a", ".amr", ".mp3", ".wav", ".opus"]:
                if not any(r["local_file"] == f.name for r in recordings):
                    recordings.append(self._parse_audio_metadata(f, str(f)))

        # Sort recordings by date descending
        recordings.sort(key=lambda x: x.get("timestamp_raw", 0), reverse=True)

        # Save catalog
        catalog_path = self.output_dir / "recordings_catalog.json"
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(recordings, f, indent=2, ensure_ascii=False)

        return recordings

    def _parse_audio_metadata(self, local_path, remote_path):
        fname = local_path.name
        fsize = local_path.stat().st_size if local_path.exists() else 0
        size_mb = round(fsize / (1024 * 1024), 2)
        size_str = f"{size_mb} MB" if size_mb >= 1.0 else f"{round(fsize/1024, 1)} KB"

        # Pattern: Call recording <Name or Number>_<YYMMDD>_<HHMMSS>.m4a
        # Example: Call recording Saranya Laksh_260830_152949.m4a
        contact_name = "Voice Audio"
        phone_number = ""
        call_date = "Unknown"
        timestamp_raw = 0

        match = re.search(r"Call recording (.*?)_(\d{6})_(\d{6})", fname, re.IGNORECASE)
        if match:
            target = match.group(1).strip()
            date_part = match.group(2)  # YYMMDD e.g. 260830 -> 2026-08-30
            time_part = match.group(3)  # HHMMSS e.g. 152949 -> 15:29:49

            if re.match(r"^\+?\d{10,13}$", target):
                phone_number = target
                contact_name = "Unknown Caller"
            else:
                contact_name = target

            try:
                dt = datetime.strptime(f"20{date_part} {time_part}", "%Y%m%d %H%M%S")
                call_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                timestamp_raw = int(dt.timestamp())
            except Exception:
                pass
        else:
            # WhatsApp or Voice Memo pattern
            contact_name = "Voice Note / Memo"
            if "whatsapp" in remote_path.lower():
                contact_name = "WhatsApp Audio / Note"
            try:
                mtime = local_path.stat().st_mtime
                call_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                timestamp_raw = int(mtime)
            except Exception:
                pass

        return {
            "title": fname,
            "contact_name": contact_name,
            "phone_number": phone_number,
            "date": call_date,
            "timestamp_raw": timestamp_raw,
            "file_size": size_str,
            "file_type": local_path.suffix.upper().replace(".", ""),
            "local_file": fname,
            "stream_url": f"/audio_data/{fname}",
            "remote_path": remote_path
        }
