import os
import sys
import io
from pathlib import Path
from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.image_recovery import ImageRecovery
from core.ai_enhancer import AIEnhancer
from core.report_generator import ReportGenerator

def run_self_test():
    print("[*] Running automated verification of Forensic & AI modules...")

    test_dir = BASE_DIR / "test_scratch"
    test_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate a test synthetic image
    test_img = Image.new("RGB", (200, 200), color=(50, 120, 200))
    d = ImageDraw.Draw(test_img)
    d.text((30, 90), "Recovered Image Test", fill=(255, 255, 255))
    
    img_byte_arr = io.BytesIO()
    test_img.save(img_byte_arr, format='JPEG')
    jpeg_bytes = img_byte_arr.getvalue()

    # 2. Embed this JPEG into a simulated corrupt binary container (.thumbdata file)
    container_bytes = b"\x00\xFF\xAA\xBB" * 100 + jpeg_bytes + b"\xDE\xAD\xBE\xEF" * 100
    container_path = test_dir / "simulated.thumbdata"
    with open(container_path, "wb") as f:
        f.write(container_bytes)

    # 3. Test File Carver
    carver = ImageRecovery(None, output_dir=test_dir / "carved_output")
    carved = carver.carve_jpegs_from_binary(container_path, prefix="test_container")
    print(f"[+] File Carving verified! Extracted {len(carved)} embedded JPEG image.")

    # 4. Test AI Super-Resolution Enhancer
    enhancer = AIEnhancer(output_dir=test_dir / "enhanced_output")
    enhanced = enhancer.enhance_image(carved[0]["path"], upscale_factor=2)
    assert enhanced is not None, "AI Enhancer failed!"
    print(f"[+] AI Image Enhancement verified! Scaled from {enhanced['original_dims']} to {enhanced['enhanced_dims']}.")

    # 5. Test Report Generator
    sample_device = {
        "manufacturer": "Samsung",
        "model": "Galaxy Test Device",
        "android_version": "13",
        "sdk_version": "33"
    }
    sample_calls = [
        {"number": "+91 9876543210", "name": "Ravi", "date": "2026-10-15 14:30:00", "duration": "2m 15s", "type": "Incoming", "status": "Active Record"},
        {"number": "+91 9123456789", "name": "Buffer Trace", "date": "2026-10-16 09:12:00", "duration": "N/A", "type": "Missed / Ended", "status": "Recovered from Telecom Buffer (Deleted/Transient)"},
        {"number": "+91 9988776655", "name": "SQLite Free-List Fragment", "date": "Deleted Record Artifact", "duration": "N/A", "type": "Carved SQLite Fragment", "status": "Carved from Database Unallocated Space"}
    ]
    reporter = ReportGenerator(output_dir=test_dir / "report")
    csv_file = reporter.export_call_logs_csv(sample_calls)
    html_file = reporter.generate_html_report(sample_device, sample_calls, carved, [enhanced])
    
    assert Path(csv_file).exists(), "CSV report was not created!"
    assert Path(html_file).exists(), "HTML report was not created!"
    print(f"[+] Report Generator verified! HTML: {html_file}")
    print("\n>>> ALL FORENSIC & AI MODULE TESTS PASSED! <<<")

if __name__ == "__main__":
    run_self_test()
