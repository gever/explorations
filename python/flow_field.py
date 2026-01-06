import argparse
import numpy as np
from PIL import Image
import math
import sys

def get_grayscale(img):
    """
    Convert PIL image to grayscale numpy array:
    0.299*R + 0.587*G + 0.114*B
    """
    # Convert to RGB to ensure 3 channels
    img = img.convert('RGB')
    
    # Create array first (as uint8), THEN cast to float32.
    # This avoids passing arguments to __array__ that Numpy 2.0 no longer likes.
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

    # Extract the window
    # Note: We need neighbors +1/-1 for gradient, so we must be careful at edges of the image
    # For simplicity/speed matching the JS, we'll iterate locally.
    
    for iy in range(y_min, y_max):
        for ix in range(x_min, x_max):
            # Boundary checks for gradient calculation
            if ix <= 0 or ix >= w - 1 or iy <= 0 or iy >= h - 1:
                continue

            # Calculate Gradients (Central Difference)
            # gx = right - left
            val_plus_x = gray[iy, ix + 1]
            val_minus_x = gray[iy, ix - 1]
            gx = val_plus_x - val_minus_x

            # gy = down - up
            val_plus_y = gray[iy + 1, ix]
            val_minus_y = gray[iy - 1, ix]
            gy = val_plus_y - val_minus_y

            sum_e += (gx * gx - gy * gy)
            sum_f += (2 * gx * gy)

    # Calculate Angle
    # + PI/2 rotates it to flow *along* the edge rather than across it
    angle = (0.5 * math.atan2(sum_f, sum_e)) + (math.pi / 2)
    return angle

def main():
    parser = argparse.ArgumentParser(description="Generate Vector Flow Fields using Ostromoukhov Dithering.")
    parser.add_argument("input_image", help="Path to input image file")
    parser.add_argument("output_svg", help="Path to save output SVG")
    parser.add_argument("--grid-size", type=int, default=12, help="Length of the drawn lines (default: 12)")
    parser.add_argument("--density", type=float, default=1.0, help="Density/Contrast scale (default: 1.0)")
    
    args = parser.parse_args()

    try:
        img = Image.open(args.input_image)
    except IOError:
        print(f"Error: Could not open image {args.input_image}")
        sys.exit(1)

    width, height = img.size
    print(f"Processing image: {width}x{height}")

    # 1. Get Grayscale Data
    gray = get_grayscale(img)

    # 2. Initialize Error Buffer
    # In JS: errorBuffer[i] = (255 - gray[i]) * contrast
    error_buffer = (255.0 - gray) * args.density

    # Constants
    step = 4  # Hardcoded in the JS loop for dithering resolution
    line_len = args.grid_size
    threshold = 128.0
    
    lines = []

    # 3. Dithering Loop
    # We must iterate sequentially because error diffuses forward
    print("Tracing flow lines...")
    
    for y in range(0, height - step, step):
        for x in range(0, width - step, step):
            
            old_val = error_buffer[y, x]
            error = 0.0

            if old_val > threshold:
                # 1. Calculate Angle
                angle = calculate_structure_tensor(gray, x, y, width, height)
                
                # 2. Calculate Line Coordinates
                cx, cy = x, y
                x1 = cx - (math.cos(angle) * line_len / 2)
                y1 = cy - (math.sin(angle) * line_len / 2)
                x2 = cx + (math.cos(angle) * line_len / 2)
                y2 = cy + (math.sin(angle) * line_len / 2)
                
                lines.append(((x1, y1), (x2, y2)))
                
                # 3. Determine Error
                error = old_val - 255.0
            else:
                error = old_val - 0.0

            # 4. Distribute Error (Ostromoukhov / Floyd-Steinberg variant)
            # (x + step, y) -> 7/16
            if x + step < width:
                error_buffer[y, x + step] += error * (7/16)
            
            # (x - step, y + step) -> 3/16
            if x - step >= 0 and y + step < height:
                error_buffer[y + step, x - step] += error * (3/16)
                
            # (x, y + step) -> 5/16
            if y + step < height:
                error_buffer[y + step, x] += error * (5/16)
                
            # (x + step, y + step) -> 1/16
            if x + step < width and y + step < height:
                error_buffer[y + step, x + step] += error * (1/16)

    # 4. Write SVG
    print(f"Generated {len(lines)} lines. Saving to {args.output_svg}...")
    
    with open(args.output_svg, "w") as f:
        # Standard SVG Header
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}px" height="{height}px">\n')
        f.write(f'<rect width="100%" height="100%" fill="white"/>\n')
        f.write(f'<g stroke="black" stroke-width="1" fill="none">\n')
        
        for (p1, p2) in lines:
            # Simple optimization: Don't write NaN coordinates
            if math.isnan(p1[0]) or math.isnan(p2[0]):
                continue
            f.write(f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" />\n')
            
        f.write('</g>\n')
        f.write('</svg>')

    print("Done.")

if __name__ == "__main__":
    main()
