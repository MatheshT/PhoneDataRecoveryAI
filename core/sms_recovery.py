import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

class SMSRecovery:
    def __init__(self, adb_manager, output_dir=None):
        self.adb = adb_manager
        if output_dir is None:
            self.output_dir = Path(__file__).resolve().parent.parent / "recovered_data" / "sms"
        else:
            self.output_dir = Path(output_dir) / "sms"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_sms(self, serial=None):
        """
        Extracts SMS messages from connected device via ADB content queries
        and scans device storage for SMS backup files (.xml, .json, .bak).
        """
        all_messages = []
        prefix = ["-s", serial] if serial else []

        # 1. Try direct ADB query on content://sms
        success, out = self.adb.run_cmd(
            prefix + ["shell", "content", "query", "--uri", "content://sms", "--projection", "_id,address,body,date,type,read"],
            timeout=25
        )

        if success and "Row:" in out:
            parsed_direct = self._parse_content_query_sms(out)
            for msg in parsed_direct:
                msg["source"] = "Direct Device SMS Provider"
                all_messages.append(msg)

        # 2. Scan device storage for SMS backups (.xml, .json, .bak)
        scanned_backups = self._scan_device_sms_backups(serial)
        for msg in scanned_backups:
            all_messages.append(msg)

        # 3. Scan local recovered_data directory for previously dumped backups
        local_sms = self._scan_local_sms_backups()
        for msg in local_sms:
            all_messages.append(msg)

        # De-duplicate messages based on address + timestamp + body snippet
        unique_messages = []
        seen = set()
        for m in all_messages:
            key = f"{m.get('address')}_{m.get('timestamp')}_{m.get('body', '')[:30]}"
            if key not in seen:
                seen.add(key)
                # Classify message
                m["category"] = self.classify_sms(m)
                unique_messages.append(m)

        # Sort by timestamp descending
        unique_messages.sort(key=lambda x: x.get("timestamp_raw", 0), reverse=True)

        # Save to JSON
        json_path = self.output_dir / "recovered_sms.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(unique_messages, f, indent=2, ensure_ascii=False)

        return unique_messages

    def _parse_content_query_sms(self, raw_output):
        messages = []
        rows = raw_output.split("Row:")
        for row in rows:
            if not row.strip():
                continue
            msg = {}
            for field in ["_id", "address", "body", "date", "type", "read"]:
                match = re.search(rf"{field}=([^,]+)", row)
                if match:
                    val = match.group(1).strip()
                    if field == "body":
                        # Body can contain commas, grab till next field or end
                        body_match = re.search(r"body=(.*?), (?:date|type|read)=", row)
                        if body_match:
                            val = body_match.group(1).strip()
                    msg[field] = val

            address = msg.get("address", "Unknown")
            body = msg.get("body", "")
            raw_date = msg.get("date", "0")
            msg_type = msg.get("type", "1")

            try:
                ms = int(raw_date)
                dt = datetime.fromtimestamp(ms / 1000.0)
                formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                timestamp_raw = int(ms / 1000)
            except Exception:
                formatted_date = "Unknown"
                timestamp_raw = 0

            # 1 = Received (Inbox), 2 = Sent, 3 = Draft, 4 = Outbox
            type_str = "Inbox" if msg_type == "1" else ("Sent" if msg_type == "2" else "Draft")

            messages.append({
                "id": msg.get("_id"),
                "address": address,
                "body": body,
                "date": formatted_date,
                "timestamp_raw": timestamp_raw,
                "type": type_str,
                "read": msg.get("read") == "1"
            })
        return messages

    def _scan_device_sms_backups(self, serial=None):
        prefix = ["-s", serial] if serial else []
        messages = []
        # Find SMS XML files or JSON files on storage
        success, out = self.adb.run_cmd(
            prefix + ["shell", "find", "/sdcard/", "-name", "*sms*.xml", "-o", "-name", "*SMS*.xml", "2>/dev/null"],
            timeout=15
        )
        if success and out.strip():
            for remote_file in out.strip().splitlines():
                remote_file = remote_file.strip()
                if not remote_file:
                    continue
                local_dest = self.output_dir / Path(remote_file).name
                pull_ok, _ = self.adb.run_cmd(prefix + ["pull", remote_file, str(local_dest)], timeout=30)
                if pull_ok and local_dest.exists():
                    messages.extend(self._parse_sms_xml(local_dest))
        return messages

    def _scan_local_sms_backups(self):
        messages = []
        base = self.output_dir.parent
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".xml") and "sms" in f.lower():
                    messages.extend(self._parse_sms_xml(Path(root) / f))
                elif f.lower().endswith(".json") and "sms" in f.lower():
                    messages.extend(self._parse_sms_json(Path(root) / f))
        return messages

    def _parse_sms_xml(self, xml_file):
        messages = []
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            for sms in root.iter("sms"):
                address = sms.get("address", "Unknown")
                body = sms.get("body", "")
                date_str = sms.get("date", "0")
                type_val = sms.get("type", "1")
                try:
                    ms = int(date_str)
                    dt = datetime.fromtimestamp(ms / 1000.0)
                    formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                    timestamp_raw = int(ms / 1000)
                except Exception:
                    formatted_date = "Unknown"
                    timestamp_raw = 0

                type_str = "Inbox" if type_val == "1" else "Sent"
                messages.append({
                    "id": sms.get("sc_toa"),
                    "address": address,
                    "body": body,
                    "date": formatted_date,
                    "timestamp_raw": timestamp_raw,
                    "type": type_str,
                    "read": sms.get("read") == "1",
                    "source": f"Backup: {xml_file.name}"
                })
        except Exception:
            pass
        return messages

    def _parse_sms_json(self, json_file):
        messages = []
        try:
            with open(json_file, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
                items = data if isinstance(data, list) else data.get("messages", data.get("items", []))
                for item in items:
                    messages.append({
                        "id": item.get("id"),
                        "address": item.get("address", item.get("number", "Unknown")),
                        "body": item.get("body", item.get("message", "")),
                        "date": item.get("date", "Unknown"),
                        "timestamp_raw": item.get("timestamp_raw", 0),
                        "type": item.get("type", "Inbox"),
                        "read": item.get("read", True),
                        "source": f"Backup: {json_file.name}"
                    })
        except Exception:
            pass
        return messages

    def classify_sms(self, msg):
        """Classifies message into Banking, OTP, Spam/Promo, or Personal."""
        body = (msg.get("body") or "").lower()
        address = (msg.get("address") or "").lower()

        # OTP detection
        otp_patterns = [r"\botp\b", r"one[- ]time password", r"verification code", r"is your code", r"do not share"]
        for p in otp_patterns:
            if re.search(p, body):
                return "OTP / Verification"

        # Banking / Financial transaction
        bank_patterns = [r"debited", r"credited", r"inr", r"rs\.", r"a/c", r"account", r"upi", r"atm", r"bank", r"transferred", r"balance"]
        for p in bank_patterns:
            if re.search(p, body):
                return "Bank & Financial"

        # Spam / Promotional
        spam_patterns = [r"flat \d+%", r"discount", r"limited offer", r"click here", r"http://", r"https://", r"coupon", r"claim", r"winner", r"congratulations"]
        for p in spam_patterns:
            if re.search(p, body):
                return "Spam / Promo"

        # If sender address is numeric (10 digits or with +91)
        if re.search(r"\d{10}", address):
            return "Personal"

        return "Informational"
