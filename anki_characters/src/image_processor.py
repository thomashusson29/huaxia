"""
Module de traitement d'image et de suppression du fond pour les cartes Chineasy.
Échantillonne la couleur des coins, génère un fond transparent avec anti-aliasing
et recadre l'illustration mnémotechnique.
"""

import os
from PIL import Image, ImageFilter
import numpy as np

def detect_corner_background_color(image: Image.Image, sample_size: int = 15) -> tuple[int, int, int]:
    """
    Échantillonne les 4 coins de l'image pour déterminer la couleur de fond dominante (RGB).
    """
    img_rgb = image.convert("RGB")
    width, height = img_rgb.size
    
    corners = [
        (0, 0, sample_size, sample_size),                                    # Top-Left
        (width - sample_size, 0, width, sample_size),                        # Top-Right
        (0, height - sample_size, sample_size, height),                      # Bottom-Left
        (width - sample_size, height - sample_size, width, height)           # Bottom-Right
    ]
    
    pixels = []
    for box in corners:
        crop = img_rgb.crop(box)
        arr = np.array(crop).reshape(-1, 3)
        pixels.append(arr)
        
    all_pixels = np.vstack(pixels)
    median_color = np.median(all_pixels, axis=0)
    return tuple(int(c) for c in median_color)

def remove_background(
    image_path: str,
    output_path: str,
    color_tolerance: float = 40.0,
    crop_illustration: bool = True,
    padding: int = 25
) -> str:
    """
    Rend le fond de l'image transparent en se basant sur la couleur de fond échantillonnée dans les coins.
    Applique un lissage des contours (anti-aliasing) et recadre l'illustration.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img = Image.open(image_path).convert("RGBA")
    
    bg_rgb = detect_corner_background_color(img)
    bg_np = np.array(bg_rgb, dtype=float)
    
    img_np = np.array(img, dtype=float)
    rgb_channels = img_np[:, :, :3]
    
    # Calcul de la distance euclidienne de chaque pixel par rapport à la couleur de fond
    diff = rgb_channels - bg_np
    dist = np.sqrt(np.sum(diff ** 2, axis=2))
    
    # Alpha brut: 0 pour le fond (dist <= tolerance), 255 pour l'objet (dist > tolerance + transition)
    transition_width = 15.0
    alpha = np.clip((dist - color_tolerance) / transition_width * 255.0, 0, 255)
    
    # Création de l'image alpha
    alpha_img = Image.fromarray(alpha.astype(np.uint8), mode="L")
    
    # Lissage léger du masque alpha pour éviter l'effet "escalier" (anti-aliasing)
    alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=1.2))
    
    # Assemblage RGBA
    img_rgba = img.copy()
    img_rgba.putalpha(alpha_img)
    
    # Si le recadrage est activé, on découpe la zone utile autour du dessin mnémotechnique
    if crop_illustration:
        bbox = alpha_img.getbbox()
        if bbox:
            w, h = img.size
            left = max(0, bbox[0] - padding)
            top = max(0, bbox[1] - padding)
            right = min(w, bbox[2] + padding)
            bottom = min(h, bbox[3] + padding)
            
            # Si le découpage inclut le mot du bas (ex: "person"), on peut découper le bas de l'image
            # ou conserver l'illustration entière.
            img_rgba = img_rgba.crop((left, top, right, bottom))
            
    img_rgba.save(output_path, format="PNG")
    return output_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        remove_background(sys.argv[1], sys.argv[2])
