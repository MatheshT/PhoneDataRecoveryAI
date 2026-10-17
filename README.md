# AegisForensic AI Intelligence Studio 📱🤖
### Enterprise-Grade Mobile Forensics, Artifact Carving & AI Restoration Suite

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Android-Forensics](https://img.shields.io/badge/Forensics-ADB%20%7C%20SQLite%20Carving-red.svg)](https://developer.android.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**AegisForensic AI Intelligence Studio** is a digital forensics acquisition, evidence carving, and AI restoration platform engineered for cybersecurity professionals, law enforcement, digital forensics analysts, and incident responders. 

It connects to Android smartphones over ADB (USB / Wi-Fi) to extract live telemetry, carve deleted records from unallocated database space and kernel telecom buffers, decrypt WhatsApp chat databases and voice notes, and apply AI super-resolution to carved media fragments.

---

## 🌟 Key Forensic Capabilities

### 1. 📞 Call Logs & Deleted Artifact Carving
- **Active Telephony**: Extracts incoming, outgoing, and missed call logs with caller ID metadata.
- **Telecom Event Buffers**: Carves transient telecom logs and cached dialer residue that was recently deleted from the user interface.
- **SQLite Raw Carver**: Searches raw database unallocated pages, rollbacks, and journals for phone number byte sequences.
- **Granular Controls**: Sub-millisecond timeframe filtering, individual record deletion, and single-click evidence certificate export.

### 2. 💬 SMS & Message Intelligence
- **Message Carving**: Extracts SMS inbox, sent, and draft messages from Android Telephony providers.
- **Financial & OTP Token Classifier**: Automatically tags banking notifications, OTP tokens, spam, and personal communications.
- **Search & Filter**: Real-time multi-keyword filter by sender address, token, or date range.

### 3. 👥 Address Book Contacts (.VCF Universal Export)
- **Contact Extraction**: Recovers contact profiles, phone numbers, and address book sources.
- **Forensic Export**: One-click generation of universal `.VCF` vCard format for direct import into case investigation tools or secondary devices.

### 4. 🎙️ Call Recordings & Audio Evidence
- **Voice Vault**: Detects and extracts call recordings from `/sdcard/Call/`, `/sdcard/Recordings/`, and audio dumps.
- **In-Browser Audio Player**: Dedicated player with playback speed controls, individual download, and evidence deletion.

### 5. 🖼️ Image Vault & AI Super-Resolution Enhancement
- **Active Media**: Recovers camera photos, screenshots, and WhatsApp media.
- **Thumbnail Cache Carver**: Recovers high-resolution preview caches from hidden `.thumbnails` directories.
- **Raw JPEG Magic Byte Carver**: Scans corrupted cache blobs (`.thumbdata*`) using JPEG markers (`0xFFD8FF` ... `0xFFD9`).
- **AI Computer Vision Engine**: Super-resolution upscaling (Lanczos multi-pass), compression artifact denoising, micro-contrast edge recovery, and color balancing.
- **Individual Download**: Instant high-speed single-image downloading for every carved photo.

### 6. 📁 Recovered Files & Document Carver
- **Document Discovery**: Carves PDF reports, Office documents (`.docx`, `.xlsx`), APK installers, archives (`.zip`, `.tar`), and certificates.
- **Forensic Hash Integrity**: Calculates SHA-256 and MD5 cryptographic hashes for chain-of-custody verification.

### 7. 📱 App Audit & Uninstalled Residue Detection
- **System & Third-Party Inventory**: Audits installed applications with version, installer package, and permissions.
- **Uninstalled App Residue**: Scans app data directories (`/data/data`, `/sdcard/Android/data`) for remnant configuration files, databases, and cached tokens left behind by uninstalled applications.

### 8. 🔐 WhatsApp Chat Vault & Encrypted DBs
- **Encrypted Databases**: Locates and downloads encrypted `msgstore.db.crypt14` databases.
- **Voice Notes & Opus Media**: Indexes voice notes and WhatsApp status media.
- **Evidence Deletion**: Granular deletion of individual voice notes or database backups.

### 9. 🎨 3D Kinetic HUD & Web Interface
- **Modern Futuristic Aesthetic**: Vibrant 3D embossed metric cards with interactive mouse-tracking kinetic tilt (`perspective(800px) rotateX/rotateY`).
- **Dynamic Timeframe Selector**: Client-side cached historical window selection (1 Month, 3 Months, 6 Months, 1 Year, 2 Years, All Time, or custom date ranges) running with sub-millisecond responsiveness.
- **Master Case Export**: Packages all extracted evidence, certificates, logs, and media into a unified `.ZIP` archive.

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10 or higher
- Android smartphone with USB Debugging enabled

### 1. Installation
```bash
git clone https://github.com/MatheshT/PhoneDataRecoveryAI.git
cd PhoneDataRecoveryAI
pip install -r requirements.txt
```

### 2. Connect Your Android Device
1. Connect your Android phone to the PC via USB cable.
2. In your phone: **Settings -> About Phone -> Software Information** -> Tap **Build Number 7 times** to unlock Developer Options.
3. In **Developer Options**, toggle **USB Debugging** to **ON**.
4. Allow the prompt on your phone screen: *"Allow USB debugging from this computer?"*.

### 3. Launch the Application
```bash
python run_web.py
```
The forensic studio will automatically start at `http://127.0.0.1:8000/` and open your default browser.

---

## 🧪 Automated Verification Test Suite

Run the built-in self-test suite to verify the binary carver, AI enhancer, and report generator:
```bash
python test_suite.py
```

---

## 📂 Project Architecture

```
PhoneDataRecoveryAI/
├── bin/                          # Google Android Platform-Tools (adb.exe)
├── core/
│   ├── adb_manager.py            # ADB lifecycle, device telemetry & acquisition
│   ├── call_logs_recovery.py     # SQLite and telecom buffer deleted log carver
│   ├── sms_recovery.py           # SMS extractor & financial/OTP token classifier
│   ├── contacts_recovery.py      # Address book recovery & universal .VCF exporter
│   ├── audio_recovery.py         # Voice note and call recording extractor
│   ├── image_recovery.py         # Media extractor & raw JPEG magic-byte carver
│   ├── ai_enhancer.py            # Super-resolution computer vision pipeline
│   ├── files_recovery.py         # Document, APK, and archive evidence carver
│   ├── apps_recovery.py          # Installed app auditor & residue scanner
│   ├── whatsapp_recovery.py      # WhatsApp crypt14 DBs and voice note parser
│   ├── log_classifier.py         # Intelligent log tagging and pattern matching
│   └── report_generator.py       # HTML case dashboard & CSV evidence generator
├── web_app/
│   ├── server.py                 # FastAPI backend server with forensic endpoints
│   └── static/
│       └── index.html            # 3D Kinetic HUD web interface (Three.js/CSS3D)
├── run_web.py                    # Fast server daemon launcher
├── main.py                       # CLI acquisition entry point
├── test_suite.py                 # Automated verification test suite
└── requirements.txt              # Project dependencies
```

---

## ⚖️ Legal & Ethical Notice

This software is developed strictly for **authorized digital forensic investigations**, educational research, and personal data recovery. Always ensure you have explicit written consent or legal authorization before acquiring data from any mobile device.

---

## 👨‍💻 Author
**MATHESH T**
- **GitHub**: [@MatheshT](https://github.com/MatheshT)
- **Email**: [matheshrmd@gmail.com](mailto:matheshrmd@gmail.com)
- **LinkedIn**: [Mathesh T](https://www.linkedin.com/in/mathesh-t-664112339)
