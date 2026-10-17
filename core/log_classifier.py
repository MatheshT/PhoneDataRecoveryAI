import time
import datetime
from collections import Counter
from datetime import timedelta

class LogClassifier:
    """
    AI & Heuristic Classifier for Phone Call Logs.
    Filters by timeframe (Default: 1 Month) and classifies call behaviors.
    """

    @staticmethod
    def filter_by_months(call_logs, months=1):
        """
        Filters call logs to only include records from the last N months.
        Default is 1 month (30 days).
        If months is 0 or >= 999, returns all logs.
        Uses reference time based on the most recent call in the dataset to guarantee
        that historical logs from offline or archived phones are accurately captured.
        """
        if not months or months <= 0 or months >= 999:
            return call_logs

        # Determine reference time (anchor to the latest call in dataset)
        timestamps = [l.get("timestamp_raw", 0) for l in call_logs if l.get("timestamp_raw", 0) > 0]
        ref_time = max(timestamps) if timestamps else time.time()

        cutoff_seconds = months * 30 * 24 * 3600
        min_timestamp = ref_time - cutoff_seconds

        filtered = []
        for log in call_logs:
            raw_ts = log.get("timestamp_raw", 0)
            if raw_ts and raw_ts > 0:
                if raw_ts >= min_timestamp:
                    filtered.append(log)
            else:
                date_str = log.get("date", "")
                try:
                    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    if dt.timestamp() >= min_timestamp:
                        filtered.append(log)
                except Exception:
                    if any(x in str(log.get("status", "")) for x in ["Buffer", "Carved", "Deleted"]):
                        filtered.append(log)

        return filtered

    @staticmethod
    def filter_by_custom_range(call_logs, start_date_str=None, end_date_str=None):
        """
        Filters call logs by user-specified start date and end date (YYYY-MM-DD).
        """
        if not start_date_str and not end_date_str:
            return call_logs

        start_ts = 0
        end_ts = float('inf')

        if start_date_str:
            try:
                s_dt = datetime.datetime.strptime(start_date_str.strip(), "%Y-%m-%d")
                start_ts = s_dt.timestamp()
            except Exception:
                pass

        if end_date_str:
            try:
                e_dt = datetime.datetime.strptime(end_date_str.strip(), "%Y-%m-%d") + timedelta(days=1)
                end_ts = e_dt.timestamp()
            except Exception:
                pass

        filtered = []
        for log in call_logs:
            ts = log.get("timestamp_raw", 0)
            if not ts:
                date_str = log.get("date", "")
                try:
                    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    ts = dt.timestamp()
                except Exception:
                    pass
            if start_ts <= ts <= end_ts:
                filtered.append(log)

        return filtered


    @staticmethod
    def classify_logs(call_logs):
        """
        Performs multi-dimensional classification on call logs:
        - Relationship / Frequency (VIP, Frequent, One-time)
        - Contact Status (Saved Name vs Unknown Number)
        - Call Pattern (Long Talk, Quick Ping, Missed Call)
        - Security / Spam Footprint (Repeated unknown missed calls)
        - Forensic Status (Active vs Deleted / Carved)
        """
        if not call_logs:
            return {
                "classified_logs": [],
                "analytics": {
                    "total_calls": 0,
                    "incoming": 0,
                    "outgoing": 0,
                    "missed": 0,
                    "deleted_recovered": 0,
                    "top_contacts": [],
                    "categories": {}
                }
            }

        # Count caller frequency
        number_counts = Counter(log.get("number", "Unknown") for log in call_logs)
        
        classified_records = []
        analytics = {
            "total_calls": len(call_logs),
            "incoming": 0,
            "outgoing": 0,
            "missed": 0,
            "deleted_recovered": 0,
            "top_contacts": [],
            "categories": {
                "Frequent Contact": 0,
                "Unknown Number": 0,
                "Long Call (>10m)": 0,
                "Missed / Unanswered": 0,
                "Deleted / Forensic Trace": 0,
                "Potential Spam / Ping": 0,
                "Standard Call": 0
            }
        }

        for log in call_logs:
            rec = dict(log)
            tags = []
            
            num = rec.get("number", "Unknown")
            name = rec.get("name", "Unknown")
            call_type = rec.get("type", "Unknown")
            status = rec.get("status", "")
            duration_sec = rec.get("duration_sec", 0)

            # 1. Forensic Status Check
            if "Deleted" in status or "Carved" in status or "Buffer" in status:
                tags.append("Deleted / Forensic Trace")
                analytics["deleted_recovered"] += 1
                analytics["categories"]["Deleted / Forensic Trace"] += 1

            # 2. Call Type Breakdown
            if "Incoming" in call_type:
                analytics["incoming"] += 1
            elif "Outgoing" in call_type:
                analytics["outgoing"] += 1
            elif "Missed" in call_type:
                analytics["missed"] += 1
                tags.append("Missed / Unanswered")
                analytics["categories"]["Missed / Unanswered"] += 1

            # 3. Frequency / VIP
            count = number_counts.get(num, 0)
            if count >= 5:
                tags.append("Frequent Contact")
                analytics["categories"]["Frequent Contact"] += 1

            # 4. Unknown vs Saved
            if name in ["Unknown", "Unnamed", "NULL", "Private / Unknown"] or not name:
                tags.append("Unknown Number")
                analytics["categories"]["Unknown Number"] += 1
                # Check for spam ping (unknown + missed)
                if "Missed" in call_type and duration_sec == 0:
                    tags.append("Potential Spam / Ping")
                    analytics["categories"]["Potential Spam / Ping"] += 1

            # 5. Duration classification
            if duration_sec >= 600:
                tags.append("Long Call (>10m)")
                analytics["categories"]["Long Call (>10m)"] += 1
            elif duration_sec > 0 and duration_sec < 60:
                tags.append("Quick Call (<1m)")

            if not tags:
                tags.append("Standard Call")
                analytics["categories"]["Standard Call"] += 1

            rec["tags"] = tags
            rec["call_count"] = count
            classified_records.append(rec)

        # Top 5 most active contacts
        top = number_counts.most_common(5)
        analytics["top_contacts"] = [{"number": k, "count": v} for k, v in top if k != "Unknown"]

        return {
            "classified_logs": classified_records,
            "analytics": analytics
        }
