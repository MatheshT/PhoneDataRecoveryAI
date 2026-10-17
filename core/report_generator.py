import csv
import json
import base64
from pathlib import Path
from datetime import datetime

class ReportGenerator:
    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir) if output_dir else Path("./recovery_report")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_call_logs_csv(self, call_logs, filename="recovered_call_logs.csv"):
        out_csv = self.output_dir / filename
        fields = ["number", "name", "date", "duration", "type", "status"]
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for log in call_logs:
                writer.writerow(log)
        return str(out_csv)

    def generate_html_report(self, device_info, call_logs, images, enhanced_images, filename="index.html"):
        report_path = self.output_dir / filename

        # Prepare log rows
        log_rows_html = ""
        for log in call_logs:
            badge_class = "badge-primary"
            status = log.get("status", "")
            if "Deleted" in status or "Carved" in status or "Buffer" in status:
                badge_class = "badge-danger"
            elif "Active" in status:
                badge_class = "badge-success"

            call_type = log.get("type", "Unknown")
            type_class = "badge-incoming" if "Incoming" in call_type else ("badge-outgoing" if "Outgoing" in call_type else "badge-missed")

            log_rows_html += f"""
            <tr>
                <td><strong>{log.get('number', 'Unknown')}</strong></td>
                <td>{log.get('name', 'Unknown')}</td>
                <td>{log.get('date', 'Unknown')}</td>
                <td>{log.get('duration', '0s')}</td>
                <td><span class="badge {type_class}">{call_type}</span></td>
                <td><span class="badge {badge_class}">{status}</span></td>
            </tr>
            """

        # Prepare image cards
        image_cards_html = ""
        for img in images[:100]:  # limit preview
            p = Path(img.get("path", ""))
            rel_path = p.name
            image_cards_html += f"""
            <div class="card image-card">
                <img src="{p.as_uri()}" alt="{rel_path}" loading="lazy" />
                <div class="card-desc">
                    <span class="img-name" title="{rel_path}">{rel_path}</span>
                    <span class="badge badge-info">{img.get('type', 'Media')}</span>
                </div>
            </div>
            """

        # Prepare enhanced cards
        enhanced_cards_html = ""
        for enh in enhanced_images[:50]:
            orig_p = Path(enh.get("original_path", ""))
            enh_p = Path(enh.get("enhanced_path", ""))
            enhanced_cards_html += f"""
            <div class="card comparison-card">
                <div class="comparison-grid">
                    <div>
                        <small>Original ({enh.get('original_dims')})</small>
                        <img src="{orig_p.as_uri()}" alt="Original" />
                    </div>
                    <div>
                        <small>AI Enhanced ({enh.get('enhanced_dims')})</small>
                        <img src="{enh_p.as_uri()}" alt="AI Enhanced" />
                    </div>
                </div>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forensic Data Recovery & AI Restoration Report</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --surface-color: #1e293b;
            --border-color: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background-color: var(--bg-color); color: var(--text-main); padding: 24px; }}
        .header {{ margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color); }}
        .header h1 {{ font-size: 26px; color: #38bdf8; display: flex; align-items: center; gap: 10px; }}
        .timestamp {{ color: var(--text-muted); font-size: 13px; margin-top: 4px; }}
        
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .stat-card {{ background: var(--surface-color); padding: 20px; border-radius: 12px; border: 1px solid var(--border-color); }}
        .stat-val {{ font-size: 28px; font-weight: bold; color: #38bdf8; }}
        .stat-label {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
        
        .tabs {{ display: flex; gap: 12px; margin-bottom: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; }}
        .tab-btn {{ background: transparent; border: none; color: var(--text-muted); font-size: 16px; font-weight: 600; padding: 8px 16px; cursor: pointer; border-radius: 8px; }}
        .tab-btn.active {{ background: #2563eb; color: white; }}
        
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        
        /* Table Styles */
        .search-box {{ margin-bottom: 16px; }}
        .search-box input {{ width: 100%; max-width: 400px; padding: 10px 14px; background: var(--surface-color); border: 1px solid var(--border-color); color: white; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; background: var(--surface-color); border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border-color); }}
        th {{ background: #1e293b; color: var(--text-muted); font-size: 13px; text-transform: uppercase; }}
        
        .badge {{ padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; display: inline-block; }}
        .badge-success {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .badge-danger {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}
        .badge-info {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; }}
        .badge-incoming {{ background: rgba(16, 185, 129, 0.15); color: #10b981; }}
        .badge-outgoing {{ background: rgba(59, 130, 246, 0.15); color: #3b82f6; }}
        .badge-missed {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; }}
        
        /* Images Grid */
        .gallery-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 16px; }}
        .card {{ background: var(--surface-color); border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; }}
        .image-card img {{ width: 100%; height: 160px; object-fit: cover; display: block; }}
        .card-desc {{ padding: 10px; display: flex; flex-direction: column; gap: 6px; }}
        .img-name {{ font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        
        .comparison-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 12px; }}
        .comparison-grid img {{ width: 100%; height: 220px; object-fit: cover; border-radius: 6px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Mobile Forensic Recovery & AI Restoration Report</h1>
        <div class="timestamp">Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Device: {device_info.get('manufacturer', '')} {device_info.get('model', 'Android Device')} (Android {device_info.get('android_version', 'N/A')})</div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-val">{len(call_logs)}</div>
            <div class="stat-label">Total Call Logs (Active & Carved)</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{len(images)}</div>
            <div class="stat-label">Recovered Photos & Thumbnails</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{len(enhanced_images)}</div>
            <div class="stat-label">AI Super-Resolved Photos</div>
        </div>
    </div>

    <div class="tabs">
        <button class="tab-btn active" onclick="openTab('logs')">📞 Call Logs ({len(call_logs)})</button>
        <button class="tab-btn" onclick="openTab('images')">🖼️ Recovered Photos ({len(images)})</button>
        <button class="tab-btn" onclick="openTab('enhanced')">✨ AI Enhanced Gallery ({len(enhanced_images)})</button>
    </div>

    <div id="logs" class="tab-content active">
        <div class="search-box">
            <input type="text" id="logSearch" placeholder="Filter by phone number, name, or status..." onkeyup="filterTable()">
        </div>
        <table id="logsTable">
            <thead>
                <tr>
                    <th>Phone Number</th>
                    <th>Contact Name</th>
                    <th>Timestamp</th>
                    <th>Duration</th>
                    <th>Type</th>
                    <th>Forensic Status</th>
                </tr>
            </thead>
            <tbody>
                {log_rows_html if log_rows_html else "<tr><td colspan='6'>No call logs retrieved.</td></tr>"}
            </tbody>
        </table>
    </div>

    <div id="images" class="tab-content">
        <div class="gallery-grid">
            {image_cards_html if image_cards_html else "<p>No images found or carved.</p>"}
        </div>
    </div>

    <div id="enhanced" class="tab-content">
        <div class="gallery-grid" style="grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));">
            {enhanced_cards_html if enhanced_cards_html else "<p>No AI enhanced images generated.</p>"}
        </div>
    </div>

    <script>
        function openTab(tabId) {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            event.currentTarget.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }}

        function filterTable() {{
            let input = document.getElementById("logSearch").value.toUpperCase();
            let tr = document.getElementById("logsTable").getElementsByTagName("tr");
            for (let i = 1; i < tr.length; i++) {{
                let txt = tr[i].textContent || tr[i].innerText;
                tr[i].style.display = (txt.toUpperCase().indexOf(input) > -1) ? "" : "none";
            }}
        }}
    </script>
</body>
</html>
        """

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return str(report_path)
