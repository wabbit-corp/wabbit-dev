from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageFont, PngImagePlugin

from dev.banner import create_banner


def _patch_default_font(monkeypatch: pytest.MonkeyPatch) -> None:
    default_font = ImageFont.load_default()

    def fake_truetype(
        _font: str | bytes | Path | None,
        _size: float = 10,
        index: int = 0,
        encoding: str = "",
        layout_engine: ImageFont.Layout | None = None,
    ) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        del _font, _size, index, encoding, layout_engine
        return default_font

    monkeypatch.setattr("dev.banner.ImageFont.truetype", fake_truetype)


def _read_rgba_signature(path: Path) -> tuple[tuple[int, int], bytes]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return rgba.size, rgba.tobytes()


def test_create_banner_skips_rewrite_when_existing_png_pixels_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_default_font(monkeypatch)

    icon_path = tmp_path / "icon.png"
    output_path = tmp_path / ".banner.png"

    Image.new("RGBA", (12, 12), (255, 0, 0, 255)).save(icon_path)

    create_banner(
        image_path=icon_path,
        font_path=tmp_path / "unused.ttf",
        main_text="demo",
        subtitle_text=None,
        background_color=(0, 0, 0, 0),
        output_path=output_path,
        icon_target_size=12,
        font_size=12,
        subtitle_font_size=None,
        padding=4,
    )

    initial_bytes = output_path.read_bytes()
    with Image.open(output_path) as existing_banner:
        banner_copy = existing_banner.copy()

    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("generator", "other-tool")
    banner_copy.save(output_path, format="PNG", compress_level=1, pnginfo=pnginfo)
    altered_bytes = output_path.read_bytes()

    assert altered_bytes != initial_bytes

    create_banner(
        image_path=icon_path,
        font_path=tmp_path / "unused.ttf",
        main_text="demo",
        subtitle_text=None,
        background_color=(0, 0, 0, 0),
        output_path=output_path,
        icon_target_size=12,
        font_size=12,
        subtitle_font_size=None,
        padding=4,
    )

    assert output_path.read_bytes() == altered_bytes


def test_create_banner_rewrites_when_rendered_pixels_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_default_font(monkeypatch)

    icon_path = tmp_path / "icon.png"
    output_path = tmp_path / ".banner.png"

    Image.new("RGBA", (12, 12), (255, 0, 0, 255)).save(icon_path)

    create_banner(
        image_path=icon_path,
        font_path=tmp_path / "unused.ttf",
        main_text="demo",
        subtitle_text=None,
        background_color=(0, 0, 0, 0),
        output_path=output_path,
        icon_target_size=12,
        font_size=12,
        subtitle_font_size=None,
        padding=4,
    )
    original_signature = _read_rgba_signature(output_path)

    create_banner(
        image_path=icon_path,
        font_path=tmp_path / "unused.ttf",
        main_text="changed",
        subtitle_text=None,
        background_color=(0, 0, 0, 0),
        output_path=output_path,
        icon_target_size=12,
        font_size=12,
        subtitle_font_size=None,
        padding=4,
    )

    assert _read_rgba_signature(output_path) != original_signature
