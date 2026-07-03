import asyncio

from telethon import events
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from telethon.tl.types import Channel
from config import supabase
from utils import db_execute  # اجرای غیرهمزمان کوئری‌های sync سوپابیس در thread pool اختصاصی

TABLE = "autocomment_settings"
DEFAULT_COMMENT_TEXT = "اولین"

# کش id خود اکانت برای هر کلاینت (چون استخراجش async هست)
_my_id_cache = {}


async def _get_my_id(client):
    key = id(client)
    if key not in _my_id_cache:
        me = await client.get_me()
        _my_id_cache[key] = me.id
    return _my_id_cache[key]


async def _get_user_settings(user_id: int):
    try:
        query = supabase.table(TABLE).select("*").eq("user_id", user_id).limit(1)
        res = await db_execute(query)
        row = res.data[0] if res.data else None
    except Exception as e:
        print(f"Error fetching autocomment settings for {user_id}: {e}")
        row = None

    if row is None:
        return {"enabled": False, "comment_text": DEFAULT_COMMENT_TEXT}
    return {
        "enabled": bool(row.get("enabled", False)),
        "comment_text": row.get("comment_text") or DEFAULT_COMMENT_TEXT,
    }


async def _update_user_settings(user_id: int, **updates):
    try:
        payload = {"user_id": user_id, **updates}
        query = supabase.table(TABLE).upsert(payload, on_conflict="user_id")
        await db_execute(query)
    except Exception as e:
        print(f"Error updating autocomment settings for {user_id}: {e}")


def register_autocomment_handler(client):
    """این تابع رو با کلاینت Telethon خودت صدا بزن تا قابلیت کامنت اول فعال بشه."""

    # ---------- دستورات کنترلی ----------

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*کامنت اول روشن$"))
    async def _enable(event):
        user_id = await _get_my_id(client)
        await _update_user_settings(user_id, enabled=True)
        await event.edit("✅ کامنت اول فعال شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*کامنت اول خاموش$"))
    async def _disable(event):
        user_id = await _get_my_id(client)
        await _update_user_settings(user_id, enabled=False)
        await event.edit("⛔️ کامنت اول غیرفعال شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\*متن کامنت\s+(.+)$"))
    async def _set_text(event):
        text = event.pattern_match.group(1).strip()
        user_id = await _get_my_id(client)
        await _update_user_settings(user_id, comment_text=text)
        await event.edit(f"📝 متن کامنت تنظیم شد:\n«{text}»")

    # ---------- پست جدید کانال‌ها ----------

    @client.on(events.NewMessage(incoming=True))
    async def _on_channel_post(event):
        chat = await event.get_chat()

        # فقط کانال‌های broadcast (نه گروه‌ها) رو در نظر بگیر
        if not isinstance(chat, Channel) or chat.megagroup:
            return

        user_id = await _get_my_id(client)
        settings = await _get_user_settings(user_id)
        if not settings.get("enabled"):
            return

        comment_text = settings.get("comment_text") or DEFAULT_COMMENT_TEXT

        try:
            result = await client(GetDiscussionMessageRequest(
                peer=chat,
                msg_id=event.message.id,
            ))
        except Exception:
            # این کانال گروه گفتگوی متصل نداره یا دسترسی نداریم
            return

        if not result.messages:
            return

        discussion_msg = result.messages[0]
        discussion_chat_id = result.chats[0].id if result.chats else None
        if discussion_chat_id is None:
            return

        try:
            await client.send_message(
                discussion_chat_id,
                comment_text,
                reply_to=discussion_msg.id,
            )
        except Exception:
            pass

    return _enable, _disable, _set_text, _on_channel_post