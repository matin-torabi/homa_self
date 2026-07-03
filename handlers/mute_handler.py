import asyncio
from telethon import events
from telethon.tl.types import User
from utils import db_execute
from config import supabase

# ایمپورت کردن توابع آنلاین سوپابیس از فایل utils

def register_mute_handlers(client):
    """
    مدیریت فوق امنیتی و ایزوله بر پایه سوپابیس (Async)
    """
    
    # متغیرهای داخلی کلاینت
    client.muted_users_list = []
    client.my_own_id = None

    async def _ensure_loaded():
        if client.my_own_id is None:
            me = await client.get_me()
            client.my_own_id = me.id
            # دریافت لیست از دیتابیس به صورت غیرهمزمان
            query = supabase.table("muted_users").select("muted_id").eq("owner_id", client.my_own_id)
            res = await db_execute(query)
            client.muted_users_list = [row["muted_id"] for row in res.data] if res.data else []
        return client.my_own_id

    # هندلر پاک کردن آنی پیام
    @client.on(events.NewMessage(incoming=True))
    async def auto_delete_muted(event):
        await _ensure_loaded()
        if event.sender_id in client.muted_users_list:
            try:
                await event.delete()
            except Exception as e:
                print(f"Error auto-deleting message: {e}")

    # ۱. دستور *سکوت
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\*سکوت$'))
    async def mute_user(event):
        await _ensure_loaded()
        if not event.is_reply:
            return await event.edit("⚠️ روی پیام شخص ریپلای کنید.")
        
        reply_msg = await event.get_reply_message()
        user_id = reply_msg.sender_id
        
        if user_id not in client.muted_users_list:
            query = supabase.table("muted_users").insert({"owner_id": client.my_own_id, "muted_id": user_id})
            await db_execute(query)
            client.muted_users_list.append(user_id)
            await event.edit("🤐 کاربر به لیست سکوت اضافه شد.")

    # ۲. دستور *حذف سکوت
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\*حذف سکوت(?:\s+(\d+))?$'))
    async def unmute_user(event):
        await _ensure_loaded()
        user_id = int(event.pattern_match.group(1)) if event.pattern_match.group(1) else (await event.get_reply_message()).sender_id
        
        if user_id in client.muted_users_list:
            query = supabase.table("muted_users").delete().eq("owner_id", client.my_own_id).eq("muted_id", user_id)
            await db_execute(query)
            client.muted_users_list.remove(user_id)
            await event.edit(f"🔊 کاربر <code>{user_id}</code> حذف شد.", parse_mode="html")

    # ۳. دستور *لیست سکوت
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\*لیست سکوت$'))
    async def show_mute_list(event):
        await _ensure_loaded()
        if not client.muted_users_list:
            return await event.edit("🔇 لیست سکوت خالی است.")
            
        msg = await event.edit("🔄 در حال دریافت لیست...")
        text = "📑 <b>لیست افراد در حالت سکوت:</b>\n\n"
        
        for index, u_id in enumerate(client.muted_users_list, start=1):
            try:
                user = await client.get_entity(u_id)
                full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "کاربر بدون نام"
            except: full_name = "ناشناس"
            text += f"{index}. {full_name} ➔ <code>{u_id}</code>\n"
        await msg.edit(text, parse_mode="html")

    # ۴. دستور *پاکسازی سکوت
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\*پاکسازی سکوت$'))
    async def clear_mute_list(event):
        await _ensure_loaded()
        query = supabase.table("muted_users").delete().eq("owner_id", client.my_own_id)
        await db_execute(query)
        client.muted_users_list = []
        await event.edit("🧹 لیست سکوت پاکسازی شد.")