import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Curated lookup of popular Android packages to user-friendly titles and categories
KNOWN_APP_CATALOG = {
    # Social & Messaging
    "com.whatsapp": {"name": "WhatsApp Messenger", "category": "Social & Messaging", "risk": "High Forensic Value"},
    "org.telegram.messenger": {"name": "Telegram Messenger", "category": "Social & Messaging", "risk": "High Forensic Value"},
    "com.instagram.android": {"name": "Instagram", "category": "Social & Media", "risk": "Forensic Footprint"},
    "com.snapchat.android": {"name": "Snapchat", "category": "Social & Media", "risk": "High Ephemeral Forensic Value"},
    "com.discord": {"name": "Discord", "category": "Social & Messaging", "risk": "Chat Footprint"},
    "in.mohalla.sharechat": {"name": "ShareChat", "category": "Social Media", "risk": "Standard"},
    "com.linkedin.android": {"name": "LinkedIn", "category": "Professional Social", "risk": "Standard"},
    
    # Financial & Banking
    "com.phonepe.app": {"name": "PhonePe UPI & Payments", "category": "Finance & Banking", "risk": "High Forensic Value (Transactions)"},
    "com.paypal.android.p2pmobile": {"name": "PayPal Mobile", "category": "Finance & Banking", "risk": "High Forensic Value"},
    "com.iexceed.appzillon.ippbMB": {"name": "IPPB Mobile Banking (India Post)", "category": "Finance & Banking", "risk": "High Forensic Value"},
    "com.digilocker.android": {"name": "DigiLocker (Govt Credentials)", "category": "Identity & Government", "risk": "Critical Forensic Value"},
    "com.tneb.tangedco": {"name": "TANGEDCO Electricity Payment", "category": "Finance & Utilities", "risk": "Utility Record"},
    
    # AI & Assistants
    "com.openai.chatgpt": {"name": "ChatGPT AI", "category": "Artificial Intelligence", "risk": "AI Prompt History"},
    "com.anthropic.claude": {"name": "Claude AI", "category": "Artificial Intelligence", "risk": "AI Prompt History"},
    "ai.perplexity.app.android": {"name": "Perplexity AI", "category": "Artificial Intelligence", "risk": "Search Traces"},
    "ai.x.grok": {"name": "xAI Grok", "category": "Artificial Intelligence", "risk": "AI Traces"},
    "ai.mainfunc.genspark": {"name": "GenSpark AI", "category": "Artificial Intelligence", "risk": "AI Traces"},
    
    # Utilities & Tools
    "com.truecaller": {"name": "Truecaller Caller ID", "category": "Communication Tools", "risk": "Call/SMS Lookup Traces"},
    "com.google.android.apps.authenticator2": {"name": "Google Authenticator", "category": "Security & 2FA", "risk": "Security Credential Token"},
    "com.authenticator.app.starnest": {"name": "2FA Authenticator", "category": "Security & 2FA", "risk": "Security Credential Token"},
    "com.adobe.reader": {"name": "Adobe Acrobat Reader", "category": "Productivity & Documents", "risk": "Document History"},
    "com.adobe.scan.android": {"name": "Adobe Scan PDF Scanner", "category": "Productivity & Documents", "risk": "Scanned Document Residue"},
    "com.microsoft.office.word": {"name": "Microsoft Word", "category": "Productivity & Documents", "risk": "Document Footprint"},
    "com.microsoft.office.excel": {"name": "Microsoft Excel", "category": "Productivity & Documents", "risk": "Spreadsheet Footprint"},
    "com.microsoft.office.powerpoint": {"name": "Microsoft PowerPoint", "category": "Productivity & Documents", "risk": "Presentation Footprint"},
    "com.microsoft.office.officehubrow": {"name": "Microsoft 365 Copilot", "category": "Productivity & Office", "risk": "Document Footprint"},
    "com.microsoft.teams": {"name": "Microsoft Teams", "category": "Workplace Communication", "risk": "Meeting & Chat Traces"},
    "com.replit.app": {"name": "Replit Coding IDE", "category": "Developer Tools", "risk": "Source Code Traces"},
    "com.mathworks.matlabmobile": {"name": "MATLAB Mobile", "category": "Engineering & Math", "risk": "Algorithm Data"},
    
    # Shopping & Travel
    "in.amazon.mShop.android.shopping": {"name": "Amazon India", "category": "E-Commerce & Shopping", "risk": "Order Traces"},
    "com.flipkart.android": {"name": "Flipkart", "category": "E-Commerce & Shopping", "risk": "Order Traces"},
    "com.meesho.supply": {"name": "Meesho Online Shopping", "category": "E-Commerce & Shopping", "risk": "Order Traces"},
    "com.whereismytrain.android": {"name": "Where is my Train", "category": "Travel & Transit", "risk": "Transit History"},
    "com.tnstc": {"name": "TNSTC Bus Booking", "category": "Travel & Transit", "risk": "Travel History"},
    "com.eaglefleet.redtaxi": {"name": "Red Taxi Cabs", "category": "Travel & Transit", "risk": "Trip History"},
    
    # Media & Gaming
    "com.spotify.music": {"name": "Spotify Streaming", "category": "Media & Entertainment", "risk": "Standard"},
    "com.winzo.gold": {"name": "WinZO Gaming Portal", "category": "Real-Money Gaming", "risk": "Financial Gaming Traces"},
    "com.chess": {"name": "Chess.com", "category": "Gaming & Strategy", "risk": "Standard"},
    "com.Rohit.IndianBikes": {"name": "Indian Bikes Driving 3D", "category": "Mobile Gaming", "risk": "Standard"}
}

class AppsRecovery:
    def __init__(self, adb_manager, output_dir=None):
        self.adb = adb_manager
        if output_dir is None:
            self.output_dir = Path(__file__).resolve().parent.parent / "recovered_data" / "apps"
        else:
            self.output_dir = Path(output_dir) / "apps"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "apks").mkdir(parents=True, exist_ok=True)

    def extract_apps_inventory(self, serial=None):
        """
        Gathers:
        1. All installed third-party apps with version, APK path, install dates.
        2. Detected deleted/uninstalled app residue from /sdcard/Android/data/.
        3. Standalone APK installers carved from download/cache directories.
        """
        prefix = ["-s", serial] if serial else []
        installed_apps = []
        installed_package_names = set()

        # 1. Query installed third-party packages
        success, out = self.adb.run_cmd(prefix + ["shell", "pm", "list", "packages", "-3", "-f"], timeout=20)
        if success and out:
            for line in out.strip().splitlines():
                line = line.strip()
                if line.startswith("package:"):
                    # Format: package:/data/app/~~...==/base.apk=com.example.app
                    content = line[len("package:"):]
                    if "=" in content:
                        apk_path, pkg_name = content.rsplit("=", 1)
                        installed_package_names.add(pkg_name)
                        
                        meta = self._get_package_metadata(pkg_name, prefix)
                        catalog_info = KNOWN_APP_CATALOG.get(pkg_name, {})
                        friendly_name = catalog_info.get("name", self._generate_friendly_name(pkg_name))
                        category = catalog_info.get("category", "General Application")
                        risk = catalog_info.get("risk", "Standard Application")

                        installed_apps.append({
                            "package_name": pkg_name,
                            "name": friendly_name,
                            "category": category,
                            "forensic_risk": risk,
                            "apk_path": apk_path,
                            "version_name": meta.get("version_name", "N/A"),
                            "version_code": meta.get("version_code", "N/A"),
                            "first_install_time": meta.get("first_install", "N/A"),
                            "last_update_time": meta.get("last_update", "N/A"),
                            "status": "Installed (Active)",
                            "is_installed": True
                        })

        # Sort installed apps by friendly name
        installed_apps.sort(key=lambda x: x["name"].lower())

        # 2. Detect Deleted / Uninstalled App Residue in /sdcard/Android/data/
        uninstalled_residue = []
        success, out = self.adb.run_cmd(prefix + ["shell", "ls", "-1", "/sdcard/Android/data/"], timeout=15)
        if success and out:
            for folder in out.strip().splitlines():
                folder = folder.strip()
                if not folder or folder in [".", ".."]:
                    continue
                
                # Check if package is NOT currently installed
                if folder not in installed_package_names and not folder.startswith("com.google.android.") and not folder.startswith("com.samsung.android.") and not folder.startswith("com.sec.android.") and not folder.startswith("android."):
                    catalog_info = KNOWN_APP_CATALOG.get(folder, {})
                    friendly_name = catalog_info.get("name", self._generate_friendly_name(folder))
                    category = catalog_info.get("category", "Uninstalled / Deleted Application")
                    
                    # Inspect folder size / files count
                    f_success, f_out = self.adb.run_cmd(prefix + ["shell", "ls", "-la", f"/sdcard/Android/data/{folder}"], timeout=5)
                    file_count = len(f_out.strip().splitlines()) if f_success and f_out else 0

                    uninstalled_residue.append({
                        "package_name": folder,
                        "name": f"{friendly_name} (Uninstalled)",
                        "category": category,
                        "status": "Deleted / Uninstalled App Residue",
                        "is_installed": False,
                        "residue_path": f"/sdcard/Android/data/{folder}",
                        "evidence_found": f"{file_count} lingering files/directories in shared storage",
                        "forensic_proof": "Storage folder remains on device after user uninstalled app."
                    })

        # 3. Pull sample APKs for top forensic apps (e.g. WhatsApp, Truecaller, DigiLocker, etc.) if possible
        manifest = {
            "installed_apps_count": len(installed_apps),
            "uninstalled_residue_count": len(uninstalled_residue),
            "installed_apps": installed_apps,
            "uninstalled_residue": uninstalled_residue,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Save to disk
        out_file = self.output_dir / "apps_inventory.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        return manifest

    def _get_package_metadata(self, pkg_name, prefix):
        """Extracts version and install timestamp using dumpsys package."""
        data = {"version_name": "N/A", "version_code": "N/A", "first_install": "N/A", "last_update": "N/A"}
        try:
            success, out = self.adb.run_cmd(prefix + ["shell", "dumpsys", "package", pkg_name], timeout=8)
            if success and out:
                for line in out.splitlines():
                    line = line.strip()
                    if line.startswith("versionName="):
                        data["version_name"] = line.split("=", 1)[1]
                    elif line.startswith("versionCode="):
                        data["version_code"] = line.split("=", 1)[1].split()[0]
                    elif line.startswith("firstInstallTime="):
                        data["first_install"] = line.split("=", 1)[1]
                    elif line.startswith("lastUpdateTime="):
                        data["last_update"] = line.split("=", 1)[1]
        except Exception:
            pass
        return data

    def _generate_friendly_name(self, pkg_name):
        parts = pkg_name.split(".")
        meaningful = [p.capitalize() for p in parts if p not in ["com", "org", "net", "app", "android", "in"]]
        if meaningful:
            return " ".join(meaningful)
        return pkg_name
