import cv2
import numpy as np
import subprocess
import os
import math

# --- 1. CONFIGURATION ---
# IMPORTANT: Adjust these paths to match your file locations.
# The script uses the exact paths you provided.
INPUT_ICON_PATH = '/storage/emulated/0/Download/icon.png'
OUTPUT_VIDEO_PATH = '/storage/emulated/0/Download/icon_shine_effect.mp4'

# Video parameters
TOTAL_DURATION = 2.5  # Total video length in seconds
ANIM_START_TIME = 0.5 # When the shine animation starts
ANIM_DURATION = 1.0   # How long the shine animation lasts
FPS = 30              # Frames per second for the output video

# Shine effect parameters (you can tweak these)
SHINE_ANGLE_DEG = -60        # The angle of the shine bar in degrees
SHINE_WIDTH_FACTOR = 0.25    # Width of the shine, as a fraction of the icon's width

# --- 2. EASING FUNCTION (for smooth animation) ---
def ease_out_quad(t):
    """
    A quadratic easing function that starts fast and slows down.
    t: progress of the animation, from 0.0 to 1.0
    """
    return 1 - (1 - t) * (1 - t)

# --- 3. MAIN FUNCTION ---
def create_shine_animation():
    """
    Loads an icon, creates a shine effect animation, and saves it as a video.
    """
    # --- Step 1: Load the icon ---
    print(f"Loading icon from: {INPUT_ICON_PATH}")
    if not os.path.exists(INPUT_ICON_PATH):
        print("\n--- ERROR ---")
        print(f"Input file not found at '{INPUT_ICON_PATH}'")
        print("Please make sure the icon file exists at that exact path, or update the INPUT_ICON_PATH in the script.")
        return

    # Load image with its alpha channel (transparency)
    icon = cv2.imread(INPUT_ICON_PATH, cv2.IMREAD_UNCHANGED)
    if icon is None:
        print(f"Error: Could not read the image from {INPUT_ICON_PATH}. Check if the file is a valid image.")
        return

    # If image has no alpha channel, create a default one
    if icon.shape[2] == 3:
        print("Warning: Input image has no alpha channel. Adding a fully opaque one.")
        icon = cv2.cvtColor(icon, cv2.COLOR_BGR2BGRA)
        icon[:, :, 3] = 255

    H, W = icon.shape[:2]
    print(f"Icon dimensions: {W}x{H}")

    # --- Step 2: Prepare layers (as per CapCut logic) ---
    # The bottom layer is the original icon on a black background
    icon_bgr_float = (icon[:, :, :3] / 255.0).astype(np.float32)
    icon_alpha_float = (icon[:, :, 3] / 255.0).astype(np.float32)
    icon_alpha_3c = np.stack([icon_alpha_float] * 3, axis=-1)
    base_image = icon_bgr_float * icon_alpha_3c

    # The top layer is the "shine" layer (a white version of the icon)
    # This is done by maximizing the "Lightness" in the HSL color space
    hls = cv2.cvtColor(icon[:, :, :3], cv2.COLOR_BGR2HLS)
    hls[:, :, 1] = 255  # Set Lightness to max
    shine_bgr_uint8 = cv2.cvtColor(hls, cv2.COLOR_HLS2BGR)
    shine_bgr_float = (shine_bgr_uint8 / 255.0).astype(np.float32)

    # --- Step 3: Prepare for animation math ---
    # Create coordinate grids
    xx, yy = np.meshgrid(np.arange(W), np.arange(H))

    # The sweep direction is perpendicular to the shine bar's angle
    sweep_angle_rad = math.radians(SHINE_ANGLE_DEG + 90)
    
    # Project all pixel coordinates onto the sweep direction axis.
    # This creates a "distance map" for the sweep.
    sweep_map = xx * math.cos(sweep_angle_rad) + yy * math.sin(sweep_angle_rad)

    # Define the start and end positions for the sweep, ensuring it starts and ends off-screen
    shine_width_pixels = W * SHINE_WIDTH_FACTOR
    map_min, map_max = sweep_map.min(), sweep_map.max()
    sweep_start_pos = map_min - shine_width_pixels
    sweep_end_pos = map_max + shine_width_pixels
    sweep_distance = sweep_end_pos - sweep_start_pos

    # --- Step 4: Setup FFmpeg process to receive video frames ---
    command = [
        'ffmpeg',
        '-y',  # Overwrite output file if it exists
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{W}x{H}',
        '-pix_fmt', 'bgr24',  # OpenCV's default color order
        '-r', str(FPS),
        '-i', '-',  # Input from stdin pipe
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',  # For high compatibility
        '-preset', 'medium',
        '-crf', '18',          # Good quality-to-size ratio
        OUTPUT_VIDEO_PATH
    ]

    try:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("\n--- ERROR ---")
        print("FFmpeg not found. Please install FFmpeg and make sure it's in your system's PATH.")
        return

    # --- Step 5: Generate and write each frame ---
    TOTAL_FRAMES = int(TOTAL_DURATION * FPS)
    ANIM_START_FRAME = int(ANIM_START_TIME * FPS)
    ANIM_END_FRAME = ANIM_START_FRAME + int(ANIM_DURATION * FPS)

    print(f"\nGenerating {TOTAL_FRAMES} frames for a {TOTAL_DURATION}s video...")
    for i in range(TOTAL_FRAMES):
        # Determine if we are inside the animation period
        if i >= ANIM_START_FRAME and i < ANIM_END_FRAME:
            # Calculate animation progress (from 0.0 to 1.0)
            progress = (i - ANIM_START_FRAME) / (ANIM_END_FRAME - ANIM_START_FRAME)
            eased_progress = ease_out_quad(progress)
            
            # Calculate the shine bar's current center position
            current_pos = sweep_start_pos + eased_progress * sweep_distance
            
            # Create the animated mask: a soft, feathered bar (using a Gaussian function)
            dist_from_center = sweep_map - current_pos
            gauss_mask = np.exp(-(dist_from_center / (shine_width_pixels / 2.5))**2)
            
            # The final alpha for the shine is the Gaussian mask multiplied by the icon's own alpha
            shine_alpha = gauss_mask * icon_alpha_float
            shine_alpha_3c = np.stack([shine_alpha] * 3, axis=-1)

            # Composite the frame: (shine_layer * shine_alpha) + (base_icon * (1 - shine_alpha))
            final_frame_float = (shine_bgr_float * shine_alpha_3c) + (base_image * (1 - shine_alpha_3c))
        else:
            # Before or after the animation, just show the static base icon
            final_frame_float = base_image

        # Convert frame to 8-bit BGR format for FFmpeg
        final_frame_uint8 = np.clip(final_frame_float * 255, 0, 255).astype(np.uint8)
        
        # Write the frame to FFmpeg's input pipe
        proc.stdin.write(final_frame_uint8.tobytes())
        
        # Print progress to the console
        print(f"\rProcessing frame {i + 1}/{TOTAL_FRAMES}", end="")

    print("\n\nFinished generating frames. Waiting for FFmpeg to finish encoding...")

    # --- Step 6: Finalize the video ---
    # Close the pipe and wait for FFmpeg to complete
    stdout, stderr = proc.communicate()
    
    if proc.returncode != 0:
        print("\n--- FFmpeg Error ---")
        print(stderr.decode())
    else:
        print(f"\nSuccess! Video saved to: {OUTPUT_VIDEO_PATH}")


# --- Run the script ---
if __name__ == "__main__":
    create_shine_animation()
