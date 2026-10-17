import os
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter

class AIEnhancer:
    """
    AI & Computer Vision Image Restoration Engine.
    Restores, enhances, and upscales low-resolution carved photos and thumbnail artifacts.
    """
    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir) if output_dir else Path("./recovered_images/ai_enhanced")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def enhance_image(self, input_path, upscale_factor=2):
        """
        Enhances a recovered photo:
        1. Multi-scale Lanczos super-sampling
        2. Denoising / Smoothing of JPEG compression artifacts
        3. Unsharp Masking for micro-contrast edge recovery
        4. Dynamic range and color vibrance restoration
        """
        in_path = Path(input_path)
        if not in_path.exists():
            return None

        try:
            with Image.open(in_path) as img:
                img = img.convert("RGB")
                orig_w, orig_h = img.size

                # Step 1: Intelligent Upscaling
                new_w = orig_w * upscale_factor
                new_h = orig_h * upscale_factor
                enhanced = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # Step 2: Denoise filter to eliminate blocking artifacts
                enhanced = enhanced.filter(ImageFilter.SMOOTH_MORE)

                # Step 3: Unsharp mask to bring back sharpness & details
                enhanced = enhanced.filter(
                    ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3)
                )

                # Step 4: Contrast & Color Balance
                enhancer_contrast = ImageEnhance.Contrast(enhanced)
                enhanced = enhancer_contrast.enhance(1.15)

                enhancer_color = ImageEnhance.Color(enhanced)
                enhanced = enhancer_color.enhance(1.10)

                enhancer_sharp = ImageEnhance.Sharpness(enhanced)
                enhanced = enhancer_sharp.enhance(1.20)

                out_filename = f"enhanced_{in_path.stem}.jpg"
                out_path = self.output_dir / out_filename
                enhanced.save(out_path, format="JPEG", quality=95)

                return {
                    "original_path": str(in_path),
                    "enhanced_path": str(out_path),
                    "original_dims": f"{orig_w}x{orig_h}",
                    "enhanced_dims": f"{new_w}x{new_h}"
                }

        except Exception as e:
            print(f"Error enhancing {input_path}: {e}")
            return None

    def batch_enhance(self, image_list, max_workers=4, progress_cb=None):
        """Processes a list of recovered images through the enhancement pipeline."""
        results = []
        for i, item in enumerate(image_list):
            path = item.get("path") if isinstance(item, dict) else item
            if progress_cb:
                progress_cb(f"Enhancing image [{i+1}/{len(image_list)}]: {Path(path).name}")

            res = self.enhance_image(path)
            if res:
                results.append(res)

        return results
