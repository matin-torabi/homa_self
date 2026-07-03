import asyncio
from telethon import events
from telethon.errors import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from utils import db_execute
from config import supabase

SETTINGS_TABLE = "forced_membership_settings"
CHANNELS_TABLE = "forced_membership_channels"

_my_id_cache = {}

async def _get_my_id(client):
    key = id(client)
    if key not in _my_id_cache:
        me = await client.get_me()
        _my_id_cache[key] = me.id
    return _my_id_cache[key]

# ---------------- توابع دیتابیس (Supabase) ----------------

async def _get_enabled(user_id: int) -> bool:
    query = supabase.table(SETTINGS_TABLE).select("enabled").eq("user_id", user_id).limit(1)
    res = await db_execute(query)
    return bool(res.data[0].get("enabled", False)) if res.data else False

async def _set_enabled(user_id: int, enabled: bool):
    query = supabase.table(SETTINGS_TABLE).upsert({"user_id": user_id, "enabled": enabled})
    await db_execute(query)

async def _add_channel(user_id: int, channel: str):
    query = supabase.table(CHANNELS_TABLE).upsert({"user_id": user_id, "channel": channel})
    await db_execute(query)

async def _remove_channel(user_id: int, channel: str):
    query = supabase.table(CHANNELS_TABLE).delete().eq("user_id", user_id).eq("channel", channel)
    await db_execute(query)

async def _list_channels(user_id: int):
    query = supabase.table(CHANNELS_TABLE).select("channel").eq("user_id", user_id)
    res = await db_execute(query)
    return [row["channel"] for row in res.data] if res.data else []

async def _clear_channels(user_id: int):
    query = supabase.table(CHANNELS_TABLE).delete().eq("user_id", user_id)
    await db_execute(query)

# ---------------- توابع کمکی ----------------

def _normalize_channel(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("https://t.me/"):
        raw = raw.replace("https://t.me/", "")
    if not raw.startswith("@"):
        raw = "@" + raw
    return raw

async def _is_member(client, channel: str, user) -> bool:
    try:
        entity = await client.get_entity(channel)
        await client(GetParticipantRequest(entity, user))
        return True
    except UserNotParticipantError:
        return False
    except Exception:
        return True

# ---------------- هندلر اصلی ----------------

def forced_membership_handler(client):
    """ثبت هندلرهای عضویت اجباری"""

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*تنظیم عضویت\s+(\S+)$"))
    async def _set_channel(event):
        channel = _normalize_channel(event.pattern_match.group(1))
        user_id = await _get_my_id(client)
        await _add_channel(user_id, channel)
        await event.edit(f"✅ کانال {channel} به لیست اضافه شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*حذف عضویت\s+(\S+)$"))
    async def _del_channel(event):
        channel = _normalize_channel(event.pattern_match.group(1))
        user_id = await _get_my_id(client)
        await _remove_channel(user_id, channel)
        await event.edit(f"🗑 کانال {channel} حذف شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*لیست عضویت اجباری$"))
    async def _list_cmd(event):
        user_id = await _get_my_id(client)
        channels = await _list_channels(user_id)
        if not channels:
            await event.edit("📭 لیست خالی است.")
            return
        await event.edit(f"📋 لیست عضویت:\n" + "\n".join(f"➖ {c}" for c in channels))

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*پاکسازی عضویت اجباری$"))
    async def _clear_cmd(event):
        user_id = await _get_my_id(client)
        await _clear_channels(user_id)
        await event.edit("🧹 لیست پاک شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*عضویت اجباری (روشن|خاموش)$"))
    async def _toggle_cmd(event):
        state = event.pattern_match.group(1) == "روشن"
        user_id = await _get_my_id(client)
        await _set_enabled(user_id, state)
        await event.edit(f"✅ عضویت اجباری {'فعال' if state else 'غیرفعال'} شد.")

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def _check_membership(event):
        user_id = await _get_my_id(client)
        if not await _get_enabled(user_id): return
        
        channels = await _list_channels(user_id)
        if not channels: return

        sender = await event.get_sender()
        if not sender or sender.bot: return

        missing = [ch for ch in channels if not await _is_member(client, ch, sender)]
        
        if missing:
            try: await event.delete()
            except: pass
            await event.respond("⚠️ برای ارسال پیام باید عضو کانال‌های زیر باشی:\n" + "\n".join(f"➖ {c}" for c in missing))