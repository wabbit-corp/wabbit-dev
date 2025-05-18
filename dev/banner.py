import os
from PIL import Image, ImageDraw, ImageFont, ImageColor


def get_text_dimensions(font, text):
    """
    Measure text size using the old getmask-based approach,
    which works in older PIL/Pillow versions.
    """
    if not text:
        return 0, 0
    mask = font.getmask(text)
    return mask.size  # returns (width, height)


def prepare_icon(icon_path, target_size, corner_radius_factor=0.15):
    """
    Open the icon image, resize it to fit within target_size while maintaining aspect ratio,
    and round its corners, preserving original alpha within the rounded shape.
    :param icon_path: Path to the icon image.
    :param target_size: The size the largest dimension of the icon should be scaled to.
    :param corner_radius_factor: Factor of the smaller dimension of the resized icon to use for corner radius.
    :return: Processed icon as an RGBA PIL Image.
    """
    icon = Image.open(icon_path)
    icon = icon.convert("RGBA")  # Ensure icon has an alpha channel

    original_width, original_height = icon.size
    aspect_ratio = original_width / original_height

    # Calculate new dimensions to fit within target_size, preserving aspect ratio
    if original_width > original_height:
        new_width = target_size
        new_height = int(target_size / aspect_ratio)
    else:
        new_height = target_size
        new_width = int(target_size * aspect_ratio)

    # Ensure dimensions are at least 1 pixel
    new_width = max(1, new_width)
    new_height = max(1, new_height)

    # Resize the icon using high-quality downsampling
    icon_resized = icon.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Calculate corner radius based on the smaller dimension of the resized icon
    radius = int(min(new_width, new_height) * corner_radius_factor)

    if radius <= 0:  # No rounding if too small, return the resized icon as is
        return icon_resized

    # Create a mask for rounded corners ('L' mode for grayscale mask)
    corner_mask = Image.new("L", (new_width, new_height), 0)
    draw = ImageDraw.Draw(corner_mask)

    # Draw the rounded rectangle on the mask.
    # Pieslices for corners and rectangles for the body.
    draw.pieslice((0, 0, 2 * radius, 2 * radius), 180, 270, fill=255)  # Top-left
    draw.pieslice(
        (new_width - 2 * radius, 0, new_width, 2 * radius), 270, 360, fill=255
    )  # Top-right
    draw.pieslice(
        (0, new_height - 2 * radius, 2 * radius, new_height), 90, 180, fill=255
    )  # Bottom-left
    draw.pieslice(
        (new_width - 2 * radius, new_height - 2 * radius, new_width, new_height),
        0,
        90,
        fill=255,
    )  # Bottom-right

    # Fill in the connecting rectangles
    draw.rectangle(
        (radius, 0, new_width - radius, new_height), fill=255
    )  # Vertical body
    draw.rectangle(
        (0, radius, new_width, new_height - radius), fill=255
    )  # Horizontal body

    # Create a fully transparent background of the same size as the resized icon
    transparent_background = Image.new("RGBA", icon_resized.size, (0, 0, 0, 0))

    # Composite the original resized icon onto the transparent background.
    # The 'corner_mask' dictates the shape:
    # - Where 'corner_mask' is white (255), pixels from 'icon_resized' (with their original alpha) are used.
    # - Where 'corner_mask' is black (0), pixels from 'transparent_background' are used (i.e., fully transparent).
    rounded_icon_with_original_alpha = Image.composite(
        icon_resized, transparent_background, corner_mask
    )

    return rounded_icon_with_original_alpha


def create_banner(
    image_path,
    main_text,
    subtitle_text: str | None = "",
    background_color="black",  # Default background for the banner itself
    font_path="CooperHewitt-Light.otf",  # Ensure this font is available
    output_path="banner_output.png",
    icon_target_size=300,  # Max dimension for the icon
    font_size=50,
    subtitle_font_size: int | None = 30,
    text_color="white",
    padding=50,
    space_between_img_text_factor=0.5,  # Factor of padding for space
):
    """
    Create a banner that places an image on the left (or right) side
    and text(s) next to it. By default, the banner background is black,
    and we download & use an Open Sans TTF font from Google Fonts.

    :param image_path: Path to the input PNG.
    :param main_text: The main heading text to display.
    :param subtitle_text: An optional subtitle below the main text.
    :param background_color: The background color (e.g. 'black').
    :param font_url: Where to download the font from, if needed.
    :param output_path: Output filename for the banner.
    :param font_size: Font size for main text.
    :param subtitle_font_size: Font size for subtitle.
    :param padding: Horizontal/vertical padding around texts.
    """
    # 1. Download (if needed) and load the font
    # font_path = download_font(font_url, "banner_font.ttf")
    main_font = ImageFont.truetype(font_path, font_size)
    if subtitle_font_size and subtitle_text:
        subtitle_font = ImageFont.truetype(font_path, subtitle_font_size)
    else:
        subtitle_font = None

    # Resolve the background color as an RGBA tuple
    background_color = (
        ImageColor.getrgb(background_color) + (255,)
        if isinstance(background_color, str)
        else background_color
    )

    # 2. Load the original PNG
    img = prepare_icon(image_path, target_size=300)
    img_width, img_height = img.size

    # 3. Compute text sizes
    main_text_width, main_text_height = get_text_dimensions(main_font, main_text)

    # Calculate width of a space character to put between image and text
    # Using 'm' as a typical wide character for spacing, or just a fixed portion of padding
    space_width = int(padding * space_between_img_text_factor)

    subtitle_text_width, subtitle_text_height = 0, 0
    if subtitle_text and subtitle_font:
        subtitle_text_width, subtitle_text_height = get_text_dimensions(
            subtitle_font, subtitle_text
        )

    # 4. Calculate total banner width & height
    text_block_width = max(main_text_width, subtitle_text_width)
    text_block_height = main_text_height
    if subtitle_text and subtitle_font:  # Add subtitle height and a small gap
        text_block_height += int(subtitle_font_size * 0.2) + subtitle_text_height

    banner_width = padding + img_width + space_width + text_block_width + padding
    # Height considers padding around the taller of the two: image or text block
    banner_height = max(img_height, text_block_height) + 2 * padding

    # 5. Determine banner background color
    if isinstance(background_color, str):
        if background_color.lower() == "transparent":
            final_banner_bg_color = (0, 0, 0, 0)
        else:
            try:
                # For named colors, getrgb returns RGB. We add Alpha for RGBA.
                final_banner_bg_color = ImageColor.getrgb(background_color) + (255,)
            except ValueError:
                print(
                    f"Warning: Unknown background color string '{background_color}'. Defaulting to transparent."
                )
                final_banner_bg_color = (0, 0, 0, 0)  # Fallback to transparent
    elif (
        isinstance(background_color, tuple) and len(background_color) == 3
    ):  # RGB tuple
        final_banner_bg_color = background_color + (255,)  # Add opaque alpha
    elif (
        isinstance(background_color, tuple) and len(background_color) == 4
    ):  # RGBA tuple
        final_banner_bg_color = background_color
    else:
        print(f"Warning: Invalid background_color format. Defaulting to transparent.")
        final_banner_bg_color = (0, 0, 0, 0)  # Fallback

    # Create the blank banner
    banner = Image.new(
        "RGBA", (banner_width, banner_height), color=final_banner_bg_color
    )
    draw = ImageDraw.Draw(banner)

    # 6. Paste the image into the banner (vertically centered)
    img_y_position = (banner_height - img_height) // 2
    # Paste with alpha compositing using the image's own alpha channel as the mask
    banner.paste(img, (padding, img_y_position), mask=img)

    # 7. Draw text (text block vertically centered)
    text_color_rgb = ImageColor.getrgb(text_color)  # Ensure text_color is RGB

    text_start_x = padding + img_width + space_width
    text_block_y_start = (banner_height - text_block_height) // 2

    # Draw the main text (horizontally centered within its part of the text_block_width if desired, or left-aligned)
    # For this layout, usually left-aligning text in its block is cleaner.
    # main_text_x = text_start_x + (text_block_width - main_text_width) // 2 # Centered in text block
    main_text_x = text_start_x  # Left-aligned in text block
    main_text_y = text_block_y_start
    draw.text(
        (main_text_x, main_text_y), main_text, font=main_font, fill=text_color_rgb
    )

    if subtitle_text and subtitle_font:
        # subtitle_text_x = text_start_x + (text_block_width - subtitle_text_width) // 2 # Centered
        subtitle_text_x = text_start_x  # Left-aligned
        subtitle_text_y = (
            main_text_y + main_text_height + int(subtitle_font_size * 0.2)
        )  # Position below main text with a small gap
        draw.text(
            (subtitle_text_x, subtitle_text_y),
            subtitle_text,
            font=subtitle_font,
            fill=text_color_rgb,
        )

    # 8. Save the final banner
    try:
        banner.save(output_path)
        print(f"Banner created and saved to {output_path}")
    except Exception as e:
        print(f"Error saving banner: {e}")


if __name__ == "__main__":
    # Example usage
    # Provide your own local image path and text
    create_banner(
        image_path="banner2.png",  # Replace with your actual PNG path
        main_text="kotlin-data-need",
        subtitle_text=None,
        background_color=(0, 0, 0, 0),
        output_path="my_banner.png",
        font_size=60,
        subtitle_font_size=None,
        padding=40,
    )
