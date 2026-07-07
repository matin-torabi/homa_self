import os
import asyncio
import tempfile

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageOps

from telethon import events
from telethon.tl.types import DocumentAttributeSticker, InputStickerSetEmpty

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG = {
    "prefix": "*",
    "command": "اسکرین",

    # ⚠️ مسیر مطلق فونت — دیگه به working directory سرویس/systemd/pm2 وابسته نیست.
    "font_path": os.path.join(_BASE_DIR, "Vazirmatn-SemiBold.ttf"),
    "font_size": 34,
    "name_font_size": 30,

    "bubble_color": (35, 35, 40, 255),     # رنگ پس‌زمینه‌ی کارت
    "text_color": (240, 240, 240, 255),    # رنگ متن پیام
    "name_color": (90, 170, 255, 255),     # رنگ اسم فرستنده

    "min_width": 360,
    "max_width": 760,
    "padding": 40,
    "gap": 20,
    "avatar_size": 90,

    # اندازه‌ی نهایی موردنیاز برای فرمت استیکر تلگرام
    "sticker_max_side": 512,
}


def _make_font(size: int):
    """
    تلاش می‌کنه فونت رو با موتور RAQM بسازه (shaping درست عربی/فارسی از طریق
    HarfBuzz+FriBidi، مستقل از اینکه فونت گلیف presentation-form داشته باشه یا نه).
    اگه سیستم libraqm نصب نداشته باشه، به‌صورت خودکار به روش قدیمی برمی‌گرده
    (که ممکنه حروف جدا نمایش بده — برای رفع کامل، حتماً روی سرور نصب کن:
    `sudo apt-get install -y libraqm0`).
    """
    try:
        font = ImageFont.truetype(CONFIG["font_path"], size, layout_engine=ImageFont.Layout.RAQM)
        # یه تست کوچیک که مطمئن بشیم RAQM واقعاً فعاله (وگرنه در زمان draw ارور میده)
        ImageDraw.Draw(Image.new("RGB", (5, 5))).textlength("آزمایش", font=font, direction="rtl")
        return font, True
    except Exception:
        return ImageFont.truetype(CONFIG["font_path"], size), False


def _shape_fa(text: str) -> str:
    """فقط برای مسیر fallback (بدون RAQM) استفاده می‌شه."""
    return get_display(arabic_reshaper.reshape(text))


def _text_width(draw, text, font, use_raqm):
    if use_raqm:
        return draw.textlength(text, font=font, direction="rtl")
    return draw.textlength(_shape_fa(text), font=font)


def _draw_rtl_text(draw, right_x, y, text, font, fill, use_raqm):
    """متن رو طوری رسم می‌کنه که سمت راستش دقیقاً روی right_x بشینه (راست‌چین)."""
    if use_raqm:
        w = draw.textlength(text, font=font, direction="rtl")
        draw.text((right_x - w, y), text, font=font, fill=fill, direction="rtl")
    else:
        shaped = _shape_fa(text)
        w = draw.textlength(shaped, font=font)
        draw.text((right_x - w, y), shaped, font=font, fill=fill)


def _wrap_text(draw, text, font, max_width, use_raqm):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        w = _text_width(draw, test, font, use_raqm)
        if w <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


async def _build_quote_image(client, sender, text: str) -> str:
    if not os.path.exists(CONFIG["font_path"]):
        raise FileNotFoundError(
            f"فونت پیدا نشد: {CONFIG['font_path']} — یه فونت فارسی .ttf دانلود کن "
            "و مسیرش رو توی CONFIG['font_path'] درست کن."
        )

    font, use_raqm = _make_font(CONFIG["font_size"])
    name_font, _ = _make_font(CONFIG["name_font_size"])
    dummy = ImageDraw.Draw(Image.new("RGBA", (10, 10)))

    max_text_width = (
        CONFIG["max_width"] - CONFIG["padding"] * 2 - CONFIG["avatar_size"] - CONFIG["gap"]
    )
    lines = _wrap_text(dummy, text, font, max_text_width, use_raqm)

    name = getattr(sender, "first_name", None) or getattr(sender, "title", None) or "کاربر"

    # عرض واقعی موردنیاز رو حساب می‌کنیم (کارت رو فقط به اندازه‌ی لازم بزرگ می‌کنیم)
    longest_line = max([_text_width(dummy, l, font, use_raqm) for l in lines], default=0)
    name_w = _text_width(dummy, name, name_font, use_raqm)
    content_w = max(longest_line, name_w)

    bubble_width = int(min(
        CONFIG["max_width"],
        max(CONFIG["min_width"], content_w + CONFIG["avatar_size"] + CONFIG["padding"] * 2 + CONFIG["gap"]),
    ))

    line_height = font.getbbox("سلام")[3] + 14
    name_height = name_font.getbbox("سلام")[3] + 20
    bubble_height = CONFIG["padding"] * 2 + name_height + len(lines) * line_height
    bubble_height = max(bubble_height, CONFIG["avatar_size"] + CONFIG["padding"] * 2)

    img = Image.new("RGBA", (bubble_width, bubble_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(0, 0), (bubble_width, bubble_height)], radius=30, fill=CONFIG["bubble_color"])

    # دانلود و رسم آواتار دایره‌ای
    avatar_path = tempfile.mktemp(suffix=".jpg")
    text_end_x = bubble_width - CONFIG["padding"]
    try:
        downloaded = await client.download_profile_photo(sender, file=avatar_path)
    except Exception:
        downloaded = None

    if downloaded and os.path.exists(downloaded):
        avatar = Image.open(downloaded).convert("RGBA")
        avatar = ImageOps.fit(avatar, (CONFIG["avatar_size"], CONFIG["avatar_size"]))
        mask = Image.new("L", avatar.size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0) + avatar.size, fill=255)
        avatar_x = bubble_width - CONFIG["padding"] - CONFIG["avatar_size"]
        img.paste(avatar, (avatar_x, CONFIG["padding"]), mask)
        os.remove(downloaded)
        text_end_x = avatar_x - CONFIG["gap"]

    # اسم فرستنده (راست‌چین)
    _draw_rtl_text(draw, text_end_x, CONFIG["padding"], name, name_font, CONFIG["name_color"], use_raqm)

    # متن پیام، خط‌به‌خط، راست‌چین
    y = CONFIG["padding"] + name_height
    for line in lines:
        _draw_rtl_text(draw, text_end_x, y, line, font, CONFIG["text_color"], use_raqm)
        y += line_height

    # تبدیل به اندازه‌ی استاندارد استیکر و ذخیره به فرمت webp
    max_side = max(img.size)
    if max_side > CONFIG["sticker_max_side"]:
        scale = CONFIG["sticker_max_side"] / max_side
        img = img.resize((int(img.width * scale), int(img.height * scale)))

    out_path = tempfile.mktemp(suffix=".webp")
    img.save(out_path, "WEBP")
    return out_path


def register_screen_handler(client):
    """
    این تابع رو با کلاینت تلتون خودت صدا بزن:
        register_screen_handler(client)
    """
    prefix = CONFIG["prefix"]
    command = CONFIG["command"]
    pattern = rf'^\{prefix}{command}\s*$'

    @client.on(events.NewMessage(outgoing=True, pattern=pattern))
    async def screen_handler(event):
        if not event.is_reply:
            await event.edit("⚠️ باید روی یه پیام ریپلای کنی و بعد *اسکرین رو بفرستی.")
            await asyncio.sleep(4)
            await event.delete()
            return

        replied = await event.get_reply_message()
        await event.delete()

        if not replied or not replied.text:
            warn = await client.send_message(event.chat_id, "⚠️ فقط پیام‌های متنی قابل تبدیل به استیکرن.")
            await asyncio.sleep(4)
            await warn.delete()
            return

        sender = await replied.get_sender()

        img_path = None
        try:
            img_path = await _build_quote_image(client, sender, replied.text)
            await client.send_file(
                event.chat_id,
                img_path,
                attributes=[DocumentAttributeSticker(alt="📌", stickerset=InputStickerSetEmpty())],
                force_document=False,
            )
        except Exception as e:
            err = await client.send_message(event.chat_id, f"⚠️ خطا در ساخت استیکر: {e}")
            await asyncio.sleep(6)
            await err.delete()
        finally:
            if img_path and os.path.exists(img_path):
                os.remove(img_path)