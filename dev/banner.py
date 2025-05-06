import os
import requests
from PIL import Image, ImageDraw, ImageFont, ImageColor

def download_font(url, font_name="banner_font.ttf"):
    """
    Utility function to download a TTF font from a URL,
    saving it locally as font_name if it doesn't already exist.
    """
    if not os.path.exists(font_name):
        print(f"Downloading font from {url} ...")
        r = requests.get(url)
        r.raise_for_status()
        with open(font_name, 'wb') as f:
            f.write(r.content)
    return font_name

def measure_text_size(font, text):
    """
    Measure text size using the old getmask-based approach,
    which works in older PIL/Pillow versions.
    """
    if not text:
        return 0, 0
    mask = font.getmask(text)
    return mask.size  # returns (width, height)

def prepare_icon(icon_path, target_size):
    """
    Open the icon image.
    Round the corners of the icon.
    Resize it to the desired size.
    """
    icon = Image.open(icon_path)
    icon = icon.convert("RGBA")
    width = icon.size[0]
    height = icon.size[1]
    max_size = max(width, height)
    size = max_size

    if width > height:
        new_width = target_size
        new_height = int(size * height / width)
    else:
        new_width = int(size * width / height)
        new_height = target_size

    corner_radius = 0.4 * size
    # Create a mask to round the corners
    mask = Image.new("L", icon.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, corner_radius, corner_radius), fill=255)
    draw.ellipse((0, height - corner_radius, corner_radius, height), fill=255)
    draw.ellipse((width - corner_radius, 0, width, corner_radius), fill=255)
    draw.ellipse((width - corner_radius, height - corner_radius, width, height), fill=255)
    draw.rectangle((corner_radius // 2, 0, width - corner_radius // 2, height), fill=255)
    draw.rectangle((0, corner_radius // 2, width, height - corner_radius // 2), fill=255)
    # Round the corners
    icon.putalpha(mask)
    # Resize the icon to the desired size
    icon.thumbnail((new_width, new_height), Image.LANCZOS)
    return icon

def create_banner(
    image_path,
    main_text,
    subtitle_text: str | None="",
    background_color="black",
    font_url="https://github.com/google/fonts/blob/main/apache/opensans/OpenSans-Regular.ttf?raw=true",  # example
    output_path="banner_output.png",
    font_size=50,
    subtitle_font_size: int | None=30,
    padding=50
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
    font_path = 'CooperHewitt-Light.otf'
    main_font = ImageFont.truetype(font_path, font_size)
    if subtitle_font_size and subtitle_text:
        subtitle_font = ImageFont.truetype(font_path, subtitle_font_size)
    else:
        subtitle_font = None

    # Resolve the background color as an RGBA tuple
    background_color = ImageColor.getrgb(background_color) + (255,) if isinstance(background_color, str) else background_color

    # 2. Load the original PNG
    img = prepare_icon(image_path, target_size=300)
    image_background_color = img.getpixel((0, 0))
    # Replace the background color with the desired one
    for x in range(img.width):
        for y in range(img.height):
            if img.getpixel((x, y)) == image_background_color:
                img.putpixel((x, y), background_color)
    img_width, img_height = img.size

    # 3. Compute text sizes using the getmask fallback
    main_text_width, main_text_height = measure_text_size(main_font, main_text)

    space_text_width, _ = measure_text_size(main_font, " ")

    if subtitle_font:
        subtitle_text_width, subtitle_text_height = measure_text_size(subtitle_font, subtitle_text)
    else:
        subtitle_text_width, subtitle_text_height = 0, 0

    # 4. Calculate total banner width & height
    text_block_width = max(main_text_width, subtitle_text_width)
    text_block_height = main_text_height + (subtitle_text_height if subtitle_text else 0)
    banner_width = padding + img_width + space_text_width + text_block_width + padding
    banner_height = max(img_height, padding + text_block_height + padding)

    # 5. Create the blank banner with the chosen background
    banner = Image.new("RGBA", (banner_width, banner_height), color=background_color)

    # 6. Paste the image into the banner on the left side
    # If it is too small, center it vertically
    banner.paste(img, (padding, (banner_height - img_height) // 2))

    # 7. Draw text
    draw = ImageDraw.Draw(banner)

    #    We'll want to center the text block vertically
    text_start_x = padding + img_width + space_text_width
    text_start_y = (banner_height - text_block_height) // 2

    #    Draw the main text (centered horizontally in the text_block_width)
    main_text_x = text_start_x + (text_block_width - main_text_width) // 2
    main_text_y = text_start_y
    draw.text((main_text_x, main_text_y), main_text, font=main_font, fill="white")

    #    Draw the subtitle (if any) below the main text
    if subtitle_text:
        subtitle_text_x = text_start_x + (text_block_width - subtitle_text_width) // 2
        subtitle_text_y = main_text_y + main_text_height
        draw.text((subtitle_text_x, subtitle_text_y), subtitle_text, font=subtitle_font, fill="white")

    # 8. Save the final banner
    banner.save(output_path)
    print(f"Banner created and saved to {output_path}")


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
        padding=40
    )
