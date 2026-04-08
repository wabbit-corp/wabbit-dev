import logging
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, PngImagePlugin

_LOGGER = logging.getLogger(__name__)


def get_text_dimensions(font: ImageFont.ImageFont | ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    """
    Measure text size using the old getmask-based approach,
    which works in older PIL/Pillow versions.
    """
    if not text:
        return 0, 0
    mask = font.getmask(text)
    width, height = mask.size
    return int(width), int(height)


def _to_rgba(color: str | tuple[int, int, int] | tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if isinstance(color, str):
        if color.lower() == "transparent":
            return 0, 0, 0, 0
        try:
            rgb_or_rgba = ImageColor.getrgb(color)
        except ValueError:
            _LOGGER.warning("Unknown background color string '%s'; defaulting to transparent.", color)
            return 0, 0, 0, 0
        if len(rgb_or_rgba) == 3:
            red, green, blue = rgb_or_rgba
            return red, green, blue, 255
        red, green, blue, alpha = rgb_or_rgba
        return red, green, blue, alpha

    if len(color) == 3:
        return color + (255,)
    return color


def prepare_icon(icon_path: str | Path, target_size: int, corner_radius_factor: float = 0.15) -> Image.Image:
    """
    Open the icon image, resize it to fit within target_size while maintaining aspect ratio,
    and round its corners, preserving original alpha within the rounded shape.
    :param icon_path: Path to the icon image.
    :param target_size: The size the largest dimension of the icon should be scaled to.
    :param corner_radius_factor: Factor of the smaller dimension of the resized icon to use for corner radius.
    :return: Processed icon as an RGBA PIL Image.
    """
    with Image.open(icon_path) as icon_source:
        icon = icon_source.convert("RGBA")  # Ensure icon has an alpha channel

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
    draw.pieslice((new_width - 2 * radius, 0, new_width, 2 * radius), 270, 360, fill=255)  # Top-right
    draw.pieslice((0, new_height - 2 * radius, 2 * radius, new_height), 90, 180, fill=255)  # Bottom-left
    draw.pieslice(
        (new_width - 2 * radius, new_height - 2 * radius, new_width, new_height),
        0,
        90,
        fill=255,
    )  # Bottom-right

    # Fill in the connecting rectangles
    draw.rectangle((radius, 0, new_width - radius, new_height), fill=255)  # Vertical body
    draw.rectangle((0, radius, new_width, new_height - radius), fill=255)  # Horizontal body

    # Create a fully transparent background of the same size as the resized icon
    transparent_background = Image.new("RGBA", icon_resized.size, (0, 0, 0, 0))

    # Composite the original resized icon onto the transparent background.
    # The 'corner_mask' dictates the shape:
    # - Where 'corner_mask' is white (255), pixels from 'icon_resized' (with their original alpha) are used.
    # - Where 'corner_mask' is black (0), pixels from 'transparent_background' are used (i.e., fully transparent).
    rounded_icon_with_original_alpha = Image.composite(icon_resized, transparent_background, corner_mask)

    return rounded_icon_with_original_alpha


def _render_banner(
    image_path: str | Path,
    main_text: str,
    subtitle_text: str | None,
    background_color: str | tuple[int, int, int] | tuple[int, int, int, int],
    font_path: str | Path,
    icon_target_size: int,
    font_size: int,
    subtitle_font_size: int | None,
    text_color: str,
    padding: int,
    space_between_img_text_factor: float,
) -> Image.Image:
    main_font = ImageFont.truetype(str(font_path), font_size)
    if subtitle_font_size and subtitle_text:
        subtitle_font = ImageFont.truetype(str(font_path), subtitle_font_size)
    else:
        subtitle_font = None

    img = prepare_icon(image_path, target_size=icon_target_size)
    img_width, img_height = img.size

    main_text_width, main_text_height = get_text_dimensions(main_font, main_text)
    space_width = int(padding * space_between_img_text_factor)

    subtitle_text_width, subtitle_text_height = 0, 0
    if subtitle_text and subtitle_font:
        subtitle_text_width, subtitle_text_height = get_text_dimensions(subtitle_font, subtitle_text)

    text_block_width = max(main_text_width, subtitle_text_width)
    text_block_height = main_text_height
    if subtitle_text and subtitle_font:
        assert subtitle_font_size is not None
        text_block_height += int(subtitle_font_size * 0.2) + subtitle_text_height

    banner_width = padding + img_width + space_width + text_block_width + padding
    banner_height = max(img_height, text_block_height) + 2 * padding

    final_banner_bg_color = _to_rgba(background_color)
    banner = Image.new("RGBA", (banner_width, banner_height), color=final_banner_bg_color)
    draw = ImageDraw.Draw(banner)

    img_y_position = (banner_height - img_height) // 2
    banner.paste(img, (padding, img_y_position), mask=img)

    text_color_rgb = ImageColor.getrgb(text_color)
    text_start_x = padding + img_width + space_width
    text_block_y_start = (banner_height - text_block_height) // 2

    main_text_x = text_start_x
    main_text_y = text_block_y_start
    draw.text((main_text_x, main_text_y), main_text, font=main_font, fill=text_color_rgb)

    if subtitle_text and subtitle_font:
        subtitle_text_x = text_start_x
        assert subtitle_font_size is not None
        subtitle_text_y = main_text_y + main_text_height + int(subtitle_font_size * 0.2)
        draw.text(
            (subtitle_text_x, subtitle_text_y),
            subtitle_text,
            font=subtitle_font,
            fill=text_color_rgb,
        )

    return banner


def _rgba_signature(image: Image.Image) -> tuple[tuple[int, int], bytes]:
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    return rgba.size, rgba.tobytes()


def _existing_banner_matches(output_path: Path, banner: Image.Image) -> bool:
    if not output_path.is_file():
        return False

    try:
        with Image.open(output_path) as existing_banner:
            return _rgba_signature(existing_banner) == _rgba_signature(banner)
    except OSError:
        _LOGGER.warning("Unable to read existing banner %s; rewriting it.", output_path)
        return False


def _save_banner_png(banner: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    banner.save(
        output_path,
        format="PNG",
        optimize=False,
        compress_level=9,
        pnginfo=PngImagePlugin.PngInfo(),
    )


def create_banner(
    image_path: str | Path,
    main_text: str,
    subtitle_text: str | None = "",
    background_color: str | tuple[int, int, int] | tuple[int, int, int, int] = "black",  # Default banner background
    font_path: str | Path = "CooperHewitt-Light.otf",  # Ensure this font is available
    output_path: str | Path = "banner_output.png",
    icon_target_size: int = 300,  # Max dimension for the icon
    font_size: int = 50,
    subtitle_font_size: int | None = 30,
    text_color: str = "white",
    padding: int = 50,
    space_between_img_text_factor: float = 0.5,  # Factor of padding for space
) -> None:
    """
    Create a banner that places an image on the left and text next to it.
    The banner uses the caller-provided ``font_path`` to render the text.

    :param image_path: Path to the input PNG.
    :param main_text: The main heading text to display.
    :param subtitle_text: An optional subtitle below the main text.
    :param background_color: The background color (e.g. 'black').
    :param font_path: Path to the font file used for rendering text.
    :param output_path: Output filename for the banner.
    :param icon_target_size: Maximum dimension for the icon.
    :param font_size: Font size for main text.
    :param subtitle_font_size: Font size for subtitle.
    :param text_color: Text color for the main text and subtitle.
    :param padding: Horizontal/vertical padding around texts.
    :param space_between_img_text_factor: Spacing factor between the icon and text block.
    """
    banner = _render_banner(
        image_path=image_path,
        main_text=main_text,
        subtitle_text=subtitle_text,
        background_color=background_color,
        font_path=font_path,
        icon_target_size=icon_target_size,
        font_size=font_size,
        subtitle_font_size=subtitle_font_size,
        text_color=text_color,
        padding=padding,
        space_between_img_text_factor=space_between_img_text_factor,
    )
    output = Path(output_path)

    try:
        if _existing_banner_matches(output, banner):
            _LOGGER.debug("Skipping banner rewrite for %s because the RGBA pixels are unchanged.", output)
            return
        _save_banner_png(banner, output)
    except Exception as e:
        _LOGGER.exception("Error saving banner to %s: %s", output, e)
        raise


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
