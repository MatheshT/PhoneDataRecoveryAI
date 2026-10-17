import os
import io
from pathlib import Path
from PIL import Image

JPEG_START = b"\xFF\xD8\xFF"
JPEG_END = b"\xFF\xD9"
PNG_START = b"\x89PNG\r\n\x1a\n"
PNG_END = b"IEND\xaeB`\x82"

class ImageRecovery:
    def __init__(self, adb_manager, serial=None, output_dir=None):
        self.adb = adb_manager
        self.serial = serial
        self.prefix = ["-s", serial] if serial else []
        self.output_dir = Path(output_dir) if output_dir else Path("./recovered_images")
        self.active_dir = self.output_dir / "active_photos"
        self.carved_dir = self.output_dir / "carved_thumbnails"
        self.enhanced_dir = self.output_dir / "ai_enhanced"

        for d in [self.active_dir, self.carved_dir, self.enhanced_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def pull_active_media(self, max_files=50, progress_cb=None):
        """
        Pulls active photos from common media directories:
        DCIM/Camera, Pictures, WhatsApp Images.
        """
        sources = [
            "/sdcard/DCIM/Camera",
            "/sdcard/Pictures",
            "/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images",
            "/sdcard/WhatsApp/Media/WhatsApp Images"
        ]

        pulled_files = []
        for src in sources:
            if progress_cb:
                progress_cb(f"Scanning media directory: {src}")

            args = self.prefix + ["shell", "ls", "-1", f'"{src}"']
            success, out = self.adb.run_cmd(args)
            if not success or not out:
                continue

            filenames = [f.strip() for f in out.splitlines() if f.strip().lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
            for fname in filenames[:max_files]:
                remote_path = f"{src}/{fname}"
                local_path = self.active_dir / fname
                if not local_path.exists():
                    p_args = self.prefix + ["pull", remote_path, str(local_path)]
                    p_success, _ = self.adb.run_cmd(p_args, timeout=60)
                    if p_success and local_path.exists():
                        pulled_files.append({
                            "path": str(local_path),
                            "filename": fname,
                            "source": src,
                            "type": "Active Media"
                        })
                else:
                    pulled_files.append({
                        "path": str(local_path),
                        "filename": fname,
                        "source": src,
                        "type": "Active Media"
                    })

        return pulled_files

    def carve_thumbnail_caches(self, progress_cb=None):
        """
        Scans Android's .thumbnails directories and caches.
        When users delete photos from their gallery, the high-res thumbnail
        or preview cached in .thumbnails / .thumbdata is often preserved.
        """
        thumb_dirs = [
            "/sdcard/DCIM/.thumbnails",
            "/sdcard/Pictures/.thumbnails"
        ]

        carved_files = []
        for tdir in thumb_dirs:
            if progress_cb:
                progress_cb(f"Inspecting hidden thumbnail cache: {tdir}")

            args = self.prefix + ["shell", "ls", "-1", f'"{tdir}"']
            success, out = self.adb.run_cmd(args)
            if not success or not out:
                continue

            files = [f.strip() for f in out.splitlines() if f.strip()]
            for fname in files:
                remote_path = f"{tdir}/{fname}"
                temp_local = self.carved_dir / f"raw_{fname}"
                
                # If it's already a JPEG/PNG file
                if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                    target = self.carved_dir / fname
                    if not target.exists():
                        self.adb.run_cmd(self.prefix + ["pull", remote_path, str(target)], timeout=60)
                    if target.exists():
                        carved_files.append({
                            "path": str(target),
                            "filename": fname,
                            "source": tdir,
                            "type": "Preserved Gallery Cache"
                        })
                # If it's a .thumbdata container (binary blob packing multiple JPEGs)
                elif "thumbdata" in fname.lower() or fname.endswith(".dat"):
                    if not temp_local.exists():
                        if progress_cb:
                            progress_cb(f"Pulling thumbnail container for carving: {fname}")
                        self.adb.run_cmd(self.prefix + ["pull", remote_path, str(temp_local)], timeout=120)

                    if temp_local.exists():
                        extracted = self.carve_jpegs_from_binary(temp_local, prefix=fname)
                        carved_files.extend(extracted)

        return carved_files

    def carve_jpegs_from_binary(self, binary_file_path, prefix="carved"):
        """
        Forensic File Carving: Carves out embedded JPEG files from raw binary blobs
        using JPEG Magic Bytes (0xFFD8FF start and 0xFFD9 end).
        """
        path = Path(binary_file_path)
        if not path.exists():
            return []

        results = []
        try:
            with open(path, "rb") as f:
                data = f.read()

            start_idx = 0
            count = 0

            while True:
                soi = data.find(JPEG_START, start_idx)
                if soi == -1:
                    break

                eoi = data.find(JPEG_END, soi + 2)
                if eoi == -1:
                    break

                # Extract JPEG slice
                jpeg_data = data[soi:eoi + 2]
                start_idx = eoi + 2

                # Sanity check file size (e.g., must be > 1024 bytes to avoid corrupt tiny matches)
                if len(jpeg_data) < 1024:
                    continue

                try:
                    # Validate that PIL can parse the image header
                    img = Image.open(io.BytesIO(jpeg_data))
                    img.verify()

                    count += 1
                    out_filename = f"{prefix}_recovered_{count:04d}.jpg"
                    out_path = self.carved_dir / out_filename

                    with open(out_path, "wb") as out_f:
                        out_f.write(jpeg_data)

                    results.append({
                        "path": str(out_path),
                        "filename": out_filename,
                        "source": str(path.name),
                        "type": "Carved from Deleted Blob Container"
                    })
                except Exception:
                    # Not a valid image or corrupted slice
                    continue

        except Exception as e:
            print(f"Carving exception: {e}")

        return results
