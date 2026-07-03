import asyncio
from telethon import events
from config import supabase
from utils import db_execute  # ایمپورت تابع مدیریت ترد

# =====================================================================
# 🗄️ بخش اول: توابع دیتابیس (Supabase) - نسخه Async
# =====================================================================

async def get_user_chat_action(user_id: int) -> str:
    try:
        # ساخت کوئری
        query = supabase.table("user_chat_actions").select("action").eq("user_id", user_id)
        # اجرای غیرهمزمان
        res = await db_execute(query)
        
        if res.data:
            return res.data[0]["action"]
    except Exception as e:
        print(f"❌ Error fetching chat action: {e}")
    return "none"

async def set_user_chat_action(user_id: int, action: str):
    try:
        # ساخت کوئری
        query = supabase.table("user_chat_actions").upsert({"user_id": user_id, "action": action})
        # اجرای غیرهمزمان
        await db_execute(query)
    except Exception as e:
        print(f"❌ Error saving chat action: {e}")


# =====================================================================
# ⚡ بخش دوم: موتور فرستادن اکشن فیک هوشمند
# =====================================================================
def register_chat_action_engine(bot):
    """شنود هوشمند چت‌ها جهت ارسال اکشن"""
    
    action_mapping = {
        "typing": "typing",
        "record-audio": "audio",        
        "upload-video": "video",        
        "record-round": "round",        
        "upload-photo": "photo",        
        "upload-document": "document", 
        "choose-sticker": "sticker",   
        "playing": "game"              
    }

    @bot.on(events.NewMessage(outgoing=True))
    async def on_my_message(event):
        if event.text and event.text.startswith('*'):
            return
            
        if not hasattr(event.client, '_cached_my_id') or event.client._cached_my_id is None:
            me = await event.client.get_me()
            event.client._cached_my_id = me.id
        owner_id = event.client._cached_my_id
        
        # استفاده از await برای فراخوانی تابع async
        mode = await get_user_chat_action(owner_id)
        if mode == "none" or mode not in action_mapping:
            return
            
        try:
            async with event.client.action(event.peer_id, action_mapping[mode]):
                await asyncio.sleep(2)
        except Exception:
            pass

    @bot.on(events.NewMessage(incoming=True))
    async def on_incoming_message(event):
        if not event.is_private: 
            return
            
        if not hasattr(event.client, '_cached_my_id') or event.client._cached_my_id is None:
            me = await event.client.get_me()
            event.client._cached_my_id = me.id
        owner_id = event.client._cached_my_id
        
        # استفاده از await برای فراخوانی تابع async
        mode = await get_user_chat_action(owner_id)
        if mode == "none" or mode not in action_mapping:
            return
            
        try:
            async with event.client.action(event.chat_id, action_mapping[mode]):
                await asyncio.sleep(3)
        except Exception:
            pass