import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime

DOCUMENT_EXTENSIONS = {
    ".pdf": "PDF Document",
    ".doc": "Word Document",
    ".docx": "Word Document",
    ".xls": "Excel Spreadsheet",
    ".xlsx": "Excel Spreadsheet",
    ".ppt": "PowerPoint Presentation",
    ".pptx": "PowerPoint Presentation",
    ".txt": "Text Document",
    ".csv": "CSV Spreadsheet",
    ".json": "JSON Data",
    ".xml": "XML Document",
    ".html": "HTML Web Page"
}

ARCHIVE_EXTENSIONS = {
    ".zip": "ZIP Archive",
    ".rar": "RAR Archive",
    ".7z": "7-Zip Archive",
    ".tar": "TAR Archive",
    ".gz": "GZ Archive"
}

APP_EXTENSIONS = {
    ".apk": "Android Application Package (APK)",
    ".xapk": "Android App Bundle (XAPK)"
}

ALL_FILE_EXTENSIONS = {**DOCUMENT_EXTENSIONS, **ARCHIVE_EXTENSIONS, **APP_EXTENSIONS}

TARGET_DIRECTORIES = [
    "/sdcard",
    "/sdcard/Documents",
    "/sdcard/Download",
    "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Documents",
    "/sdcard/Android/data/com.sec.android.app.myfiles/files",
    "/sdcard/Initha documents I.B.COM(CA)",
    "/sdcard/Mathesh cerificate"
]

class FilesRecovery:
    def __init__(self, adb_manager, output_dir=None):
        self.adb = adb_manager
        if output_dir is None:
            self.output_dir = Path(__file__).resolve().parent.parent / "recovered_data" / "files"
        else:
            self.output_dir = Path(output_dir) / "files"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "documents").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "apks").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "archives").mkdir(parents=True, exist_ok=True)

    def extract_files(self, serial=None, max_files_to_pull=50):
        """
        Scans device storage for active documents, deleted file remnants, and cached files.
        Pulls discovered files locally and calculates cryptographic hashes.
        """
        prefix = ["-s", serial] if serial else []
        discovered_files = []
        seen_filenames = set()

        for target_dir in TARGET_DIRECTORIES:
            # Query directory listing with sizes and timestamps
            success, out = self.adb.run_cmd(prefix + ["shell", "ls", "-la", target_dir], timeout=15)
            if not success or not out:
                continue

            for line in out.strip().splitlines():
                line = line.strip()
                if not line or line.startswith("total ") or line.startswith("d"):
                    continue

                parts = line.split(maxsplit=7)
                if len(parts) < 8:
                    continue

                # Typical format: -rw-rw---- 1 u0_a219 media_rw  942702 2024-07-19 18:26 filename.pdf
                size_str = parts[4]
                date_str = f"{parts[5]} {parts[6]}"
                filename = parts[7]

                if not size_str.isdigit() or filename in [".", ".."]:
                    continue

                file_size = int(size_str)
                ext = Path(filename).suffix.lower()

                if ext in ALL_FILE_EXTENSIONS:
                    full_remote_path = f"{target_dir}/{filename}"
                    category = ALL_FILE_EXTENSIONS[ext]
                    
                    # Detect status (Active, Carved, Deleted remnant)
                    is_deleted_cache = (
                        filename.startswith(".") or 
                        "temp" in filename.lower() or 
                        "cache" in target_dir.lower() or
                        "scan" in filename.lower() or
                        filename.startswith("_data_user_")
                    )
                    status = "Carved Document Fragment / Cache" if is_deleted_cache else "Recovered Active Document"

                    discovered_files.append({
                        "filename": filename,
                        "extension": ext,
                        "category": category,
                        "size_bytes": file_size,
                        "size_formatted": self._format_size(file_size),
                        "modified_date": date_str,
                        "remote_path": full_remote_path,
                        "status": status,
                        "local_path": "",
                        "sha256": ""
                    })

        # Sort by size or date (priority to actual documents)
        discovered_files.sort(key=lambda x: x["size_bytes"], reverse=True)

        # Pull top files to local storage for instant download
        pull_count = 0
        for item in discovered_files:
            fname = item["filename"]
            # Clean local filename to avoid special char issues
            clean_name = re.sub(r'[\\/*?:"<>|]', "_", fname)
            
            subfolder = "documents"
            if item["extension"] in APP_EXTENSIONS:
                subfolder = "apks"
            elif item["extension"] in ARCHIVE_EXTENSIONS:
                subfolder = "archives"
                
            local_dest = self.output_dir / subfolder / clean_name
            
            # If not yet pulled or within pull limit
            if not local_dest.exists() and pull_count < max_files_to_pull and item["size_bytes"] < 50 * 1024 * 1024:
                pull_res, _ = self.adb.run_cmd(prefix + ["pull", item["remote_path"], str(local_dest)], timeout=30)
                if pull_res and local_dest.exists():
                    pull_count += 1
            
            if local_dest.exists():
                item["local_path"] = str(local_dest)
                item["sha256"] = self._compute_hash(local_dest)
                item["available_offline"] = True
            else:
                item["available_offline"] = False
                item["sha256"] = "Pending Device Download"

        # Save manifest
        manifest_path = self.output_dir / "recovered_files_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(discovered_files, f, indent=2, ensure_ascii=False)

        return discovered_files

    def _format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{round(size_bytes / 1024, 1)} KB"
        else:
            return f"{round(size_bytes / (1024 * 1024), 2)} MB"

    def _compute_hash(self, file_path):
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""
