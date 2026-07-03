import asyncio
from telethon import events
from telethon.tl.types import MessageEntitySpoiler
from utils import db_execute
from config import supabase

# =====================================================================
# 🗄️ بخش اول: توابع دیتابیس (Async)
# =====================================================================

async def get_user_text_mode(user_id: int) -> str:
    """دریافت مود فعلی متن کاربر از دیتابیس به صورت غیرهمزمان"""
    try:
        query = supabase.table("user_text_modes").select("mode").eq("user_id", user_id)
        res = await db_execute(query)
        if res.data:
            return res.data[0]["mode"]
    except Exception as e:
        print(f"❌ Error fetching text mode: {e}")
    return "none"

async def set_user_text_mode(user_id: int, mode: str):
    """ذخیره یا آپدیت مود متن کاربر در دیتابیس به صورت غیرهمزمان"""
    try:
        query = supabase.table("user_text_modes").upsert({"user_id": user_id, "mode": mode})
        await db_execute(query)
    except Exception as e:
        print(f"❌ Error saving text mode: {e}")

# =====================================================================
# ✍️ بخش دوم: موتور اصلی اعمال فونت و افکت تایپ انیمیشنی
# =====================================================================
def register_auto_font_engine(bot):
    """شنود پیام‌های خروجی کلاینت و اعمال خودکار فونت و افکت‌های پیشرفته"""
    
    @bot.on(events.NewMessage(outgoing=True))
    async def auto_font_formatter(event):
        if event.text and event.text.startswith('*'):
            return
            
        if not hasattr(event.client, '_cached_my_id') or event.client._cached_my_id is None:
            me = await event.client.get_me()
            event.client._cached_my_id = me.id
        owner_id = event.client._cached_my_id
        
        mode = await get_user_text_mode(owner_id)
        if mode == "none" or not event.text:
            return
            
        raw_text = event.text
        
        # -------------------------------------------------------------
        # 🌊 حالت اول: افکت تایپ انیمیشنی
        # -------------------------------------------------------------
        if mode == "gradient":
            words = raw_text.split()
            if len(words) <= 1: return
                
            current_text = ""
            for i, word in enumerate(words):
                current_text += (word + " ")
                if i == 0: continue
                
                try:
                    await event.edit(current_text.strip() + " |")
                    await asyncio.sleep(0.2)
                except Exception: pass
            
            try: await event.edit(raw_text)
            except Exception: pass
            return
        
        # -------------------------------------------------------------
        # 📚 حالت دوم: استایل‌های متنی
        # -------------------------------------------------------------
        formatted_text = raw_text
        parse_mode = "markdown"
        msg_entities = None
        
        if mode == "bold": formatted_text = f"**{raw_text}**"
        elif mode == "italic":
            formatted_text = f"<i>{raw_text}</i>"; parse_mode = "html"
        elif mode == "strike": formatted_text = f"~~{raw_text}~~"
        elif mode == "mono": formatted_text = f"`{raw_text}`"
        elif mode == "underline":
            formatted_text = f"<u>{raw_text}</u>"; parse_mode = "html"
        elif mode == "spoiler":
            formatted_text = raw_text
            parse_mode = None
            msg_entities = [MessageEntitySpoiler(offset=0, length=len(raw_text))]
        elif mode == "quote":
            formatted_text = f"<blockquote>{raw_text}</blockquote>"; parse_mode = "html"

        try:
            if mode == "spoiler":
                await event.edit(formatted_text, formatting_entities=msg_entities)
            elif event.text != formatted_text: 
                await event.edit(formatted_text, parse_mode=parse_mode)
        except Exception as e:
            if "not modified" not in str(e).lower():
                print(f"❌ خطای اعمال فونت خودکار: {e}")