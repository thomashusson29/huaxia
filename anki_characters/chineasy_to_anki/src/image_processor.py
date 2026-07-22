"""
Module de traitement d'image et de suppression du fond pour les cartes Chineasy.
Échantillonne la couleur de fond sous la barre de statut iPhone, génère un fond transparent avec anti-aliasing,
masque la barre d'état système et les bruits UI, et recadre l'illustration mnémotechnique.
Prise en charge native des cartes combinées 'Word of the Day'.
"""

import os
from PIL import Image, ImageFilter
import numpy as np

def detect_corner_background_color(image: Image.Image) -> tuple[int, int, int]:
    """
    Échantillonne la couleur de fond sous la barre de statut iPhone (y_ratio 0.20-0.40)
    pour déterminer la couleur de fond exacte (RGB) sans subir le noir du notch iPhone.
    """
    img_rgb = image.convert("RGB")
    width, height = img_rgb.size
    
    samples = []
    # Échantillonner les bords gauche, centre et droit entre 18% et 40% de la hauteur
    for x_ratio in [0.10, 0.50, 0.90]:
        for y_ratio in [0.20, 0.30, 0.40]:
            px = img_rgb.getpixel((int(width * x_ratio), int(height * y_ratio)))
            samples.append(px)
            
    median_color = np.median(samples, axis=0)
    return tuple(int(c) for c in median_color)

def remove_background(
    image_path: str,
    output_path: str,
    color_tolerance: float = 40.0,
    crop_illustration: bool = True,
    padding: int = 25,
    is_word_of_the_day: bool = False
) -> str:
    """
    Rend le fond de l'image transparent en se basant sur la couleur de fond échantillonnée.
    Masque la barre d'état et les boutons de l'interface UI, et recadre l'illustration.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img = Image.open(image_path).convert("RGBA")
    width, height = img.size
    
    # Si c'est une carte Word of the Day combinée, isoler la zone d'illustration du haut (15% à 52% de la hauteur)
    if is_word_of_the_day:
        box = (int(width * 0.05), int(height * 0.12), int(width * 0.95), int(height * 0.52))
        img = img.crop(box)
        width, height = img.size

    bg_rgb = detect_corner_background_color(img)
    bg_np = np.array(bg_rgb, dtype=float)
    
    img_np = np.array(img, dtype=float)
    rgb_channels = img_np[:, :, :3]
    
    diff = rgb_channels - bg_np
    dist = np.sqrt(np.sum(diff ** 2, axis=2))
    
    transition_width = 15.0
    alpha = np.clip((dist - color_tolerance) / transition_width * 255.0, 0, 255)
    
    if is_word_of_the_day:
        # Masquer la croix X en haut à gauche et les boutons ronds A / HP en bas à droite
        top_left_mask = int(height * 0.12)
        alpha[:top_left_mask, :int(width * 0.20)] = 0
        bottom_right_mask_y = int(height * 0.78)
        bottom_right_mask_x = int(width * 0.65)
        alpha[bottom_right_mask_y:, bottom_right_mask_x:] = 0
    else:
        # Masquage standard de la barre d'état et des marges supérieures/inférieures
        top_crop_margin = int(height * 0.16)
        bottom_crop_margin = int(height * 0.12)
        alpha[:top_crop_margin, :] = 0
        alpha[height - bottom_crop_margin:, :] = 0

    alpha_img = Image.fromarray(alpha.astype(np.uint8), mode="L")
    alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(radius=1.2))
    
    img_rgba = img.copy()
    img_rgba.putalpha(alpha_img)
    
    if crop_illustration:
        bbox = alpha_img.getbbox()
        if bbox:
            left = max(0, bbox[0] - padding)
            top = max(0, bbox[1] - padding)
            right = min(width, bbox[2] + padding)
            bottom = min(height, bbox[3] + padding)
            img_rgba = img_rgba.crop((left, top, right, bottom))
            
    img_rgba.save(output_path, format="PNG")
    return output_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        remove_background(sys.argv[1], sys.argv[2])
