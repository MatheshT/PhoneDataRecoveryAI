import os
import re
import json
from pathlib import Path

class ContactsRecovery:
    def __init__(self, adb_manager, output_dir=None):
        self.adb = adb_manager
        if output_dir is None:
            self.output_dir = Path(__file__).resolve().parent.parent / "recovered_data" / "contacts"
        else:
            self.output_dir = Path(output_dir) / "contacts"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_contacts(self, serial=None):
        """
        Extracts phonebook contacts via ADB content queries and scans for .vcf files on storage.
        """
        contacts = []
        prefix = ["-s", serial] if serial else []

        # 1. Query content://contacts/phones/
        success, out = self.adb.run_cmd(
            prefix + ["shell", "content", "query", "--uri", "content://contacts/phones/", "--projection", "display_name,number,type"],
            timeout=20
        )
        if success and "Row:" in out:
            parsed = self._parse_contacts_query(out)
            for c in parsed:
                c["source"] = "Device Phonebook Provider"
                contacts.append(c)

        # 2. Query content://com.android.contacts/data/phones
        if not contacts:
            success, out = self.adb.run_cmd(
                prefix + ["shell", "content", "query", "--uri", "content://com.android.contacts/data/phones", "--projection", "display_name,data1"],
                timeout=20
            )
            if success and "Row:" in out:
                parsed = self._parse_contacts_query(out, num_field="data1")
                for c in parsed:
                    c["source"] = "Android Contacts Provider"
                    contacts.append(c)

        # 3. Scan for .vcf files on device
        vcf_contacts = self._scan_device_vcf_files(serial)
        contacts.extend(vcf_contacts)

        # 4. De-duplicate contacts
        unique_contacts = []
        seen = set()
        for c in contacts:
            norm_num = self._normalize_number(c.get("number", ""))
            key = f"{c.get('name')}_{norm_num}"
            if key not in seen and norm_num:
                seen.add(key)
                unique_contacts.append(c)

        # Sort alphabetically by name
        unique_contacts.sort(key=lambda x: (x.get("name") or "Unknown").lower())

        # Save to JSON
        json_path = self.output_dir / "recovered_contacts.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(unique_contacts, f, indent=2, ensure_ascii=False)

        # Also generate exportable master vCard (.vcf)
        self.export_to_vcf(unique_contacts, self.output_dir / "contacts_export.vcf")

        return unique_contacts

    def _normalize_number(self, num):
        if not num:
            return ""
        clean = re.sub(r"[^\d+]", "", num)
        if clean.startswith("+91") and len(clean) == 13:
            return clean[3:]
        if clean.startswith("0") and len(clean) == 11:
            return clean[1:]
        return clean

    def _parse_contacts_query(self, raw_output, num_field="number"):
        contacts = []
        for row in raw_output.split("Row:"):
            if not row.strip():
                continue
            name_match = re.search(r"display_name=(.*?), (?:number|data1|type)=", row)
            num_match = re.search(rf"{num_field}=([^,]+)", row)
            name = name_match.group(1).strip() if name_match else "Unknown"
            number = num_match.group(1).strip() if num_match else ""
            if number:
                contacts.append({
                    "name": name,
                    "number": number,
                    "normalized_number": self._normalize_number(number)
                })
        return contacts

    def _scan_device_vcf_files(self, serial=None):
        prefix = ["-s", serial] if serial else []
        contacts = []
        success, out = self.adb.run_cmd(
            prefix + ["shell", "find", "/sdcard/", "-name", "*.vcf", "-o", "-name", "*.vcard", "2>/dev/null"],
            timeout=15
        )
        if success and out.strip():
            for remote_file in out.strip().splitlines():
                remote_file = remote_file.strip()
                if not remote_file:
                    continue
                local_dest = self.output_dir / Path(remote_file).name
                pull_ok, _ = self.adb.run_cmd(prefix + ["pull", remote_file, str(local_dest)], timeout=25)
                if pull_ok and local_dest.exists():
                    contacts.extend(self._parse_vcf(local_dest))
        return contacts

    def _parse_vcf(self, vcf_file):
        contacts = []
        try:
            with open(vcf_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            cards = re.split(r"END:VCARD", content, flags=re.IGNORECASE)
            for card in cards:
                if "BEGIN:VCARD" not in card.upper():
                    continue
                name_match = re.search(r"(?:FN|N)(?:;[^:]*)?:(.*?)(?:\r?\n|$)", card, re.IGNORECASE)
                tel_matches = re.findall(r"TEL(?:;[^:]*)?:(.*?)(?:\r?\n|$)", card, re.IGNORECASE)
                name = name_match.group(1).strip() if name_match else "Unknown"
                for tel in tel_matches:
                    clean_tel = tel.strip()
                    if clean_tel:
                        contacts.append({
                            "name": name,
                            "number": clean_tel,
                            "normalized_number": self._normalize_number(clean_tel),
                            "source": f"vCard: {vcf_file.name}"
                        })
        except Exception:
            pass
        return contacts

    def export_to_vcf(self, contacts, output_vcf_path):
        """Exports all recovered contacts into a standard VCF file."""
        lines = []
        for c in contacts:
            lines.append("BEGIN:VCARD")
            lines.append("VERSION:3.0")
            lines.append(f"FN:{c.get('name', 'Unknown')}")
            lines.append(f"TEL;TYPE=CELL:{c.get('number', '')}")
            lines.append("END:VCARD\n")
        with open(output_vcf_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def enrich_logs_with_contacts(self, logs, contacts):
        """
        Takes a list of call logs or SMS and enriches any entry
        where 'name' is Unknown using the contacts address book.
        """
        contact_map = {}
        for c in contacts:
            norm = c.get("normalized_number")
            if norm:
                contact_map[norm] = c.get("name")

        for log in logs:
            num = log.get("number") or log.get("address")
            curr_name = log.get("name")
            if not curr_name or curr_name.strip() in ["Unknown", ""]:
                norm = self._normalize_number(num)
                if norm in contact_map:
                    log["name"] = contact_map[norm]
        return logs
