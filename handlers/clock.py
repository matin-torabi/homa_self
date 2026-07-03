# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime, timedelta
from telethon import events, functions, types
from telethon.errors import FloodWaitError, RPCError, MessageNotModifiedError
from utils import db_execute  # ایمپورت تابع مدیریت ترد

# ایمپورت اتصال سوپابیس از کانفیگ اصلی پروژه‌تان
from config import supabase  

UPDATE_INTERVAL = 60   # ثانیه
IDLE_SLEEP = 10        # ثانیه

CLOCK_EMOJIS = [
    "🕛", "🕧", "🕐", "🕜", "🕑", "🕝", "🕒", "🕞", "🕓", "🕟",
    "🕔", "🕠", "🕕", "🕡", "🕖", "🕢", "🕗", "🕣", "🕘", "🕤",
    "🕙", "🕥", "🕚", "🕦",
]

def _digit_map(chars: str) -> dict:
    return dict(zip("0123456789", chars))

FONTS = {
    1:  {**_digit_map("0123456789"), ":": ":"},
    2:  {**_digit_map("０１２３４５６７８９"), ":": "："},
    3:  {**_digit_map("𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"), ":": ":"}, # 👈 اصلاح شد: فونت بولد ریاضی جایگزین متن اشتباه قبلی شد
    4:  {**_digit_map("𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"), ":": ":"},
    5:  {**_digit_map("𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"), ":": ":"},
    6:  {**_digit_map("𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"), ":": ":"},
    7:  {**_digit_map("⁰¹²³⁴⁵⁶⁷⁸⁹"), ":": "˸"},
    8:  {**_digit_map("₀₁₂₃₄₅₆₇₈₉"), ":": "˸"},
    9:  {**_digit_map("⓪①②③④⑤⑥⑦⑧⑨"), ":": "："},
    10: {**_digit_map("⓿❶❷❸❹❺❻❼❽❾"), ":": "："},
}

# 📑 نسخه اصلاح‌شده بدون استفاده از رنج‌های نامعتبر یونیکد جهت جلوگیری از ارور موتور پایتون
CLOCK_CLEAN_PATTERN = r"\s*[\d０-９建𝟎-𝟗𝟘-𝟛𝟜-𝟡𝟬-𝟵𝟶-𝟿⁰⁹₀₉⓪①②③④⑤⑥⑦⑧⑨⓿❶❷❸❹❺❻❼❽❾]{2}[:：˸][\d０-９建𝟎-𝟗𝟘-𝟛𝟜-𝟡𝟬-𝟵𝟶-𝟿⁰⁹₀₉⓪①②③④⑤⑥⑦⑧⑨⓿❶❷❸❹❺❻❼❽❾]{2}\s*"

def render_clock(font_no: int) -> str:
    font = FONTS.get(font_no, FONTS[1])
    # حل سازگاری با ویندوز و لینوکس بدون کرش تایم‌زون
    iran_time = datetime.utcnow() + timedelta(hours=3, minutes=30)
    raw = iran_time.strftime("%H:%M")
    return "".join(font.get(ch, ch) for ch in raw)

# ---------------------------------------------------------------------------
# توابع مدیریت دیتابیس سوپابیس
# ---------------------------------------------------------------------------
async def db_get_settings(user_id: int) -> dict:
    try:
        query = supabase.table("user_clocks").select("*").eq("user_id", user_id)
        res = await db_execute(query)
        if res.data:
            return res.data[0]
        
        default = {
            "user_id": user_id, "bio_clock": False, "name_clock": False,
            "premium_clock": False, "font": 1, "base_bio": "", "base_last_name": ""
        }
        insert_query = supabase.table("user_clocks").insert(default)
        await db_execute(insert_query)
        return default
    except Exception as e:
        print(f"⚠️ DB Error get settings for {user_id}: {e}")
        return None

async def db_update_settings(user_id: int, **kwargs):
    try:
        query = supabase.table("user_clocks").update(kwargs).eq("user_id", user_id)
        await db_execute(query)
    except Exception as e:
        print(f"⚠️ DB Error update settings for {user_id}: {e}")

_emoji_doc_cache = {}

async def _get_emoji_document_id(client, emoji_char: str):
    if emoji_char in _emoji_doc_cache:
        return _emoji_doc_cache[emoji_char]
    try:
        result = await client(functions.messages.GetStickerSetRequest(
            stickerset=types.InputStickerSetShortName(short_name="AnimatedEmojies"), hash=0
        ))
        for doc in result.documents:
            alt = next((attr.alt for attr in doc.attributes if isinstance(attr, types.DocumentAttributeSticker)), "")
            if alt == emoji_char:
                _emoji_doc_cache[emoji_char] = doc.id
                return doc.id
    except Exception: pass
    return None

# ---------------------------------------------------------------------------
# حلقه اصلی آپدیت ساعت کلاینت
# ---------------------------------------------------------------------------
async def _clock_loop(client, user_id: int):
    while True:
        try:
            settings = await db_get_settings(user_id)
            if not settings:
                await asyncio.sleep(IDLE_SLEEP)
                continue

            any_active = settings["bio_clock"] or settings["name_clock"] or settings["premium_clock"]
            if not any_active:
                await asyncio.sleep(IDLE_SLEEP)
                continue

            clock_str = render_clock(settings["font"])

            # --- ساعت بیو ---
            if settings["bio_clock"]:
                base_bio = settings.get("base_bio") or ""
                new_about = f"{base_bio} {clock_str}".strip() if base_bio else clock_str
                try:
                    await client(functions.account.UpdateProfileRequest(about=new_about[:70]))
                except FloodWaitError as e: await asyncio.sleep(e.seconds)
                except RPCError: pass

            # --- ساعت نام ---
            if settings["name_clock"]:
                first_name_clean = settings.get("base_last_name") or "User" 
                try:
                    await client(functions.account.UpdateProfileRequest(
                        first_name=first_name_clean[:64],
                        last_name=clock_str
                    ))
                except FloodWaitError as e: await asyncio.sleep(e.seconds)
                except RPCError: pass

            # --- ساعت پریمیوم ---
            if settings["premium_clock"]:
                try:
                    iran_time = datetime.utcnow() + timedelta(hours=3, minutes=30)
                    idx = (iran_time.hour % 12) * 2 + (1 if iran_time.minute >= 30 else 0)
                    emoji = CLOCK_EMOJIS[idx]
                    doc_id = await _get_emoji_document_id(client, emoji)
                    if doc_id:
                        await client(functions.account.UpdateEmojiStatusRequest(
                            emoji_status=types.EmojiStatus(document_id=doc_id)
                        ))
                except RPCError: pass

        except Exception as e:
            print(f"⚠️ Critical loop error for user {user_id}: {e}")
        
        await asyncio.sleep(UPDATE_INTERVAL)


# ---------------------------------------------------------------------------
# تابع اصلی ریجستر ساعت
# ---------------------------------------------------------------------------
def register_clock(client):
    user_info = {"id": None}

    async def init_client_and_start_loop():
        try:
            me = await client.get_me()
            if me:
                user_info["id"] = me.id
                asyncio.create_task(_clock_loop(client, me.id))
        except Exception as e:
            print(f"⚠️ Error initializing clock user: {e}")

    client.loop.create_task(init_client_and_start_loop())

    pattern_bio = r"^[*.]ساعت\s+بیو\s+(روشن|خاموش)$"
    pattern_name = r"^[*.]ساعت\s+نام\s+(روشن|خاموش)$"
    pattern_premium = r"^[*.]ساعت\s+پریمیوم\s+(روشن|خاموش)$"
    pattern_font = r"^[*.]فونت\s+(\d{1,2})$"
    pattern_status = r"^[*.]وضعیت\s+ساعت$"


    @client.on(events.NewMessage(outgoing=True, pattern=pattern_bio))
    async def _bio_handler(event):
        import re
        u_id = user_info["id"] or event.sender_id
        state = event.pattern_match.group(1) == "روشن"
        
        if state:
            me = await client.get_me()
            full = await client(functions.users.GetFullUserRequest(me.id))
            current_bio = full.full_user.about or ""
            
            clean_bio = re.sub(CLOCK_CLEAN_PATTERN, "", current_bio).strip()
            await db_update_settings(u_id, base_bio=clean_bio, bio_clock=True)
            
            # ⚡ آپدیت آنی: منتظر لوپ نمون و همین الان ساعت رو ست کن!
            s = await db_get_settings(u_id)
            clock_str = render_clock(s.get("font", 1))
            new_about = f"{clean_bio} {clock_str}".strip() if clean_bio else clock_str
            try:
                await client(functions.account.UpdateProfileRequest(about=new_about[:70]))
            except: pass
        else:
            await db_update_settings(u_id, bio_clock=False)
            try:
                s = await db_get_settings(u_id)
                await client(functions.account.UpdateProfileRequest(about=s.get("base_bio", "")[:70]))
            except: pass
            
        try:
            await event.edit(f"✅ ساعت بیو {'فعال' if state else 'غیرفعال'} شد.")
        except (MessageNotModifiedError, Exception):
            pass

    @client.on(events.NewMessage(outgoing=True, pattern=pattern_name))
    async def _name_handler(event):
        import re
        u_id = user_info["id"] or event.sender_id
        state = event.pattern_match.group(1) == "روشن"
        
        if state:
            me = await client.get_me()
            current_first = me.first_name or ""
            
            clean_first = re.sub(CLOCK_CLEAN_PATTERN, "", current_first).strip()
            if not clean_first: 
                clean_first = "User"
                
            await db_update_settings(u_id, base_last_name=clean_first, name_clock=True)
            
            # ⚡ آپدیت آنی: منتظر لوپ نمون و همین الان اسم رو تغییر بده!
            s = await db_get_settings(u_id)
            clock_str = render_clock(s.get("font", 1))
            try:
                await client(functions.account.UpdateProfileRequest(
                    first_name=clean_first[:64],
                    last_name=clock_str
                ))
            except: pass
        else:
            await db_update_settings(u_id, name_clock=False)
            try:
                s = await db_get_settings(u_id)
                orig_name = s.get("base_last_name", "User")
                await client(functions.account.UpdateProfileRequest(first_name=orig_name[:64], last_name=""))
            except: pass
            
        try:
            await event.edit(f"✅ ساعت نام {'فعال' if state else 'غیرفعال'} شد.")
        except (MessageNotModifiedError, Exception):
            pass

    @client.on(events.NewMessage(outgoing=True, pattern=pattern_premium))
    async def _premium_handler(event):
        u_id = user_info["id"] or event.sender_id
        state = event.pattern_match.group(1) == "روشن"
        me = await client.get_me()
        if state and not getattr(me, "premium", False):
            await event.edit("⛔ این قابلیت نیازمند اکانت پریمیوم است.")
            return
        await db_update_settings(u_id, premium_clock=state)
        if not state:
            try:
                await client(functions.account.UpdateEmojiStatusRequest(emoji_status=types.EmojiStatusEmpty()))
            except: pass
        try:
            await event.edit(f"✅ ساعت پریمیوم {'فعال' if state else 'غیرفعال'} شد.")
        except (MessageNotModifiedError, Exception):
            pass

    @client.on(events.NewMessage(outgoing=True, pattern=pattern_font))
    async def _font_handler(event):
        u_id = user_info["id"] or event.sender_id
        num = int(event.pattern_match.group(1))
        if num not in FONTS:
            await event.edit("⛔ فونت نامعتبر است (۱ تا ۱۰).")
            return
        await db_update_settings(u_id, font=num)
        try:
            await event.edit(f"✅ فونت روی {num} تنظیم شد.\n`{render_clock(num)}`")
        except (MessageNotModifiedError, Exception):
            pass

    @client.on(events.NewMessage(outgoing=True, pattern=pattern_status))
    async def _status_handler(event):
        u_id = user_info["id"] or event.sender_id
        s = await db_get_settings(u_id)
        txt = (
            "📋 وضعیت ساعت شما:\n\n"
            f"ساعت بیو: {'🟢 روشن' if s['bio_clock'] else '🔴 خاموش'}\n"
            f"ساعت نام: {'🟢 روشن' if s['name_clock'] else '🔴 خاموش'}\n"
            f"ساعت پریمیوم: {'🟢 روشن' if s['premium_clock'] else '🔴 خاموش'}\n"
            f"فونت: {s['font']}  ({render_clock(s['font'])})"
        )
        try:
            await event.edit(txt)
        except (MessageNotModifiedError, Exception):
            pass

    return client