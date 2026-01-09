import argparse
import numpy as np
from PIL import Image
import math
import sys

def get_grayscale(img):
    """
    Convert PIL image to grayscale numpy array matching the JS logic:
    0.299*R + 0.587*G + 0.114*B
    """
    # Convert to RGB to ensure 3 channels
    img = img.convert('RGB')
    
    # NumPy 2.0 Fix: Create array first, then cast
    data = np.array(img).astype(np.float32)
    
    # Perform the weighted sum
    gray = 0.299 * data[:, :, 0] + 0.587 * data[:, :, 1] + 0.114 * data[:, :, 2]
    return gray

def calculate_structure_tensor(gray, x, y, w, h, window_size=5):
    """
    Calculates the local orientation of features in the image.
    Returns the angle in radians.
    """
    half = window_size // 2
    sum_e = 0.0
    sum_f = 0.0
    
    # Define bounds to avoid checking boundaries inside the inner loop
    y_min = max(0, y - half)
    y_max = min(h, y + half + 1)
    x_min = max(0, x - half)
    x_max = min(w, x + half + 1)

    for iy in range(y_min, y_max):
        for ix in range(x_min, x_max):
            if ix <= 0 or ix >= w - 1 or iy <= 0 or iy >= h - 1:
                continue

            # Calculate Gradients (Central Difference)
            val_plus_x = gray[iy, ix + 1]
            val_minus_x = gray[iy, ix - 1]
            gx = val_plus_x - val_minus_x

            val_plus_y = gray[iy + 1, ix]
            val_minus_y = gray[iy - 1, ix]
            gy = val_plus_y - val_minus_y

            sum_e += (gx * gx - gy * gy)
            sum_f += (2 * gx * gy)

    # Calculate Angle (+ PI/2 rotates it to flow along the edge)
    angle = (0.5 * math.atan2(sum_f, sum_e)) + (math.pi / 2)
    return angle

def main():
    parser = argparse.ArgumentParser(description="Generate Vector Flow Fields using Ostromoukhov Dithering.")
    parser.add_argument("input_image", help="Path to input image file")
    parser.add_argument("output_svg", help="Path to save output SVG")
    parser.add_argument("--grid-size", type=int, default=12, help="Length of the drawn lines (default: 12)")
    parser.add_argument("--density", type=float, default=1.0, help="Density/Contrast scale (default: 1.0)")
    parser.add_argument("--max-dim", type=int, default=1024, help="Maximum dimension for resizing (default: 1024)")
    
    args = parser.parse_args()

    try:
        img = Image.open(args.input_image)
    except IOError:
        print(f"Error: Could not open image {args.input_image}")
        sys.exit(1)

    # --- Resizing Logic ---
    original_width, original_height = img.size
    max_dim = args.max_dim

    if max(original_width, original_height) > max_dim:
        scale_factor = max_dim / max(original_width, original_height)
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)
        
        print(f"Resizing image from {original_width}x{original_height} to {new_width}x{new_height}...")
        
        # Use Resampling.LANCZOS for high quality downsampling
        # (Fallbacks to Image.LANCZOS for older Pillow versions)
        resample_method = getattr(Image, 'Resampling', Image).LANCZOS
        img = img.resize((new_width, new_height), resample_method)
    else:
        print(f"Image size {original_width}x{original_height} is within limit ({max_dim}).")

    width, height = img.size
    
    # 1. Get Grayscale Data
    gray = get_grayscale(img)

    # 2. Initialize Error Buffer
    error_buffer = (255.0 - gray) * args.density

    # Constants
    step = 4  
    line_len = args.grid_size
    threshold = 128.0
    
    lines = []

    # 3. Dithering Loop
    print("Tracing flow lines...")
    
    for y in range(0, height - step, step):
        for x in range(0, width - step, step):
            
            old_val = error_buffer[y, x]
            error = 0.0

            if old_val > threshold:
                angle = calculate_structure_tensor(gray, x, y, width, height)
                
                cx, cy = x, y
                x1 = cx - (math.cos(angle) * line_len / 2)
                y1 = cy - (math.sin(angle) * line_len / 2)
                x2 = cx + (math.cos(angle) * line_len / 2)
                y2 = cy + (math.sin(angle) * line_len / 2)
                
                lines.append(((x1, y1), (x2, y2)))
                
                error = old_val - 255.0
            else:
                error = old_val - 0.0

            # Distribute Error
            if x + step < width:
                error_buffer[y, x + step] += error * (7/16)
            if x - step >= 0 and y + step < height:
                error_buffer[y + step, x - step] += error * (3/16)
            if y + step < height:
                error_buffer[y + step, x] += error * (5/16)
            if x + step < width and y + step < height:
                error_buffer[y + step, x + step] += error * (1/16)

    # 4. Write SVG
    print(f"Generated {len(lines)} lines. Saving to {args.output_svg}...")
    
    with open(args.output_svg, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}px" height="{height}px">\n')
        f.write(f'<rect width="100%" height="100%" fill="white"/>\n')
        f.write(f'<g stroke="black" stroke-width="1" fill="none">\n')
        
        for (p1, p2) in lines:
            if math.isnan(p1[0]) or math.isnan(p2[0]):
                continue
            f.write(f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" />\n')
            
        f.write('</g>\n')
        f.write('</svg>')

    print("Done.")

if __name__ == "__main__":
    main()
