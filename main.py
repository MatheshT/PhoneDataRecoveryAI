import os
import sys
import time
import webbrowser
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.adb_manager import ADBManager
from core.call_logs_recovery import CallLogRecovery
from core.image_recovery import ImageRecovery
from core.ai_enhancer import AIEnhancer
from core.report_generator import ReportGenerator

def print_banner():
    banner = """
================================================================================
    SMARTPHONE FORENSIC DATA RECOVERY & AI RESTORATION SUITE
================================================================================
  [+] Deep Call Log Carving (Active + Telecom Buffers + SQLite Free-lists)
  [+] Advanced Image Carving (Hidden .thumbnails, .thumbdata, Media Caches)
  [+] AI Super-Resolution & Denoising Restoration
================================================================================
"""
    print(banner)

def main():
    print_banner()

    adb = ADBManager(base_dir=BASE_DIR)
    
    # Step 1: Ensure ADB is available
    print("[1/5] Checking ADB subsystem...")
    success, msg = adb.ensure_adb(progress_callback=print)
    if not success:
        print(f"[!] ERROR: {msg}")
        return
    print(f"[+] {msg}\n")

    # Step 2: Detect connected devices
    print("[2/5] Detecting connected Android phone over USB...")
    while True:
        devices = adb.get_connected_devices()
        if not devices:
            print("\n[!] No device detected over USB cable.")
            print("------------------------------------------------------------------")
            print("💡 HOW TO CONNECT YOUR PHONE:")
            print(" 1. Connect your phone to this PC using a USB cable.")
            print(" 2. On your phone, go to: Settings -> About Phone -> Software Info.")
            print(" 3. Tap 'Build Number' 7 times until Developer Mode is unlocked.")
            print(" 4. Go to: Settings -> Developer Options -> Enable 'USB Debugging'.")
            print(" 5. Look at your phone screen: a popup will ask 'Allow USB debugging?'.")
            print("    Check 'Always allow from this computer' and tap 'ALLOW'.")
            print("------------------------------------------------------------------")
            user_input = input("\nPress [ENTER] to re-scan for connected phone (or 'q' to quit): ").strip()
            if user_input.lower() == 'q':
                print("Exiting.")
                return
            continue

        target_device = devices[0]
        if target_device["status"] == "unauthorized":
            print("\n[!] Device detected but UNAUTHORIZED.")
            print(">> Please unlock your phone screen and tap 'ALLOW' on the USB debugging prompt!")
            input("After tapping 'ALLOW' on your phone, press [ENTER] to continue...")
            continue
        elif target_device["status"] == "device":
            print(f"[+] Device connected: Serial={target_device['serial']}")
            break
        else:
            print(f"[!] Device in status: {target_device['status']}. Reconnecting...")
            time.sleep(2)

    device_serial = target_device["serial"]
    dev_info = adb.get_device_info(serial=device_serial)
    print(f"\n[+] Target Phone Identified:")
    print(f"    • Manufacturer: {dev_info.get('manufacturer')}")
    print(f"    • Model:        {dev_info.get('model')}")
    print(f"    • Android OS:   {dev_info.get('android_version')} (SDK {dev_info.get('sdk_version')})")

    output_dir = BASE_DIR / "recovered_data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 3: Recover Call Logs
    print("\n[3/5] Starting Forensic Call Log Recovery...")
    call_rec = CallLogRecovery(adb, serial=device_serial)
    recovered_calls = call_rec.recover_all()
    print(f"[+] Total call log records extracted: {len(recovered_calls)}")

    # Step 4: Recover Images & Hidden Thumbnails
    print("\n[4/5] Starting Forensic Image & Thumbnail Carving...")
    img_rec = ImageRecovery(adb, serial=device_serial, output_dir=output_dir / "images")
    
    print("  -> Scanning active photos from Camera / Pictures / WhatsApp...")
    active_imgs = img_rec.pull_active_media(max_files=40, progress_cb=print)
    
    print("  -> Carving hidden and deleted image caches from .thumbnails & .thumbdata...")
    carved_imgs = img_rec.carve_thumbnail_caches(progress_cb=print)
    
    all_images = active_imgs + carved_imgs
    print(f"[+] Total images recovered / carved: {len(all_images)}")

    # Step 5: AI Super-Resolution Enhancement
    print("\n[5/5] Running AI Image Super-Resolution & Denoising...")
    enhancer = AIEnhancer(output_dir=output_dir / "images" / "ai_enhanced")
    # Enhance carved thumbnail images
    enhanced_results = enhancer.batch_enhance(carved_imgs[:30], progress_cb=print)
    print(f"[+] AI enhanced images generated: {len(enhanced_results)}")

    # Step 6: Generate Report & Dashboard
    print("\n[*] Generating Interactive HTML Dashboard & CSV exports...")
    reporter = ReportGenerator(output_dir=output_dir / "report")
    csv_path = reporter.export_call_logs_csv(recovered_calls)
    html_path = reporter.generate_html_report(dev_info, recovered_calls, all_images, enhanced_results)

    print("\n================================================================================")
    print("                     [+] FORENSIC RECOVERY COMPLETE! [+]")
    print("================================================================================")
    print(f"[*] Recovered Data Folder: {output_dir}")
    print(f"[*] CSV Call Logs:         {csv_path}")
    print(f"[*] HTML Dashboard:        {html_path}")
    print("================================================================================\n")

    # Automatically open the report in the default browser
    try:
        webbrowser.open(Path(html_path).as_uri())
    except Exception:
        pass

if __name__ == "__main__":
    main()
