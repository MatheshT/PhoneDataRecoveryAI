import os
import re
import json
import hashlib
from datetime import datetime
from pathlib import Path

WHATSAPP_BASES = [
    "/sdcard/Android/media/com.whatsapp/WhatsApp",
    "/sdcard/WhatsApp"
]

TELEGRAM_BASE = "/sdcard/Android/data/org.telegram.messenger"

class WhatsAppRecovery:
    def __init__(self, adb_manager, output_dir=None):
        self.adb = adb_manager
        if output_dir is None:
            self.output_dir = Path(__file__).resolve().parent.parent / "recovered_data" / "whatsapp"
        else:
            self.output_dir = Path(output_dir) / "whatsapp"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "voice_notes").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "statuses").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "databases").mkdir(parents=True, exist_ok=True)

    def extract_whatsapp_artifacts(self, serial=None):
        """
        Scans device storage for:
        1. Encrypted WhatsApp Chat Databases (msgstore.db.crypt14 / crypt15).
        2. Real WhatsApp Voice Notes (PTT-*.opus).
        3. WhatsApp Statuses and media caches.
        4. Telegram session & media remnants.
        """
        prefix = ["-s", serial] if serial else []
        artifacts = {
            "databases": [],
            "voice_notes": [],
            "statuses": [],
            "telegram": {},
            "media_stats": {},
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 1. Extract Encrypted WhatsApp Databases
        for base_path in WHATSAPP_BASES:
            db_dir = f"{base_path}/Databases"
            success, out = self.adb.run_cmd(prefix + ["shell", "ls", "-la", db_dir], timeout=15)
            if success and out.strip():
                for line in out.strip().splitlines():
                    line = line.strip()
                    if not line or line.startswith("total ") or line.startswith("d"):
                        continue
                    parts = line.split(maxsplit=7)
                    if len(parts) >= 8:
                        fname = parts[7]
                        fsize = parts[4]
                        if "msgstore" in fname.lower():
                            local_dest = self.output_dir / "databases" / fname
                            # If not already pulled in root output_dir or databases dir
                            root_file = self.output_dir / fname
                            if not local_dest.exists() and not root_file.exists():
                                self.adb.run_cmd(prefix + ["pull", f"{db_dir}/{fname}", str(local_dest)], timeout=45)
                            
                            actual_local = local_dest if local_dest.exists() else (root_file if root_file.exists() else None)
                            fsize_int = int(fsize) if fsize.isdigit() else 0
                            
                            artifacts["databases"].append({
                                "name": fname,
                                "size_formatted": f"{round(fsize_int / (1024*1024), 2)} MB" if fsize_int else fsize,
                                "size_bytes": fsize_int,
                                "remote_path": f"{db_dir}/{fname}",
                                "crypt_type": self._detect_crypt_type(fname),
                                "local_path": str(actual_local) if actual_local else "",
                                "available_offline": bool(actual_local and actual_local.exists())
                            })

        # Also register existing databases if already present in self.output_dir
        for existing in self.output_dir.glob("msgstore*.db.crypt*"):
            if not any(d["name"] == existing.name for d in artifacts["databases"]):
                size_mb = round(existing.stat().st_size / (1024*1024), 2)
                artifacts["databases"].append({
                    "name": existing.name,
                    "size_formatted": f"{size_mb} MB",
                    "size_bytes": existing.stat().st_size,
                    "remote_path": f"/sdcard/Android/media/com.whatsapp/WhatsApp/Databases/{existing.name}",
                    "crypt_type": self._detect_crypt_type(existing.name),
                    "local_path": str(existing),
                    "available_offline": True
                })

        # Sort databases newest first
        artifacts["databases"].sort(key=lambda x: x["name"], reverse=True)

        # 2. Extract Recent WhatsApp Voice Notes
        # Check the recent weeks for Voice Notes
        for base_path in WHATSAPP_BASES:
            vn_base = f"{base_path}/Media/WhatsApp\\ Voice\\ Notes"
            success, out = self.adb.run_cmd(prefix + ["shell", "ls", "-1", vn_base], timeout=10)
            if success and out.strip():
                subfolders = [f.strip() for f in out.strip().splitlines() if f.strip().isdigit()]
                # Check top 5 most recent folders
                subfolders.sort(reverse=True)
                pulled_vn_count = 0
                for s_dir in subfolders[:6]:
                    folder_path = f"{base_path}/Media/WhatsApp\\ Voice\\ Notes/{s_dir}"
                    f_success, f_out = self.adb.run_cmd(prefix + ["shell", "ls", "-la", folder_path], timeout=10)
                    if f_success and f_out:
                        for fline in f_out.strip().splitlines():
                            parts = fline.strip().split(maxsplit=7)
                            if len(parts) >= 8:
                                vn_name = parts[7]
                                vn_size = parts[4]
                                vn_date = f"{parts[5]} {parts[6]}"
                                if vn_name.endswith(".opus") or vn_name.endswith(".m4a") or vn_name.endswith(".aac"):
                                    local_vn = self.output_dir / "voice_notes" / vn_name
                                    if not local_vn.exists() and pulled_vn_count < 15:
                                        self.adb.run_cmd(prefix + ["pull", f"{base_path}/Media/WhatsApp Voice Notes/{s_dir}/{vn_name}", str(local_vn)], timeout=15)
                                        pulled_vn_count += 1
                                    
                                    fsize_num = int(vn_size) if vn_size.isdigit() else 0
                                    artifacts["voice_notes"].append({
                                        "filename": vn_name,
                                        "folder": s_dir,
                                        "date": vn_date,
                                        "size_bytes": fsize_num,
                                        "size_formatted": f"{round(fsize_num / 1024, 1)} KB",
                                        "local_path": str(local_vn) if local_vn.exists() else "",
                                        "available_offline": local_vn.exists()
                                    })

        # Sort voice notes newest first
        artifacts["voice_notes"].sort(key=lambda x: x["filename"], reverse=True)

        # 3. Pull hidden WhatsApp Statuses (.Statuses cache)
        for base_path in WHATSAPP_BASES:
            status_dir = f"{base_path}/Media/.Statuses"
            status_dest = self.output_dir / "statuses"
            status_dest.mkdir(parents=True, exist_ok=True)
            success, out = self.adb.run_cmd(prefix + ["shell", "ls", "-1", status_dir], timeout=10)
            if success and out.strip():
                for sfile in out.strip().splitlines()[:20]:
                    sfile = sfile.strip()
                    if sfile and not sfile.startswith("."):
                        target_path = status_dest / sfile
                        if not target_path.exists():
                            self.adb.run_cmd(prefix + ["pull", f"{status_dir}/{sfile}", str(target_path)], timeout=15)
                        if target_path.exists():
                            artifacts["statuses"].append({
                                "filename": sfile,
                                "local_path": str(target_path),
                                "size_bytes": target_path.stat().st_size
                            })

        # 4. Telegram Forensic Cache & Traces
        telegram_data = {
            "installed": False,
            "cache_folders": [],
            "media_found": 0,
            "status": "No Telegram artifacts detected"
        }
        success, out = self.adb.run_cmd(prefix + ["shell", "ls", "-la", f"{TELEGRAM_BASE}/files/Telegram"], timeout=10)
        if success and out.strip():
            telegram_data["installed"] = True
            telegram_data["status"] = "Active Telegram data directories recovered"
            for t_line in out.strip().splitlines():
                parts = t_line.strip().split(maxsplit=7)
                if len(parts) >= 8:
                    folder_name = parts[7]
                    if folder_name not in [".", ".."]:
                        telegram_data["cache_folders"].append(folder_name)
        artifacts["telegram"] = telegram_data

        # 5. Media summary
        media_types = [
            ("WhatsApp Images", "Images & Photos"),
            ("WhatsApp Audio", "Sent/Received Audio Tracks"),
            ("WhatsApp Video", "Video Clips"),
            ("WhatsApp Documents", "PDFs & Worksheets"),
            ("WhatsApp Voice Notes", "Voice Recordings (PTT)")
        ]
        for base_path in WHATSAPP_BASES:
            for mtype, label in media_types:
                escaped_mtype = mtype.replace(' ', r'\ ')
                mpath = f"{base_path}/Media/{escaped_mtype}"
                success, out = self.adb.run_cmd(prefix + ["shell", "ls", "-1", mpath], timeout=5)
                if success and out.strip():
                    count = len([x for x in out.strip().splitlines() if x.strip() and not x.strip().startswith(".")])
                    artifacts["media_stats"][label] = count

        # Save summary
        summary_path = self.output_dir / "whatsapp_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(artifacts, f, indent=2, ensure_ascii=False)

        return artifacts

    def _detect_crypt_type(self, fname):
        match = re.search(r"crypt(\d+)", fname, re.IGNORECASE)
        if match:
            return f"Crypt{match.group(1)} (End-to-End Encrypted Master Backup)"
        return "Standard Crypt Backup"
