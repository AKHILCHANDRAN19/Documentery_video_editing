import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os
import sys
import math
# Ensure 'packaging' is installed for version parsing: pip install packaging
from packaging.version import parse as parse_version
from PIL import __version__ as PILLOW_VERSION


# --- Configuration ---
DEFAULT_START_YEAR = 2000
DEFAULT_END_YEAR = 2010
ANIMATION_DURATION_SECONDS = 2.0
FONT_PATH = "/storage/emulated/0/Download/THEBOLDFONT.ttf"
OUTPUT_FOLDER = "/storage/emulated/0/Download/"
OUTPUT_FILENAME = "year_scroll_animation.mp4"

ASPECT_RATIO_W = 16
ASPECT_RATIO_H = 9
FRAME_WIDTH = 1280
FRAME_HEIGHT = int(FRAME_WIDTH * (ASPECT_RATIO_H / ASPECT_RATIO_W))
FPS = 30

BACKGROUND_COLOR_CV = (0, 0, 0)
TEXT_COLOR_PIL = (230, 230, 230, 255)

MASK_VISIBLE_HEIGHT_FACTOR = 0.20
FEATHER_AMOUNT_PIXELS = 50

# --- Helper Functions ---

def get_user_years():
    try:
        start_year_str = input(f"Enter start year for scroll (default: {DEFAULT_START_YEAR}): ")
        start_year = int(start_year_str) if start_year_str else DEFAULT_START_YEAR
    except ValueError:
        print(f"Invalid start year, using default: {DEFAULT_START_YEAR}")
        start_year = DEFAULT_START_YEAR

    try:
        end_year_str = input(f"Enter end year for scroll (default: {DEFAULT_END_YEAR}): ")
        end_year = int(end_year_str) if end_year_str else DEFAULT_END_YEAR
    except ValueError:
        print(f"Invalid end year, using default: {DEFAULT_END_YEAR}")
        end_year = DEFAULT_END_YEAR

    if start_year >= end_year:
        print("Start year must be less than end year for scrolling. Please re-enter.")
        return get_user_years()
    return start_year, end_year

def ease_in_out_cubic(t):
    t *= 2
    if t < 1:
        return 0.5 * t * t * t
    t -= 2
    return 0.5 * (t * t * t + 2)

def create_multi_year_text_image(years_list, font, text_color, line_spacing_factor=1.2):
    text_str = "\n".join(map(str, years_list))
    padding_internal = 20 # Internal padding used when creating the image

    dummy_img = Image.new("RGBA", (1, 1), (0,0,0,0))
    draw = ImageDraw.Draw(dummy_img)

    if not hasattr(draw, 'textbbox'):
        raise AttributeError("ImageDraw object is missing 'textbbox' method. Requires Pillow 8.0.0+.")

    single_year_bbox = draw.textbbox((0,0), str(years_list[0]), font=font, anchor="lt")
    single_line_actual_height = single_year_bbox[3] - single_year_bbox[1]
    single_line_render_height = int(single_line_actual_height * line_spacing_factor)
    spacing_for_multiline = single_line_render_height - single_line_actual_height

    if hasattr(draw, 'multiline_textbbox'):
        multi_bbox = draw.multiline_textbbox((0,0), text_str, font=font, spacing=spacing_for_multiline)
    else:
        print("Warning: multiline_textbbox not found (Pillow < 9.2.0). Using manual calculation for block dimensions.")
        min_bx, min_by = float('inf'), float('inf')
        max_br, max_bb = float('-inf'), float('-inf')
        temp_y = 0
        num_lines = len(years_list)
        for i, year_str_val in enumerate(years_list):
            line_bbox = draw.textbbox((0, temp_y), str(year_str_val), font=font, anchor="lt")
            min_bx = min(min_bx, line_bbox[0])
            min_by = min(min_by, line_bbox[1])
            max_br = max(max_br, line_bbox[2])
            max_bb = max(max_bb, line_bbox[3])
            if i < num_lines -1:
                temp_y += single_line_render_height
            else:
                temp_y += single_line_actual_height
        multi_bbox = (min_bx, min_by, max_br, max_bb)

    text_block_width = multi_bbox[2] - multi_bbox[0]
    text_block_height = multi_bbox[3] - multi_bbox[1]

    img_width = text_block_width + padding_internal * 2
    img_height = text_block_height + padding_internal * 2

    full_text_img = Image.new("RGBA", (img_width, img_height), (0,0,0,0))
    draw_on_full = ImageDraw.Draw(full_text_img)

    draw_x = padding_internal - multi_bbox[0]
    draw_y = padding_internal - multi_bbox[1]

    draw_on_full.multiline_text(
        (draw_x, draw_y),
        text_str,
        font=font,
        fill=text_color,
        spacing=spacing_for_multiline,
        align="center"
    )
    # Return the padding used as well, or ensure main uses the same value
    return full_text_img, text_block_height, single_line_render_height


def create_feathered_mask(frame_w, frame_h, visible_strip_h, feather_px):
    mask = np.zeros((frame_h, frame_w), dtype=np.uint8)
    center_y = frame_h // 2
    strip_top = center_y - visible_strip_h // 2
    strip_bottom = center_y + visible_strip_h // 2
    cv2.rectangle(mask, (0, strip_top), (frame_w, strip_bottom), 255, -1)
    blur_ksize = feather_px * 2 + 1
    feathered_mask = cv2.GaussianBlur(mask, (blur_ksize, blur_ksize), 0)
    return feathered_mask

def main():
    # This 'padding' value must match the 'padding_internal' in create_multi_year_text_image
    # if it's used to interpret the structure of full_text_pil.
    padding = 20 

    start_year, end_year = get_user_years()
    years = list(range(start_year, end_year + 1))

    if not os.path.exists(FONT_PATH):
        print(f"ERROR: Font file not found at {FONT_PATH}")
        sys.exit(1)

    target_font_pixel_height = int(FRAME_HEIGHT * MASK_VISIBLE_HEIGHT_FACTOR * 0.75)
    font_size_candidate = target_font_pixel_height
    
    try:
        font = ImageFont.truetype(FONT_PATH, size=font_size_candidate)
        _d_img = Image.new("RGBA", (1,1)); _d_draw = ImageDraw.Draw(_d_img)
        _s_bbox = _d_draw.textbbox((0,0), "2000", font=font, anchor="lt")
        _s_actual_h = _s_bbox[3] - _s_bbox[1]
        if _s_actual_h > 0 and abs(_s_actual_h - target_font_pixel_height) > target_font_pixel_height * 0.05:
            font_size_candidate = int(font_size_candidate * (target_font_pixel_height / _s_actual_h))
            font = ImageFont.truetype(FONT_PATH, size=font_size_candidate)
            _s_bbox = _d_draw.textbbox((0,0), "2000", font=font, anchor="lt")
            _s_actual_h = _s_bbox[3] - _s_bbox[1]
            print(f"Adjusted font size to {font_size_candidate} for target line height ~{target_font_pixel_height} (actual: {_s_actual_h})")
        else:
            print(f"Initial font size {font_size_candidate} suitable for target line height ~{target_font_pixel_height} (actual: {_s_actual_h})")

    except IOError:
        print(f"ERROR: Could not load font {FONT_PATH}.")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading/adjusting font (size {font_size_candidate}): {e}. Trying a default size.")
        try:
            font = ImageFont.truetype(FONT_PATH, size=int(FRAME_HEIGHT * 0.15))
            _d_img = Image.new("RGBA", (1,1)); _d_draw = ImageDraw.Draw(_d_img)
            _s_bbox = _d_draw.textbbox((0,0), "2000", font=font, anchor="lt")
            _s_actual_h = _s_bbox[3] - _s_bbox[1]
        except:
            print("Could not load font even with default size. Exiting.")
            sys.exit(1)

    print("Rendering full text block...")
    full_text_pil, text_block_rendered_height, single_line_render_h_incl_spacing = create_multi_year_text_image(
        years, font, TEXT_COLOR_PIL
    )
    # full_text_pil.save("debug_full_text.png")

    full_text_bgra_cv = cv2.cvtColor(np.array(full_text_pil), cv2.COLOR_RGBA2BGRA)

    video_center_y = FRAME_HEIGHT / 2
    
    start_scroll_y_offset_pil_top = video_center_y - (padding + _s_actual_h / 2)
    end_scroll_y_offset_pil_top = video_center_y - (padding + text_block_rendered_height - _s_actual_h / 2)

    mask_visible_actual_h = int(FRAME_HEIGHT * MASK_VISIBLE_HEIGHT_FACTOR)
    feathered_mask_cv = create_feathered_mask(FRAME_WIDTH, FRAME_HEIGHT, mask_visible_actual_h, FEATHER_AMOUNT_PIXELS)
    
    feathered_mask_normalized = feathered_mask_cv.astype(np.float32) / 255.0
    feathered_mask_normalized = feathered_mask_normalized[:, :, np.newaxis]

    output_path = os.path.join(OUTPUT_FOLDER, OUTPUT_FILENAME)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(output_path, fourcc, FPS, (FRAME_WIDTH, FRAME_HEIGHT))

    if not video_writer.isOpened():
        print(f"ERROR: Could not open video writer for {output_path}")
        sys.exit(1)

    num_total_frames = int(ANIMATION_DURATION_SECONDS * FPS)
    print(f"Generating {num_total_frames} frames for {ANIMATION_DURATION_SECONDS}s animation...")

    for frame_idx in range(num_total_frames):
        progress = frame_idx / (num_total_frames - 1) if num_total_frames > 1 else 0
        eased_progress = ease_in_out_cubic(progress)

        current_y_pil_top = start_scroll_y_offset_pil_top + (end_scroll_y_offset_pil_top - start_scroll_y_offset_pil_top) * eased_progress
        current_y_pil_top = int(round(current_y_pil_top))

        final_frame_bgr = np.full((FRAME_HEIGHT, FRAME_WIDTH, 3), BACKGROUND_COLOR_CV, dtype=np.uint8)
        temp_scrolled_text_canvas_bgra = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 4), dtype=np.uint8)

        text_img_h, text_img_w = full_text_bgra_cv.shape[:2]
        
        dst_x_offset_canvas = (FRAME_WIDTH - text_img_w) // 2
        
        src_y1_text_img = 0
        src_y2_text_img = text_img_h
        dst_y1_canvas = current_y_pil_top
        dst_y2_canvas = current_y_pil_top + text_img_h

        eff_dst_y1 = max(0, dst_y1_canvas)
        eff_dst_y2 = min(FRAME_HEIGHT, dst_y2_canvas)
        
        eff_src_y1_text_img = src_y1_text_img + (eff_dst_y1 - dst_y1_canvas)
        eff_src_y2_text_img = src_y2_text_img - (dst_y2_canvas - eff_dst_y2)
        
        src_x1_text_img = 0
        src_x2_text_img = text_img_w
        dst_x1_canvas = dst_x_offset_canvas
        dst_x2_canvas = dst_x_offset_canvas + text_img_w

        eff_dst_x1 = max(0, dst_x1_canvas)
        eff_dst_x2 = min(FRAME_WIDTH, dst_x2_canvas)

        eff_src_x1_text_img = src_x1_text_img + (eff_dst_x1 - dst_x1_canvas)
        eff_src_x2_text_img = src_x2_text_img - (dst_x2_canvas - eff_dst_x2)

        if eff_dst_y2 > eff_dst_y1 and eff_dst_x2 > eff_dst_x1 and \
           eff_src_y2_text_img > eff_src_y1_text_img and eff_src_x2_text_img > eff_src_x1_text_img:
            
            source_slice = full_text_bgra_cv[eff_src_y1_text_img:eff_src_y2_text_img, eff_src_x1_text_img:eff_src_x2_text_img]
            if source_slice.size > 0:
                temp_scrolled_text_canvas_bgra[eff_dst_y1:eff_dst_y2, eff_dst_x1:eff_dst_x2] = source_slice
        
        scrolled_b = temp_scrolled_text_canvas_bgra[:,:,0]
        scrolled_g = temp_scrolled_text_canvas_bgra[:,:,1]
        scrolled_r = temp_scrolled_text_canvas_bgra[:,:,2]
        scrolled_alpha = temp_scrolled_text_canvas_bgra[:,:,3].astype(np.float32) / 255.0

        combined_alpha = scrolled_alpha * feathered_mask_normalized[:,:,0]
        
        final_frame_bgr[:,:,0] = final_frame_bgr[:,:,0] * (1 - combined_alpha) + scrolled_b * combined_alpha
        final_frame_bgr[:,:,1] = final_frame_bgr[:,:,1] * (1 - combined_alpha) + scrolled_g * combined_alpha
        final_frame_bgr[:,:,2] = final_frame_bgr[:,:,2] * (1 - combined_alpha) + scrolled_r * combined_alpha
        
        video_writer.write(final_frame_bgr)

        if frame_idx % (FPS // 2) == 0:
            print(f"  Frame {frame_idx+1}/{num_total_frames} ({(progress*100):.1f}%)")

    video_writer.release()
    print(f"Animation saved to {output_path}")

if __name__ == "__main__":
    try:
        from packaging.version import parse as parse_version
    except ImportError:
        print("ERROR: 'packaging' library not found. Please install it: pip install packaging")
        sys.exit(1)
    main()
