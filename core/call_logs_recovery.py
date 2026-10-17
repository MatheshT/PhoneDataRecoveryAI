import re
import datetime
from pathlib import Path

CALL_TYPES = {
    "1": "Incoming",
    "2": "Outgoing",
    "3": "Missed",
    "4": "Voicemail",
    "5": "Rejected",
    "6": "Blocked",
}

class CallLogRecovery:
    def __init__(self, adb_manager, serial=None):
        self.adb = adb_manager
        self.serial = serial
        self.prefix = ["-s", serial] if serial else []
        self.known_contacts = {} # { "+917538868096": "Mano" }

    def _parse_row(self, line, default_status="Active Record"):
        """Helper to parse a single line from content query output."""
        record = {
            "id": None,
            "number": "Unknown",
            "name": "Unknown",
            "date": "Unknown",
            "timestamp_raw": 0,
            "duration": "0s",
            "duration_sec": 0,
            "type": "Unknown",
            "status": default_status
        }

        for token in re.findall(r'(\w+)=([^,]+)', line):
            key, val = token[0], token[1].strip()
            if key == "_id":
                try:
                    record["id"] = int(val)
                except Exception:
                    pass
            elif key == "number":
                record["number"] = val if val != "NULL" else "Private / Unknown"
            elif key == "name":
                record["name"] = val if val != "NULL" else "Unnamed"
            elif key == "date":
                try:
                    ts = int(val) // 1000
                    record["timestamp_raw"] = ts
                    record["date"] = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    record["date"] = val
            elif key == "duration":
                try:
                    dur = int(val)
                    record["duration_sec"] = dur
                    mins, secs = divmod(dur, 60)
                    record["duration"] = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                except Exception:
                    record["duration"] = f"{val}s"
            elif key == "type":
                record["type"] = CALL_TYPES.get(val, f"Type {val}")

        # Store in known contacts cache
        if record["number"] != "Unknown" and record["name"] not in ["Unknown", "Unnamed"]:
            self.known_contacts[record["number"]] = record["name"]

        return record

    def extract_active_call_logs(self):
        """Queries Android standard CallLog provider."""
        cols = "_id:number:date:duration:type:name"
        args = self.prefix + [
            "shell", "content", "query",
            "--uri", "content://call_log/calls",
            "--projection", cols
        ]
        success, output = self.adb.run_cmd(args, timeout=60)
        if not success or not output:
            return {}, []

        records_map = {}
        records_list = []
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("Row:"):
                continue
            rec = self._parse_row(line, default_status="Active Record")
            if rec["id"] is not None:
                records_map[rec["id"]] = rec
            records_list.append(rec)

        return records_map, records_list

    def extract_samsung_deep_logs(self, active_ids_set):
        """
        Forensically queries Samsung's native logs/call provider.
        Any call present here but missing from active_ids_set was DELETED from dialer!
        """
        cols = "_id:number:date:duration:type:name"
        args = self.prefix + [
            "shell", "content", "query",
            "--uri", "content://logs/call",
            "--projection", cols
        ]
        success, output = self.adb.run_cmd(args, timeout=60)
        if not success or not output:
            return []

        deleted_records = []
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("Row:"):
                continue
            rec = self._parse_row(line, default_status="Active Record")
            rec_id = rec.get("id")

            # If present in Samsung deep logs but ABSENT from CallLog -> It's a DELETED CALL!
            if rec_id is not None and rec_id not in active_ids_set:
                rec["status"] = "Deleted Call (Carved from Samsung System Logs)"
                # If name is unknown, try matching with known contacts
                if rec["name"] in ["Unknown", "Unnamed"] and rec["number"] in self.known_contacts:
                    rec["name"] = self.known_contacts[rec["number"]]
                deleted_records.append(rec)

        return deleted_records

    def load_phonebook_contacts(self):
        """Loads contacts from phonebook for accurate de-masking."""
        args = self.prefix + ["shell", "content", "query", "--uri", "content://com.android.contacts/data/phones", "--projection", "data1:display_name"]
        success, out = self.adb.run_cmd(args, timeout=30)
        if success and out:
            for line in out.splitlines():
                m_num = re.search(r'data1=([^,]+)', line)
                m_name = re.search(r'display_name=([^,]+)', line)
                if m_num and m_name:
                    cleaned_num = m_num.group(1).replace(" ", "").replace("-", "").strip()
                    self.known_contacts[cleaned_num] = m_name.group(1).strip()

    def de_mask_number(self, masked_num):
        """Resolves masked phone numbers (e.g. +91*******712 or 95******23) to full contact info."""
        if "*" not in masked_num:
            name = self.known_contacts.get(masked_num, "Unknown")
            return masked_num, name

        # Split on asterisks to get prefix and suffix
        parts = [p for p in masked_num.split("*") if p]
        if not parts:
            return masked_num, "Unknown"

        prefix = parts[0]
        suffix = parts[-1]

        for full_num, name in self.known_contacts.items():
            if full_num.startswith(prefix) and full_num.endswith(suffix):
                return full_num, name
            # Also try matching without country code
            if prefix.startswith("+91") and full_num.endswith(suffix):
                return full_num, name

        return masked_num, "Buffer Trace"

    def carve_dumpsys_call_artifacts(self, active_signatures_set):
        """
        Forensically carves calls directly from Samsung's telecom event buffer (REQUEST_ADD_CALL_LOG).
        This captures recently made/received calls that were deleted from the dialer.
        """
        args = self.prefix + ["shell", "dumpsys", "telecom"]
        success, output = self.adb.run_cmd(args, timeout=60)
        if not success or not output:
            return []

        carved = []
        # Pattern matching REQUEST_ADD_CALL_LOG blocks
        pattern = re.compile(
            r'REQUEST_ADD_CALL_LOG.*?Number\s*:\s*(\+?[0-9*]+).*?CallType\s*:\s*(\d+).*?Start\s*:\s*(\d+).*?Duration\s*:\s*(\d+)',
            re.DOTALL
        )

        matches = pattern.findall(output)
        for raw_num, ctype, start_ms, dur_str in matches:
            try:
                start_int = int(start_ms)
                ts_sec = start_int // 1000
                dt_str = datetime.datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")
                dur = int(dur_str)
                mins, secs = divmod(dur, 60)
                dur_fmt = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"

                resolved_num, contact_name = self.de_mask_number(raw_num)
                call_type = CALL_TYPES.get(ctype, f"Type {ctype}")

                # Check if this call is currently present in active call log
                sig = (resolved_num, ts_sec)
                # also check +/- 3 seconds tolerance for provider write delays
                is_active = any((resolved_num, ts_sec + delta) in active_signatures_set for delta in range(-3, 4))

                if not is_active:
                    carved.append({
                        "id": None,
                        "number": resolved_num,
                        "name": contact_name,
                        "date": dt_str,
                        "timestamp_raw": ts_sec,
                        "duration": dur_fmt,
                        "duration_sec": dur,
                        "type": call_type,
                        "status": "Deleted Call (Recovered from Telecom Event Buffer)"
                    })
            except Exception as e:
                continue

        # Pattern 2: Legacy TouchWiz / Android 7 Analytics Call blocks
        pattern_legacy = re.compile(
            r'Call TC@\d+:\s*\{\s*startTime:\s*(\d+)\s*endTime:\s*(\d+)\s*direction:\s*(\w+)',
            re.DOTALL
        )
        for start_ms, end_ms, direction in pattern_legacy.findall(output):
            try:
                start_int = int(start_ms)
                ts_sec = start_int // 1000
                end_int = int(end_ms)
                dur = max(0, (end_int - start_int) // 1000)
                mins, secs = divmod(dur, 60)
                dur_fmt = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                dt_str = datetime.datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")

                call_type = "Incoming" if "INCOMING" in direction else ("Outgoing" if "OUTGOING" in direction else direction)

                carved.append({
                    "id": None,
                    "number": "Carrier Network Trace",
                    "name": "Telecom Call Session",
                    "date": dt_str,
                    "timestamp_raw": ts_sec,
                    "duration": dur_fmt,
                    "duration_sec": dur,
                    "type": call_type,
                    "status": "Recovered from Telecom Kernel Buffer (Deleted/Historical)"
                })
            except Exception:
                continue

        return carved

    def scan_sdcard_calllog_backups(self):
        """
        Scans SD card for call log backups (e.g., XML/JSON/CSV from backup tools or exports).
        """
        search_dirs = ["/sdcard/SMSBackupRestore", "/sdcard/Download", "/sdcard"]
        recovered = []
        for sdir in search_dirs:
            args = self.prefix + ["shell", "ls", "-1", f'"{sdir}"']
            success, out = self.adb.run_cmd(args, timeout=20)
            if not success or not out:
                continue

            for fname in out.splitlines():
                fname = fname.strip()
                if "call" in fname.lower() and fname.endswith((".xml", ".json", ".csv", ".bak")):
                    remote_file = f"{sdir}/{fname}"
                    local_temp = Path("./recovered_data") / f"temp_{fname}"
                    local_temp.parent.mkdir(parents=True, exist_ok=True)
                    p_success, _ = self.adb.run_cmd(self.prefix + ["pull", remote_file, str(local_temp)], timeout=60)
                    if p_success and local_temp.exists():
                        try:
                            content = local_temp.read_text(encoding="utf-8", errors="ignore")
                            # 1. Try JSON parsing (for .bak / .json format)
                            try:
                                import json
                                json_data = json.loads(content)
                                if isinstance(json_data, dict) and "items" in json_data:
                                    for item in json_data["items"]:
                                        raw_date = item.get("date", 0)
                                        raw_int = int(raw_date)
                                        ts_sec = raw_int // 1000 if raw_int > 10000000000 else raw_int
                                        dt_str = datetime.datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S") if ts_sec > 0 else "Unknown Date"
                                        dur = int(item.get("duration", 0))
                                        mins, secs = divmod(dur, 60)
                                        dur_fmt = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                                        call_type = CALL_TYPES.get(str(item.get("type", "1")), "Incoming")

                                        recovered.append({
                                            "id": None,
                                            "number": item.get("number", "Unknown"),
                                            "name": item.get("name") or "Saved Contact",
                                            "date": dt_str,
                                            "timestamp_raw": ts_sec,
                                            "duration": dur_fmt,
                                            "duration_sec": dur,
                                            "type": call_type,
                                            "status": "Recovered Call Log (From Device Backup)"
                                        })
                            except Exception:
                                pass

                            # 2. Try XML parsing for calls
                            call_tags = re.findall(r'<call\s+([^>]+)/>', content)
                            for tag in call_tags:
                                attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
                                raw_date = attrs.get("date", "0")
                                ts_sec = int(raw_date) // 1000 if len(raw_date) > 10 else int(raw_date)
                                dt_str = attrs.get("readable_date") or (datetime.datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S") if ts_sec > 0 else "Historical Backup")
                                dur = int(attrs.get("duration", 0))
                                mins, secs = divmod(dur, 60)
                                dur_fmt = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                                call_type = CALL_TYPES.get(attrs.get("type", "1"), "Incoming")

                                recovered.append({
                                    "id": None,
                                    "number": attrs.get("number", "Unknown"),
                                    "name": attrs.get("name") or "Saved Contact",
                                    "date": dt_str,
                                    "timestamp_raw": ts_sec,
                                    "duration": dur_fmt,
                                    "duration_sec": dur,
                                    "type": call_type,
                                    "status": "Recovered from SD Card CallLog Backup"
                                })
                        except Exception:
                            continue

        return recovered

    def recover_all(self):
        """
        Executes active extraction + Samsung deep log cross-reference + telecom buffer event carving + SD card backup scans.
        """
        # 0. Pre-load address book
        self.load_phonebook_contacts()

        # 1. Extract active call logs
        active_map, active_list = self.extract_active_call_logs()
        active_ids = set(active_map.keys())

        # Build signatures set (number, timestamp_sec) for fast deleted detection
        active_signatures = set()
        for r in active_list:
            if r.get("timestamp_raw") and r.get("number"):
                active_signatures.add((r["number"], r["timestamp_raw"]))

        # 2. Carve deleted calls preserved in Samsung system logs
        samsung_deleted = self.extract_samsung_deep_logs(active_ids)

        # 3. Carve deleted calls preserved in Telecom event buffer (catches the most recent deleted calls!)
        telecom_deleted = self.carve_dumpsys_call_artifacts(active_signatures)

        # 4. Scan SD card for any existing call backups
        sdcard_calls = self.scan_sdcard_calllog_backups()

        # Put carved deleted records and SD card records FIRST!
        all_records = telecom_deleted + samsung_deleted + sdcard_calls + active_list

        # Deduplicate by number + date
        seen = set()
        deduped = []
        for r in all_records:
            # Clean number for dedup
            num_clean = r.get("number", "").replace(" ", "").replace("-", "")
            key = (num_clean, r.get("date"), r.get("type"))
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        # SORT BY TIMESTAMP DESCENDING
        deduped.sort(key=lambda x: x.get("timestamp_raw", 0), reverse=True)

        return deduped
