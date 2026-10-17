import os
import sys
import time
import json
import zipfile
import subprocess
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.adb_manager import ADBManager
from core.call_logs_recovery import CallLogRecovery
from core.image_recovery import ImageRecovery
from core.ai_enhancer import AIEnhancer
from core.log_classifier import LogClassifier
from core.sms_recovery import SMSRecovery
from core.contacts_recovery import ContactsRecovery
from core.audio_recovery import AudioRecovery
from core.whatsapp_recovery import WhatsAppRecovery
from core.report_generator import ReportGenerator
from core.files_recovery import FilesRecovery
from core.apps_recovery import AppsRecovery

app = FastAPI(title="Phone Forensic Recovery & AI Suite - Enterprise Edition")

# Paths
OUTPUT_DIR = BASE_DIR / "recovered_data"
IMAGES_DIR = OUTPUT_DIR / "images"
AUDIO_DIR = OUTPUT_DIR / "audio"
SMS_DIR = OUTPUT_DIR / "sms"
CONTACTS_DIR = OUTPUT_DIR / "contacts"
WHATSAPP_DIR = OUTPUT_DIR / "whatsapp"
FILES_DIR = OUTPUT_DIR / "files"
APPS_DIR = OUTPUT_DIR / "apps"
STATIC_DIR = BASE_DIR / "web_app" / "static"

for p in [OUTPUT_DIR, IMAGES_DIR, AUDIO_DIR, SMS_DIR, CONTACTS_DIR, WHATSAPP_DIR, FILES_DIR, APPS_DIR, STATIC_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Mount media directories for browser playback & previews
app.mount("/images_data", StaticFiles(directory=str(IMAGES_DIR)), name="images_data")
app.mount("/audio_data", StaticFiles(directory=str(AUDIO_DIR)), name="audio_data")
app.mount("/files_data", StaticFiles(directory=str(FILES_DIR)), name="files_data")
app.mount("/whatsapp_data", StaticFiles(directory=str(WHATSAPP_DIR)), name="whatsapp_data")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

adb_mgr = ADBManager(base_dir=BASE_DIR)

# Comprehensive in-memory cache
CACHE = {
    "device_info": {},
    "device_advanced": {},
    "raw_logs": [],
    "sms": [],
    "contacts": [],
    "recordings": [],
    "whatsapp": {},
    "chats": {},
    "files": [],
    "apps": {},
    "images": [],
    "enhanced_images": [],
    "last_scanned": None
}

@app.on_event("startup")
def startup_load_existing_evidence():
    """Auto-loads previously recovered phone data and evidence from disk into cache instantly on launch."""
    try:
        import json, csv, datetime
        
        # 1. Load Calls from CSV
        csv_file = OUTPUT_DIR / "report" / "recovered_call_logs.csv"
        if csv_file.exists():
            loaded_calls = []
            with open(csv_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = 0
                    try:
                        dt = datetime.datetime.strptime(row.get("date", ""), "%Y-%m-%d %H:%M:%S")
                        ts = int(dt.timestamp())
                    except Exception:
                        pass
                    row["timestamp_raw"] = ts
                    loaded_calls.append(row)
            CACHE["raw_logs"] = loaded_calls

        # 2. Load Contacts from JSON
        contacts_file = CONTACTS_DIR / "recovered_contacts.json"
        if contacts_file.exists():
            with open(contacts_file, "r", encoding="utf-8") as f:
                CACHE["contacts"] = json.load(f)
        elif CACHE.get("raw_logs"):
            # Synthesize from call logs
            seen = set()
            synth = []
            for c in CACHE["raw_logs"]:
                num = c.get("number")
                if num and num not in seen and num != "Unknown":
                    seen.add(num)
                    synth.append({
                        "name": c.get("name") if c.get("name") != "Unknown" else f"Caller {num}",
                        "number": num,
                        "source": "Call Log History"
                    })
            CACHE["contacts"] = synth

        # 3. Load SMS from JSON
        sms_file = SMS_DIR / "recovered_sms.json"
        if sms_file.exists():
            with open(sms_file, "r", encoding="utf-8") as f:
                CACHE["sms"] = json.load(f)

        # 4. Load Audio Recordings
        aud_rec = AudioRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        catalog = []
        for f in AUDIO_DIR.glob("*.*"):
            if f.suffix.lower() in [".m4a", ".amr", ".mp3", ".wav", ".opus"]:
                catalog.append(aud_rec._parse_audio_metadata(f, str(f)))
        catalog.sort(key=lambda x: x.get("timestamp_raw", 0), reverse=True)
        CACHE["recordings"] = catalog

        # 5. Load Images & AI Enhanced
        imgs = []
        for f in IMAGES_DIR.rglob("*.*"):
            if f.suffix.lower() in [".jpg", ".jpeg", ".png", ".webp"] and "ai_enhanced" not in str(f):
                imgs.append({"path": str(f), "type": "Carved Thumbnail" if "thumbnail" in str(f) else "Active Photo"})
        if imgs:
            CACHE["images"] = imgs

        enhanced = []
        for f in (IMAGES_DIR / "ai_enhanced").glob("*.*"):
            if f.suffix.lower() in [".jpg", ".jpeg", ".png"]:
                enhanced.append({
                    "original_path": str(IMAGES_DIR / "carved_thumbnails" / f.name),
                    "enhanced_path": str(f),
                    "original_dims": "Thumbnail",
                    "enhanced_dims": "AI Super-Resolved (HD)"
                })
        if enhanced:
            CACHE["enhanced_images"] = enhanced

        # 6. Load Recovered Files & Documents
        files_manifest = FILES_DIR / "recovered_files_manifest.json"
        if files_manifest.exists():
            with open(files_manifest, "r", encoding="utf-8") as f:
                CACHE["files"] = json.load(f)

        # 7. Load Apps Inventory & Residue
        apps_manifest = APPS_DIR / "apps_inventory.json"
        if apps_manifest.exists():
            with open(apps_manifest, "r", encoding="utf-8") as f:
                CACHE["apps"] = json.load(f)

        # 8. Load WhatsApp & App Chats
        wa_summary = WHATSAPP_DIR / "whatsapp_summary.json"
        if wa_summary.exists():
            with open(wa_summary, "r", encoding="utf-8") as f:
                wa_data = json.load(f)
                CACHE["whatsapp"] = wa_data
                CACHE["chats"] = wa_data

    except Exception as e:
        print(f"Startup preloading info: {e}")



class RecoveryRequest(BaseModel):
    months: int = 1
    carve_images: bool = True
    ai_enhance: bool = True
    extract_sms: bool = True
    extract_contacts: bool = True
    extract_audio: bool = True
    extract_whatsapp: bool = True
    extract_files: bool = True
    extract_apps: bool = True
    extract_chats: bool = True

@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/device/status")
def get_device_status():
    """
    Checks ADB and Windows device manager to report real connection state.
    """
    adb_mgr.ensure_adb()
    devices = adb_mgr.get_connected_devices()

    if devices:
        dev = devices[0]
        status = dev["status"]
        info = adb_mgr.get_device_info(serial=dev["serial"]) if status == "device" else {}
        return {
            "connected": (status == "device"),
            "status": status,
            "serial": dev["serial"],
            "device_info": info,
            "message": "Phone is successfully connected and authorized!" if status == "device" else "Phone is detected but unauthorized. Unlock phone screen and tap 'ALLOW'."
        }

    # If no ADB device, inspect Windows hardware for Code 43 or USB connection
    try:
        cmd = 'powershell "Get-PnpDevice -PresentOnly | Where-Object { $_.Problem -eq 43 } | Select-Object -ExpandProperty FriendlyName"'
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        out = proc.stdout.strip()
        if "Unknown USB Device" in out or "Descriptor" in out:
            return {
                "connected": False,
                "status": "code_43",
                "message": "USB Hardware Error (Code 43 - Device Descriptor Request Failed). Please try a different USB cable or another USB port on your PC."
            }
    except Exception:
        pass

    return {
        "connected": False,
        "status": "disconnected",
        "message": "No phone detected over USB. Plug in your phone and enable USB Debugging."
    }

@app.get("/api/device/details")
def get_advanced_device_details():
    """Returns deep hardware forensic details: battery, storage, carrier, root state."""
    devices = adb_mgr.get_connected_devices()
    if not devices or devices[0]["status"] != "device":
        # If disconnected, return cached or fallback
        if CACHE.get("device_advanced"):
            return {"connected": False, "details": CACHE["device_advanced"]}
        return {
            "connected": False,
            "details": {
                "model": "Not Connected",
                "manufacturer": "N/A",
                "android_version": "N/A",
                "battery_level": "N/A",
                "battery_status": "N/A",
                "storage_internal": "N/A",
                "carrier": "N/A",
                "root_status": "Unknown",
                "resolution": "N/A"
            }
        }
    serial = devices[0]["serial"]
    adv_info = adb_mgr.get_advanced_device_info(serial=serial)
    CACHE["device_advanced"] = adv_info
    return {"connected": True, "details": adv_info}

@app.post("/api/recover")
def run_recovery(req: RecoveryRequest):
    """
    Runs multi-vector forensic extraction pipeline across Calls, Images, AI Enhancements,
    SMS, Contacts, Audio recordings, and WhatsApp artifacts.
    """
    devices = adb_mgr.get_connected_devices()
    serial = devices[0]["serial"] if (devices and devices[0]["status"] == "device") else None

    # Retrieve hardware details if device is connected
    if serial:
        dev_info = adb_mgr.get_device_info(serial=serial)
        CACHE["device_info"] = dev_info
        CACHE["device_advanced"] = adb_mgr.get_advanced_device_info(serial=serial)
    else:
        dev_info = CACHE.get("device_info", {})

    # 1. Recover Call Logs
    call_rec = CallLogRecovery(adb_mgr, serial=serial)
    raw_calls = call_rec.recover_all()
    CACHE["raw_logs"] = raw_calls

    # 2. Extract Contacts Book & Cross-Reference
    contacts = []
    if req.extract_contacts:
        contacts_rec = ContactsRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        contacts = contacts_rec.extract_contacts(serial=serial)
        CACHE["contacts"] = contacts
        if contacts and raw_calls:
            # Auto-enrich unknown caller names using contacts phonebook
            raw_calls = contacts_rec.enrich_logs_with_contacts(raw_calls, contacts)
            CACHE["raw_logs"] = raw_calls

    # 3. Extract & Classify SMS Messages
    sms_messages = []
    if req.extract_sms:
        sms_rec = SMSRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        sms_messages = sms_rec.extract_sms(serial=serial)
        if contacts and sms_messages:
            sms_messages = contacts_rec.enrich_logs_with_contacts(sms_messages, contacts)
        CACHE["sms"] = sms_messages

    # 4. Extract Call Recordings & Audio Memos
    recordings = []
    if req.extract_audio:
        audio_rec = AudioRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        recordings = audio_rec.extract_recordings(serial=serial)
        CACHE["recordings"] = recordings

    # 5. Extract WhatsApp Forensic Artifacts & Chats
    whatsapp_artifacts = {}
    if req.extract_whatsapp or req.extract_chats:
        wa_rec = WhatsAppRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        whatsapp_artifacts = wa_rec.extract_whatsapp_artifacts(serial=serial)
        CACHE["whatsapp"] = whatsapp_artifacts
        CACHE["chats"] = whatsapp_artifacts

    # 6. Extract Recovered Documents & Carved Files
    recovered_files = []
    if req.extract_files:
        files_rec = FilesRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        recovered_files = files_rec.extract_files(serial=serial)
        CACHE["files"] = recovered_files

    # 7. Audit Installed Apps & Deleted App Residue
    apps_data = {}
    if req.extract_apps:
        apps_rec = AppsRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        apps_data = apps_rec.extract_apps_inventory(serial=serial)
        CACHE["apps"] = apps_data

    # 8. Recover Images & Carved Thumbnails
    all_imgs = []
    enhanced = []
    if req.carve_images:
        img_rec = ImageRecovery(adb_mgr, serial=serial, output_dir=IMAGES_DIR)
        active_imgs = img_rec.pull_active_media(max_files=30)
        carved_imgs = img_rec.carve_thumbnail_caches()
        all_imgs = active_imgs + carved_imgs

        # AI Enhancement
        if req.ai_enhance and carved_imgs:
            enhancer = AIEnhancer(output_dir=IMAGES_DIR / "ai_enhanced")
            enhanced = enhancer.batch_enhance(carved_imgs[:25])

    CACHE["images"] = all_imgs
    CACHE["enhanced_images"] = enhanced
    CACHE["last_scanned"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Filter and classify calls
    filtered_logs = LogClassifier.filter_by_months(raw_calls, months=req.months)
    classified = LogClassifier.classify_logs(filtered_logs)

    return {
        "success": True,
        "months_filtered": req.months,
        "total_calls": len(raw_calls),
        "total_sms": len(sms_messages),
        "total_contacts": len(contacts),
        "total_recordings": len(recordings),
        "total_files": len(recovered_files) or len(CACHE.get("files", [])),
        "total_apps_installed": apps_data.get("installed_apps_count", 0) or CACHE.get("apps", {}).get("installed_apps_count", 0),
        "total_apps_residue": apps_data.get("uninstalled_residue_count", 0) or CACHE.get("apps", {}).get("uninstalled_residue_count", 0),
        "total_images": len(all_imgs),
        "total_enhanced": len(enhanced),
        "device_info": dev_info,
        "analytics": classified["analytics"]
    }

@app.get("/api/logs")
def get_logs(
    months: int = Query(1, description="Months timeframe (default 1)"),
    start_date: Optional[str] = Query(None, description="Start date filter YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date filter YYYY-MM-DD"),
    category: Optional[str] = Query(None)
):
    """
    Returns filtered and classified call logs.
    Supports preset months (1, 3, 6, 12, etc.) or custom date ranges.
    """
    raw_logs = CACHE["raw_logs"]
    if not raw_logs:
        return {"logs": [], "analytics": {}, "months": months}

    for idx, log in enumerate(raw_logs):
        log["raw_index"] = idx

    # Filter by date range or months
    if start_date or end_date:
        filtered = LogClassifier.filter_by_custom_range(raw_logs, start_date, end_date)
    else:
        filtered = LogClassifier.filter_by_months(raw_logs, months=months)

    classified_result = LogClassifier.classify_logs(filtered)

    # Calculate all-time carved deleted traces for analytics badge
    all_classified = LogClassifier.classify_logs(raw_logs)["classified_logs"]
    all_deleted = [l for l in all_classified if "Deleted / Forensic Trace" in l.get("tags", [])]
    classified_result["analytics"]["deleted_recovered"] = len(all_deleted)
    classified_result["analytics"]["categories"]["Deleted / Forensic Trace"] = len(all_deleted)

    if category == "Deleted / Forensic Trace":
        return {
            "months": months,
            "total_count": len(all_deleted),
            "analytics": classified_result["analytics"],
            "logs": all_deleted
        }

    logs = classified_result["classified_logs"]
    if category and category != "all":
        logs = [l for l in logs if category in l.get("tags", [])]

    return {
        "months": months,
        "total_count": len(logs),
        "analytics": classified_result["analytics"],
        "logs": logs
    }


@app.get("/api/sms")
def get_sms(category: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    """Returns SMS messages classified into Banking, OTP, Personal, Spam with search support."""
    messages = CACHE["sms"]
    if not messages:
        # Check if saved JSON exists
        saved_file = SMS_DIR / "recovered_sms.json"
        if saved_file.exists():
            import json
            try:
                with open(saved_file, "r", encoding="utf-8") as f:
                    messages = json.load(f)
                    CACHE["sms"] = messages
            except Exception:
                pass

    filtered = messages
    if category and category != "all":
        filtered = [m for m in filtered if m.get("category") == category]

    if search:
        s = search.lower()
        filtered = [m for m in filtered if s in (m.get("address", "") + m.get("body", "") + m.get("name", "")).lower()]

    categories_count = {}
    for m in messages:
        c = m.get("category", "General")
        categories_count[c] = categories_count.get(c, 0) + 1

    return {
        "total": len(messages),
        "filtered_count": len(filtered),
        "categories": categories_count,
        "messages": filtered
    }

@app.get("/api/contacts")
def get_contacts(search: Optional[str] = Query(None)):
    """Returns address book contacts with search."""
    contacts = CACHE.get("contacts", [])
    if not contacts and CACHE.get("raw_logs"):
        seen_numbers = set()
        for call in CACHE["raw_logs"]:
            num = call.get("number", "")
            name = call.get("name", "Unknown")
            if num and num not in seen_numbers and num != "Unknown":
                seen_numbers.add(num)
                contacts.append({
                    "name": name if name != "Unknown" else f"Caller {num}",
                    "number": num,
                    "source": "Call Log History"
                })
        CACHE["contacts"] = contacts

    filtered = contacts
    if search:
        s = search.lower()
        filtered = [c for c in filtered if s in (c.get("name", "") + c.get("number", "")).lower()]

    return {
        "total": len(contacts),
        "filtered_count": len(filtered),
        "contacts": filtered
    }

@app.get("/api/contacts/export/vcf")
def download_vcf():
    """Allows downloading all recovered contacts as a standard vCard .vcf file."""
    vcf_path = CONTACTS_DIR / "contacts_export.vcf"
    contacts = CACHE.get("contacts", [])
    if not contacts and CACHE.get("raw_logs"):
        seen_numbers = set()
        for call in CACHE["raw_logs"]:
            num = call.get("number", "")
            name = call.get("name", "Unknown")
            if num and num not in seen_numbers and num != "Unknown":
                seen_numbers.add(num)
                contacts.append({
                    "name": name if name != "Unknown" else f"Caller {num}",
                    "number": num,
                    "source": "Call Log History"
                })
        CACHE["contacts"] = contacts

    if contacts:
        rec = ContactsRecovery(adb_mgr, output_dir=OUTPUT_DIR)
        rec.export_to_vcf(contacts, vcf_path)
        return FileResponse(vcf_path, media_type="text/vcard", filename="Recovered_Contacts.vcf")
    raise HTTPException(status_code=404, detail="No contacts available to export.")


@app.get("/api/audio")
def get_audio_recordings():
    """Returns list of call recordings and audio memos with playable URLs."""
    recordings = CACHE["recordings"]
    if not recordings:
        saved_file = AUDIO_DIR / "recordings_catalog.json"
        if saved_file.exists():
            import json
            try:
                with open(saved_file, "r", encoding="utf-8") as f:
                    recordings = json.load(f)
                    CACHE["recordings"] = recordings
            except Exception:
                pass
        else:
            # Scan local audio folder
            rec = AudioRecovery(adb_mgr, output_dir=OUTPUT_DIR)
            recordings = rec.extract_recordings(serial=None)
            CACHE["recordings"] = recordings

    return {
        "total": len(recordings),
        "recordings": recordings
    }

@app.get("/api/whatsapp")
def get_whatsapp_artifacts():
    """Returns WhatsApp databases and extracted artifact details."""
    wa = CACHE["whatsapp"]
    if not wa:
        saved_file = WHATSAPP_DIR / "whatsapp_summary.json"
        if saved_file.exists():
            import json
            try:
                with open(saved_file, "r", encoding="utf-8") as f:
                    wa = json.load(f)
                    CACHE["whatsapp"] = wa
            except Exception:
                pass
    return wa or {"databases": [], "media_stats": {}, "statuses": []}

@app.get("/api/images")
def get_images():
    """Returns active and carved images formatted for web preview."""
    base_url = "/images_data/"
    formatted_images = []
    for img in CACHE["images"]:
        p = Path(img.get("path", ""))
        try:
            rel = p.relative_to(IMAGES_DIR).as_posix()
            formatted_images.append({
                "url": f"{base_url}{rel}",
                "filename": p.name,
                "type": img.get("type", "Media")
            })
        except Exception:
            continue

    formatted_enhanced = []
    for enh in CACHE["enhanced_images"]:
        orig_p = Path(enh.get("original_path", ""))
        enh_p = Path(enh.get("enhanced_path", ""))
        try:
            orig_rel = orig_p.relative_to(IMAGES_DIR).as_posix()
            enh_rel = enh_p.relative_to(IMAGES_DIR).as_posix()
            formatted_enhanced.append({
                "original_url": f"{base_url}{orig_rel}",
                "enhanced_url": f"{base_url}{enh_rel}",
                "original_dims": enh.get("original_dims", ""),
                "enhanced_dims": enh.get("enhanced_dims", ""),
                "filename": enh_p.name
            })
        except Exception:
            continue

    return {
        "images": formatted_images,
        "enhanced": formatted_enhanced
    }

@app.get("/api/image/download")
def download_individual_image(filename: str = Query(..., description="Image filename")):
    """Serves an individual image with Content-Disposition attachment for immediate download."""
    target_path = None
    enh_p = IMAGES_DIR / "ai_enhanced" / filename
    if enh_p.exists():
        target_path = enh_p
    else:
        carv_p = IMAGES_DIR / "carved_thumbnails" / filename
        if carv_p.exists():
            target_path = carv_p
        else:
            matches = list(IMAGES_DIR.glob(f"**/{filename}"))
            if matches:
                target_path = matches[0]

    if not target_path or not target_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found.")

    return FileResponse(
        target_path,
        media_type="image/jpeg",
        filename=f"Recovered_{filename}"
    )

@app.get("/api/audio/download")
def download_individual_audio(filename: str = Query(..., description="Audio recording filename")):
    """Serves individual call recording for direct browser download."""
    audio_path = AUDIO_DIR / filename
    if not audio_path.exists():
        matches = list(AUDIO_DIR.glob(f"**/{filename}"))
        if matches:
            audio_path = matches[0]
        else:
            raise HTTPException(status_code=404, detail="Audio file not found.")

    return FileResponse(
        audio_path,
        media_type="audio/mp4",
        filename=filename
    )

@app.get("/api/record/export")
def export_individual_call_record(index: int = Query(..., description="Call record index")):
    """Exports a single call record as an individual forensic evidence certificate."""
    logs = CACHE.get("raw_logs", [])
    if index < 0 or index >= len(logs):
        raise HTTPException(status_code=404, detail="Record index out of range.")

    rec = logs[index]
    import hashlib
    record_str = f"{rec.get('number')}_{rec.get('date')}_{rec.get('duration')}_{rec.get('status')}"
    sha256 = hashlib.sha256(record_str.encode()).hexdigest().upper()

    certificate = {
        "forensic_case_id": "FOR-2026-EVID-8819",
        "evidence_record_index": index,
        "caller_number": rec.get("number"),
        "contact_name": rec.get("name"),
        "timestamp": rec.get("date"),
        "duration": rec.get("duration"),
        "call_type": rec.get("type"),
        "forensic_status": rec.get("status"),
        "sha256_hash_verification": sha256,
        "chain_of_custody": "Extracted via Android ADB Forensic Subsystem (Direct/Buffer/Backup Carving)",
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    }
    return JSONResponse(
        content=certificate,
        headers={"Content-Disposition": f'attachment; filename="Call_Evidence_{rec.get("number", "record")}_{index}.json"'}
    )

@app.get("/api/files")
def get_recovered_files(category: Optional[str] = Query(None), search: Optional[str] = Query(None)):
    """Returns discovered & carved files, documents, APKs, and archives."""
    files = CACHE.get("files", [])
    if not files:
        manifest_file = FILES_DIR / "recovered_files_manifest.json"
        if manifest_file.exists():
            with open(manifest_file, "r", encoding="utf-8") as f:
                files = json.load(f)
                CACHE["files"] = files

    categories_count = {}
    for f in files:
        cat = f.get("category", "Other")
        categories_count[cat] = categories_count.get(cat, 0) + 1

    filtered = files
    if category and category.lower() != "all":
        filtered = [f for f in filtered if category.lower() in f.get("category", "").lower()]

    if search:
        s = search.lower()
        filtered = [f for f in filtered if s in f.get("filename", "").lower() or s in f.get("category", "").lower()]

    return {
        "total": len(files),
        "filtered_count": len(filtered),
        "categories": categories_count,
        "files": filtered[:250]
    }

@app.get("/api/files/download")
def download_individual_file(filename: str = Query(..., description="File to download")):
    """Downloads an individual recovered file or document."""
    target = None
    matches = list(FILES_DIR.glob(f"**/{filename}"))
    if matches:
        target = matches[0]
    else:
        matches2 = list(OUTPUT_DIR.glob(f"**/{filename}"))
        if matches2:
            target = matches2[0]

    if not target or not target.exists():
        raise HTTPException(status_code=404, detail="Requested file not found in local evidence vault.")

    ext = target.suffix.lower()
    media_type = "application/octet-stream"
    if ext == ".pdf":
        media_type = "application/pdf"
    elif ext in [".docx", ".doc"]:
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext in [".xlsx", ".xls"]:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == ".apk":
        media_type = "application/vnd.android.package-archive"
    elif ext == ".zip":
        media_type = "application/zip"
    elif ext == ".txt":
        media_type = "text/plain"

    return FileResponse(
        target,
        media_type=media_type,
        filename=target.name
    )

@app.get("/api/apps")
def get_apps_inventory():
    """Returns installed 3rd-party apps and detected uninstalled/deleted app residue."""
    apps_data = CACHE.get("apps", {})
    if not apps_data or not apps_data.get("installed_apps"):
        manifest_file = APPS_DIR / "apps_inventory.json"
        if manifest_file.exists():
            with open(manifest_file, "r", encoding="utf-8") as f:
                apps_data = json.load(f)
                CACHE["apps"] = apps_data

    return apps_data or {
        "installed_apps_count": 0,
        "uninstalled_residue_count": 0,
        "installed_apps": [],
        "uninstalled_residue": []
    }

@app.get("/api/chats")
def get_chat_forensics():
    """Returns WhatsApp encrypted databases, voice notes, media stats, and Telegram traces."""
    chats = CACHE.get("chats", {})
    if not chats or not chats.get("voice_notes"):
        summary_file = WHATSAPP_DIR / "whatsapp_summary.json"
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                chats = json.load(f)
                CACHE["chats"] = chats
                CACHE["whatsapp"] = chats

    voice_notes = chats.get("voice_notes", [])
    for vn in voice_notes:
        vn["playback_url"] = f"/whatsapp_data/voice_notes/{vn.get('filename')}"
        vn["download_url"] = f"/api/chats/download-voicenote?filename={vn.get('filename')}"

    databases = chats.get("databases", [])
    for db in databases:
        db["download_url"] = f"/api/chats/download-db?name={db.get('name')}"

    return chats or {
        "databases": [],
        "voice_notes": [],
        "statuses": [],
        "telegram": {},
        "media_stats": {}
    }

@app.get("/api/chats/download-db")
def download_whatsapp_database(name: str = Query(..., description="Database filename")):
    """Downloads an encrypted WhatsApp database backup file."""
    db_path = WHATSAPP_DIR / "databases" / name
    if not db_path.exists():
        db_path = WHATSAPP_DIR / name

    if not db_path.exists():
        matches = list(WHATSAPP_DIR.glob(f"**/{name}"))
        if matches:
            db_path = matches[0]

    if not db_path or not db_path.exists():
        raise HTTPException(status_code=404, detail="Database backup file not found.")

    return FileResponse(
        db_path,
        media_type="application/octet-stream",
        filename=name
    )

@app.get("/api/chats/download-voicenote")
def download_whatsapp_voicenote(filename: str = Query(..., description="Voice note filename")):
    """Downloads an individual WhatsApp voice note audio file."""
    vn_path = WHATSAPP_DIR / "voice_notes" / filename
    if not vn_path.exists():
        matches = list(WHATSAPP_DIR.glob(f"**/{filename}"))
        if matches:
            vn_path = matches[0]
        else:
            raise HTTPException(status_code=404, detail="Voice note file not found.")

    return FileResponse(
        vn_path,
        media_type="audio/ogg",
        filename=filename
    )

@app.delete("/api/files/delete")
def delete_file(filename: str = Query(..., description="File to delete")):
    """Deletes an individual recovered document/file from evidence vault."""
    deleted = False
    for sub in ["documents", "apks", "archives", ""]:
        p = FILES_DIR / sub / filename if sub else FILES_DIR / filename
        if p.exists() and p.is_file():
            try:
                p.unlink()
                deleted = True
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")

    # Remove from CACHE and manifest
    CACHE["files"] = [f for f in CACHE.get("files", []) if f.get("filename") != filename]
    manifest_file = FILES_DIR / "recovered_files_manifest.json"
    if manifest_file.exists():
        try:
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(CACHE["files"], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return {"success": True, "message": f"File '{filename}' successfully deleted.", "total_remaining": len(CACHE["files"])}

@app.delete("/api/audio/delete")
def delete_audio(filename: str = Query(..., description="Audio file to delete")):
    """Deletes an individual call recording from evidence vault."""
    p = AUDIO_DIR / filename
    if p.exists() and p.is_file():
        p.unlink()
    CACHE["recordings"] = [r for r in CACHE.get("recordings", []) if r.get("local_file") != filename and r.get("filename") != filename]
    return {"success": True, "message": f"Recording '{filename}' deleted.", "total_remaining": len(CACHE["recordings"])}

@app.delete("/api/images/delete")
def delete_image(filename: str = Query(..., description="Image file to delete")):
    """Deletes an individual image from thumbnails or enhanced cache."""
    for sub in ["ai_enhanced", "carved_thumbnails", ""]:
        p = IMAGES_DIR / sub / filename if sub else IMAGES_DIR / filename
        if p.exists() and p.is_file():
            p.unlink()
    CACHE["images"] = [img for img in CACHE.get("images", []) if Path(img.get("path", "")).name != filename]
    CACHE["enhanced_images"] = [e for e in CACHE.get("enhanced_images", []) if Path(e.get("enhanced_path", "")).name != filename]
    return {"success": True, "message": f"Image '{filename}' deleted."}

@app.delete("/api/logs/delete")
def delete_call_log(index: int = Query(..., description="Call record index")):
    """Deletes a call log entry from evidence memory and reports."""
    logs = CACHE.get("raw_logs", [])
    if 0 <= index < len(logs):
        removed = logs.pop(index)
        CACHE["raw_logs"] = logs
        return {"success": True, "message": f"Record for {removed.get('number')} removed.", "total_remaining": len(logs)}
    raise HTTPException(status_code=404, detail="Call record index out of range.")

@app.delete("/api/chats/delete")
def delete_chat_artifact(name: str = Query(..., description="Chat artifact or DB name")):
    """Deletes a chat database or voice note."""
    for sub in ["databases", "voice_notes", "statuses", ""]:
        p = WHATSAPP_DIR / sub / name if sub else WHATSAPP_DIR / name
        if p.exists() and p.is_file():
            p.unlink()
    
    # Update cache
    if CACHE.get("chats"):
        CACHE["chats"]["databases"] = [d for d in CACHE["chats"].get("databases", []) if d.get("name") != name]
        CACHE["chats"]["voice_notes"] = [v for v in CACHE["chats"].get("voice_notes", []) if v.get("filename") != name]
    return {"success": True, "message": f"Artifact '{name}' deleted."}

class BatchDownloadRequest(BaseModel):
    filenames: list[str]

@app.post("/api/images/download-batch")
def download_batch_images(req: BatchDownloadRequest):
    """Zips selected images into a custom package for batch download."""
    if not req.filenames:
        raise HTTPException(status_code=400, detail="No images specified.")

    batch_zip = OUTPUT_DIR / "Selected_Recovered_Images.zip"
    with zipfile.ZipFile(batch_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for fname in req.filenames[:150]:
            matches = list(IMAGES_DIR.glob(f"**/{fname}"))
            if matches:
                z.write(matches[0], arcname=fname)

    return FileResponse(batch_zip, media_type="application/zip", filename="Selected_Recovered_Images.zip")

@app.get("/api/export/bundle")
def export_complete_forensic_bundle():
    """Creates a comprehensive ZIP package with all recovered evidence."""
    zip_path = OUTPUT_DIR / "Forensic_Recovery_Master_Bundle.zip"
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. Add Call logs CSV
        csv_file = OUTPUT_DIR / "report" / "recovered_call_logs.csv"
        if csv_file.exists():
            z.write(csv_file, arcname="Call_Logs/recovered_call_logs.csv")

        # 2. Add Contacts VCF
        vcf_file = CONTACTS_DIR / "contacts_export.vcf"
        if vcf_file.exists():
            z.write(vcf_file, arcname="Contacts/Recovered_Contacts.vcf")

        # 3. Add SMS JSON
        sms_file = SMS_DIR / "recovered_sms.json"
        if sms_file.exists():
            z.write(sms_file, arcname="SMS/recovered_sms.json")

        # 4. Add Audio Recordings
        for a in AUDIO_DIR.glob("*.*"):
            if a.suffix.lower() in [".m4a", ".amr", ".mp3", ".wav", ".opus"]:
                z.write(a, arcname=f"Audio_Recordings/{a.name}")

        # 5. Add AI Enhanced Images
        for img in (IMAGES_DIR / "ai_enhanced").glob("*.jpg"):
            z.write(img, arcname=f"Images/AI_Enhanced/{img.name}")

        # 6. Add Recovered Documents
        for doc in (FILES_DIR / "documents").glob("*.*"):
            if doc.stat().st_size < 30 * 1024 * 1024:
                z.write(doc, arcname=f"Documents/{doc.name}")

        # 7. Add Apps Inventory JSON
        apps_json = APPS_DIR / "apps_inventory.json"
        if apps_json.exists():
            z.write(apps_json, arcname="Apps_Forensics/apps_inventory.json")

        # 8. Add WhatsApp Databases & Voice Notes
        wa_sum = WHATSAPP_DIR / "whatsapp_summary.json"
        if wa_sum.exists():
            z.write(wa_sum, arcname="Chats/whatsapp_summary.json")

        for vn in (WHATSAPP_DIR / "voice_notes").glob("*.*"):
            z.write(vn, arcname=f"Chats/WhatsApp_Voice_Notes/{vn.name}")

        # 9. Add HTML Report
        html_report = OUTPUT_DIR / "report" / "index.html"
        if html_report.exists():
            z.write(html_report, arcname="Case_Report.html")

    return FileResponse(zip_path, media_type="application/zip", filename="Forensic_Recovery_Master_Bundle.zip")

@app.post("/api/load-sample")
def load_sample_dataset():
    """Loads a full rich sample forensic dataset for demo testing."""
    now = time.time()
    day = 86400

    sample_calls = [
        {"number": "+91 98401 23456", "name": "Kavitha (Office)", "timestamp_raw": now - (2 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 2 * day)), "duration_sec": 740, "duration": "12m 20s", "type": "Incoming", "status": "Active Record"},
        {"number": "+91 98401 23456", "name": "Kavitha (Office)", "timestamp_raw": now - (4 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 4 * day)), "duration_sec": 310, "duration": "5m 10s", "type": "Outgoing", "status": "Active Record"},
        {"number": "+91 80562 99881", "name": "Unknown", "timestamp_raw": now - (5 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 5 * day)), "duration_sec": 0, "duration": "0s", "type": "Missed", "status": "Active Record"},
        {"number": "+91 94440 11223", "name": "Deleted Dial Fragment", "timestamp_raw": now - (15 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 15 * day)), "duration_sec": 0, "duration": "N/A", "type": "Missed / Ended", "status": "Recovered from Telecom Buffer (Deleted/Transient)"},
        {"number": "+91 73580 44556", "name": "SQLite Free-List Record", "timestamp_raw": now - (20 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 20 * day)), "duration_sec": 0, "duration": "N/A", "type": "Carved SQLite Fragment", "status": "Carved from Database Unallocated Space"},
        {"number": "+91 98840 55667", "name": "Muthu Brother", "timestamp_raw": now - (40 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 40 * day)), "duration_sec": 890, "duration": "14m 50s", "type": "Incoming", "status": "Active Record"},
        {"number": "+91 99620 77889", "name": "Travel Agency", "timestamp_raw": now - (120 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 120 * day)), "duration_sec": 120, "duration": "2m 0s", "type": "Outgoing", "status": "Active Record"},
        {"number": "+91 97910 88990", "name": "College Friend", "timestamp_raw": now - (180 * day), "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 180 * day)), "duration_sec": 1200, "duration": "20m 0s", "type": "Incoming", "status": "Active Record"}
    ]

    sample_sms = [
        {"id": "1", "address": "HDFCBK", "name": "HDFC Bank", "body": "Your A/C XX4921 has been debited with INR 2,450.00 on 16-OCT-26 via UPI. Ref 429104.", "date": "2026-10-16 19:42:10", "type": "Inbox", "category": "Bank & Financial"},
        {"id": "2", "address": "VK-GOOGLE", "name": "Google", "body": "G-582910 is your Google verification code. Do not share this OTP with anyone.", "date": "2026-10-16 18:15:02", "type": "Inbox", "category": "OTP / Verification"},
        {"id": "3", "address": "+919840123456", "name": "Kavitha", "body": "Hey, I sent you the project document over email. Check when you are free.", "date": "2026-10-16 15:30:45", "type": "Inbox", "category": "Personal"},
        {"id": "4", "address": "DM-SWIGGY", "name": "Swiggy", "body": "Craving biryani? Get flat 50% discount up to Rs.100 on your next order! Use code FEAST.", "date": "2026-10-16 13:10:00", "type": "Inbox", "category": "Spam / Promo"}
    ]

    sample_contacts = [
        {"name": "Appa", "number": "+918089117816", "normalized_number": "8089117816", "source": "SIM Card"},
        {"name": "Vinoth", "number": "+918220185712", "normalized_number": "8220185712", "source": "Google Account"},
        {"name": "Mano", "number": "+917538868096", "normalized_number": "7538868096", "source": "Device Phonebook"},
        {"name": "Saranya Athai", "number": "+919566399523", "normalized_number": "9566399523", "source": "Device Phonebook"},
        {"name": "Latha", "number": "+917339043048", "normalized_number": "7339043048", "source": "WhatsApp Cache"}
    ]

    CACHE["raw_logs"] = sample_calls
    CACHE["sms"] = sample_sms
    CACHE["contacts"] = sample_contacts
    CACHE["device_info"] = {"manufacturer": "Samsung", "model": "Galaxy S23 Ultra (Demo)", "android_version": "14", "sdk_version": "34"}
    CACHE["device_advanced"] = {
        "model": "Galaxy S23 Ultra", "manufacturer": "Samsung", "android_version": "14", "battery_level": "85%",
        "battery_status": "Normal", "storage_internal": "Used 42GB of 256GB (16% full)", "carrier": "Jio 5G", "root_status": "Standard (Unrooted)", "resolution": "1440x3088"
    }

    classified = LogClassifier.classify_logs(LogClassifier.filter_by_months(sample_calls, months=1))
    return {"success": True, "message": "Enterprise sample dataset loaded!", "analytics": classified["analytics"]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
