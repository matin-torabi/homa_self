# import os
# import asyncio
# from datetime import datetime
# from telethon import events, types

# # هاب مرکزی کلاینت‌ها برای جلوگیری از تداخل حافظه در مولتی‌کلاینت
# GLOBAL_CLIENTS = {}

# def register_chat_guard(bot):
#     """ثبت هندلرهای پیشرفته نگهبان چت - نسخه فوق‌پایدار هوشمند با نمایش مشخصات کامل کاربر"""
    
#     async def init_and_get_client_data(client_bot):
#         try:
#             if not hasattr(client_bot, '_cached_my_id') or client_bot._cached_my_id is None:
#                 me = await client_bot.get_me()
#                 client_bot._cached_my_id = me.id
            
#             my_id = client_bot._cached_my_id
            
#             if my_id not in GLOBAL_CLIENTS:
#                 GLOBAL_CLIENTS[my_id] = {
#                     "client": client_bot,
#                     "guard_config": {"save_deleted": True, "save_edited": True, "save_ttl": True},
#                     "msg_history_cache": {},
#                     "cache_keys_order": []
#                 }
                
#                 async def load_db_config(uid):
#                     try:
#                         from utils import get_chat_guard_from_db
#                         cfg = get_chat_guard_from_db(uid)
#                         if cfg:
#                             GLOBAL_CLIENTS[uid]["guard_config"] = cfg
#                             print(f"⚙️ تنظیمات دیتابیس برای کلاینت {uid} اعمال شد.")
#                     except Exception as db_err:
#                         print(f"❌ خطا در لود دیتابیس برای {uid}: {db_err}")
                
#                 client_bot.loop.create_task(load_db_config(my_id))
                
#             return GLOBAL_CLIENTS[my_id]
#         except Exception as e:
#             return None

#     # ==========================================
#     # ۱. هندلرهای دستورات مدیریت نگهبان
#     # ==========================================
    
#     @bot.on(events.NewMessage(pattern=r'^\*(پیام های حذف شده|پیامهای حذف شده) (روشن|خاموش)$', outgoing=True))
#     async def toggle_deleted(event):
#         data = await init_and_get_client_data(event.client)
#         if not data: return
#         from utils import save_chat_guard_to_db
#         status = event.pattern_match.group(2) == "روشن"
#         if save_chat_guard_to_db(event.client._cached_my_id, {"save_deleted": status}):
#             data["guard_config"]["save_deleted"] = status
#             await event.edit(f"🔒 ذخیره حذف شده‌ها: {'🟢 روشن' if status else '🔴 خاموش'}")

#     @bot.on(events.NewMessage(pattern=r'^\*(پیام های ویرایش شده|پیامهای ویرایش شده) (روشن|خاموش)$', outgoing=True))
#     async def toggle_edited(event):
#         data = await init_and_get_client_data(event.client)
#         if not data: return
#         from utils import save_chat_guard_to_db
#         status = event.pattern_match.group(2) == "روشن"
#         if save_chat_guard_to_db(event.client._cached_my_id, {"save_edited": status}):
#             data["guard_config"]["save_edited"] = status
#             await event.edit(f"🔒 ذخیره ویرایش شده‌ها: {'🟢 روشن' if status else '🔴 خاموش'}")

#     @bot.on(events.NewMessage(pattern=r'^\*(عکس تایمی|عکسهای تایمی) (روشن|خاموش)$', outgoing=True))
#     async def toggle_ttl(event):
#         data = await init_and_get_client_data(event.client)
#         if not data: return
#         from utils import save_chat_guard_to_db
#         status = event.pattern_match.group(2) == "روشن"
#         if save_chat_guard_to_db(event.client._cached_my_id, {"save_ttl": status}):
#             data["guard_config"]["save_ttl"] = status
#             await event.edit(f"🔒 ذخیره عکس تایمی: {'🟢 روشن' if status else '🔴 خاموش'}")

#     # ==========================================
#     # ۲. هندلر اصلی دریافت پیام (بک‌آپ‌گیری سریع در کش)
#     # ==========================================
#     @bot.on(events.NewMessage(incoming=True))
#     async def universal_tracker_and_ttl(event):
#         if not event.is_private or event.out: return
        
#         data = await init_and_get_client_data(event.client)
#         if not data: return

#         # الف) ذخیره آنی متن پیام متنی در کش (همراه با نام و یوزرنیم فرستنده)
#         if event.text:
#             try:
#                 sender = await event.get_sender()
#                 first_name = getattr(sender, 'first_name', '') or ''
#                 last_name = getattr(sender, 'last_name', '') or ''
#                 full_name = f"{first_name} {last_name}".strip() or "کاربر ناشناس"
#                 username = f"@{sender.username}" if getattr(sender, 'username', None) else "ندارد"

#                 data["msg_history_cache"][event.id] = {
#                     "text": event.text,
#                     "sender_id": event.sender_id,
#                     "sender_name": full_name,
#                     "username": username,
#                     "date": datetime.now().strftime("%H:%M:%S")
#                 }
#                 data["cache_keys_order"].append(event.id)
                
#                 # بهینه‌سازی خودکار کش حافظه برای جلوگیری از کندی سلف‌بات
#                 if len(data["cache_keys_order"]) > 3000:
#                     old_id = data["cache_keys_order"].pop(0)
#                     data["msg_history_cache"].pop(old_id, None)
#             except Exception as e:
#                 print(f"❌ خطا در ثبت کش متنی: {e}")

#         # ب) شکار عکس یا فیلم تایم‌دار
#         try:
#             if data["guard_config"] and data["guard_config"].get("save_ttl", False) and event.media:
#                 is_ttl = False
#                 if hasattr(event.media, 'ttl_seconds') and event.media.ttl_seconds: is_ttl = True
#                 elif isinstance(event.media, types.MessageMediaDocument) and getattr(event.media.document, 'ttl_seconds', None): is_ttl = True
                    
#                 if is_ttl:
#                     sender = await event.get_sender()
#                     first_name = getattr(sender, 'first_name', '') or ''
#                     last_name = getattr(sender, 'last_name', '') or ''
#                     full_name = f"{first_name} {last_name}".strip() or "کاربر ناشناس"
#                     username = f"@{sender.username}" if getattr(sender, 'username', None) else "ندارد"

#                     path = await event.download_media()
#                     if path and os.path.exists(path):
#                         caption = (
#                             f"⏱️ <b>عکس/فیلم تایم‌دار نجات یافته!</b>\n"
#                             f"👤 <b>نام فرستنده:</b> {full_name}\n"
#                             f"🆔 <b>یوزرنیم:</b> {username}\n"
#                             f"🔢 <b>آیدی عددی:</b> <code>{event.sender_id}</code>"
#                         )
#                         uploaded_file = await event.client.upload_file(path)
#                         await event.client.send_file(event.client._cached_my_id, uploaded_file, caption=caption, parse_mode="html")
#                         os.remove(path)
#         except:
#             pass

#     # ==========================================
#     # ۳. شنود اختصاصی پیام‌های ویرایش شده (Raw Engine)
#     # ==========================================
#     @bot.on(events.Raw())
#     async def on_raw_update(event):
#         if not isinstance(event, (types.UpdateEditMessage, types.UpdateEditChannelMessage)): 
#             return
            
#         message = event.message
#         if not message or message.out or not isinstance(message.peer_id, types.PeerUser): 
#             return

#         current_bot = event._client
#         if not current_bot: return
        
#         data = await init_and_get_client_data(current_bot)
#         if not data or not data["guard_config"] or not data["guard_config"].get("save_edited", False): 
#             return
            
#         try:
#             if message.id in data["msg_history_cache"]:
#                 old_data = data["msg_history_cache"][message.id]
#                 new_text = message.message
                
#                 if not new_text or old_data["text"] == new_text: 
#                     return
                
#                 report = (
#                     "✏️ <b>پیام ویرایش شده کشف شد!</b>\n"
#                     f"👤 <b>نام فرستنده:</b> {old_data['sender_name']}\n"
#                     f"🆔 <b>یوزرنیم:</b> {old_data['username']}\n"
#                     f"🔢 <b>آیدی عددی:</b> <code>{message.peer_id.user_id}</code>\n"
#                     f"⏱️ زمان ارسال اولیه: {old_data['date']}\n\n"
#                     f"📝 <b>متن قدیمی:</b>\n<code>{old_data['text']}</code>\n\n"
#                     f"🔄 <b>متن جدید:</b>\n<code>{new_text}</code>"
#                 )
                
#                 await current_bot.send_message(current_bot._cached_my_id, report, parse_mode="html")
#                 # بروزرسانی متن کش جهت تشخیص ادیت‌های بعدی احتمالی روی همین پیام
#                 data["msg_history_cache"][message.id]["text"] = new_text
#         except Exception as e:
#             print(f"❌ خطا در ردیابی ادیت: {e}")

#     # ==========================================
#     # ۴. شنود پیام‌های حذف شده (مستقل)
#     # ==========================================
#     @bot.on(events.MessageDeleted())
#     async def on_message_deleted(event):
#         current_bot = event.client
#         data = await init_and_get_client_data(current_bot)
#         if not data or not data["guard_config"] or not data["guard_config"].get("save_deleted", False): 
#             return
            
#         try:
#             for deleted_id in event.deleted_ids:
#                 old_data = data["msg_history_cache"].pop(deleted_id, None)
#                 if old_data:
#                     report = (
#                         "🗑️ <b>پیام حذف شده نجات یافت!</b>\n"
#                         f"👤 <b>نام فرستنده:</b> {old_data['sender_name']}\n"
#                         f"🆔 <b>یوزرنیم:</b> {old_data['username']}\n"
#                         f"🔢 <b>آیدی عددی:</b> <code>{old_data['sender_id']}</code>\n"
#                         f"⏱️ زمان ارسال: {old_data['date']}\n\n"
#                         f"💬 <b>متن پیام پاک شده:</b>\n<code>{old_data['text']}</code>"
#                     )
#                     await current_bot.send_message(current_bot._cached_my_id, report, parse_mode="html")
#         except Exception as e:
#             print(f"❌ خطا در پردازش حذف: {e}")


import os
import asyncio
from datetime import datetime
from telethon import events, types
from utils import get_chat_guard_from_db

# هاب مرکزی کلاینت‌ها برای جلوگیری از تداخل حافظه در مولتی‌کلاینت
GLOBAL_CLIENTS = {}

def register_chat_guard(bot):
    """ثبت هندلرهای پیشرفته نگهبان چت - نسخه فوق‌پایدار مولتی‌کلاینت هماهنگ با دکمه‌های شیشه‌ای پنل ادمین"""
    
    async def init_and_get_client_data(client_bot):
        try:
            if not hasattr(client_bot, '_cached_my_id') or client_bot._cached_my_id is None:
                me = await client_bot.get_me()
                client_bot._cached_my_id = me.id
            
            my_id = client_bot._cached_my_id
            

            cfg = await get_chat_guard_from_db(my_id)
            if not cfg:
                cfg = {"save_deleted": True, "save_edited": True, "save_ttl": True}

            if my_id not in GLOBAL_CLIENTS:
                GLOBAL_CLIENTS[my_id] = {
                    "client": client_bot,
                    "guard_config": cfg,
                    "msg_history_cache": {},
                    "cache_keys_order": []
                }
            else:
                # 🔥 نکته کلیدی: بروزرسانی مداوم کانفیگ از دیتابیس جهت هماهنگی با پنل دکمه‌ای
                GLOBAL_CLIENTS[my_id]["guard_config"] = cfg
                
            return GLOBAL_CLIENTS[my_id]
        except Exception as e:
            print(f"❌ خطا در لود و سینک کلاینت: {e}")
            return None

    # ==========================================
    # ۱. هندلرهای دستورات متنی (روشن و خاموش مستقیم)
    # ==========================================
    
    @bot.on(events.NewMessage(pattern=r'^\*(پیام های حذف شده|پیامهای حذف شده) (روشن|خاموش)$', outgoing=True))
    async def toggle_deleted(event):
        data = await init_and_get_client_data(event.client)
        if not data: return
        from utils import save_chat_guard_to_db
        status = event.pattern_match.group(2) == "روشن"
        
        # ساخت دیکشنری کامل جهت جلوگیری از ارورهای احتمالی دیتابیس
        update_dict = data["guard_config"].copy()
        update_dict["save_deleted"] = status
        
        if await save_chat_guard_to_db(event.client._cached_my_id, update_dict):
            data["guard_config"]["save_deleted"] = status
            await event.edit(f"🔒 ذخیره حذف شده‌ها: {'🟢 روشن' if status else '🔴 خاموش'}")

    @bot.on(events.NewMessage(pattern=r'^\*(پیام های ویرایش شده|پیامهای ویرایش شده) (روشن|خاموش)$', outgoing=True))
    async def toggle_edited(event):
        data = await init_and_get_client_data(event.client)
        if not data: return
        from utils import save_chat_guard_to_db
        status = event.pattern_match.group(2) == "روشن"
        
        update_dict = data["guard_config"].copy()
        update_dict["save_edited"] = status
        
        if await save_chat_guard_to_db(event.client._cached_my_id, update_dict):
            data["guard_config"]["save_edited"] = status
            await event.edit(f"🔒 ذخیره ویرایش شده‌ها: {'🟢 روشن' if status else '🔴 خاموش'}")

    @bot.on(events.NewMessage(pattern=r'^\*(عکس تایمی|عکسهای تایمی) (روشن|خاموش)$', outgoing=True))
    async def toggle_ttl(event):
        data = await init_and_get_client_data(event.client)
        if not data: return
        from utils import save_chat_guard_to_db
        status = event.pattern_match.group(2) == "روشن"
        
        update_dict = data["guard_config"].copy()
        update_dict["save_ttl"] = status
        
        if await save_chat_guard_to_db(event.client._cached_my_id, update_dict):
            data["guard_config"]["save_ttl"] = status
            await event.edit(f"🔒 ذخیره عکس تایمی: {'🟢 روشن' if status else '🔴 خاموش'}")

    # ==========================================
    # ۲. هندلر اصلی دریافت پیام (بک‌آپ‌گیری سریع در کش)
    # ==========================================
    @bot.on(events.NewMessage(incoming=True))
    async def universal_tracker_and_ttl(event):
        if not event.is_private or event.out: return
        
        data = await init_and_get_client_data(event.client)
        if not data: return

        # الف) ذخیره آنی متن پیام متنی در کش
        if event.text:
            try:
                sender = await event.get_sender()
                first_name = getattr(sender, 'first_name', '') or ''
                last_name = getattr(sender, 'last_name', '') or ''
                full_name = f"{first_name} {last_name}".strip() or "کاربر ناشناس"
                username = f"@{sender.username}" if getattr(sender, 'username', None) else "ندارد"

                data["msg_history_cache"][event.id] = {
                    "text": event.text,
                    "sender_id": event.sender_id,
                    "sender_name": full_name,
                    "username": username,
                    "date": datetime.now().strftime("%H:%M:%S")
                }
                data["cache_keys_order"].append(event.id)
                
                if len(data["cache_keys_order"]) > 3000:
                    old_id = data["cache_keys_order"].pop(0)
                    data["msg_history_cache"].pop(old_id, None)
            except Exception as e:
                print(f"❌ خطا در ثبت کش متنی: {e}")

        # ب) شکار عکس یا فیلم تایم‌دار
        try:
            if data["guard_config"] and data["guard_config"].get("save_ttl", False) and event.media:
                is_ttl = False
                if hasattr(event.media, 'ttl_seconds') and event.media.ttl_seconds: is_ttl = True
                elif isinstance(event.media, types.MessageMediaDocument) and getattr(event.media.document, 'ttl_seconds', None): is_ttl = True
                    
                if is_ttl:
                    sender = await event.get_sender()
                    first_name = getattr(sender, 'first_name', '') or ''
                    last_name = getattr(sender, 'last_name', '') or ''
                    full_name = f"{first_name} {last_name}".strip() or "کاربر ناشناس"
                    username = f"@{sender.username}" if getattr(sender, 'username', None) else "ندارد"

                    path = await event.download_media()
                    if path and os.path.exists(path):
                        caption = (
                            f"⏱️ <b>عکس/فیلم تایم‌دار نجات یافته!</b>\n"
                            f"👤 <b>نام فرستنده:</b> {full_name}\n"
                            f"🆔 <b>یوزرنیم:</b> {username}\n"
                            f"🔢 <b>آیدی عددی:</b> <code>{event.sender_id}</code>"
                        )
                        uploaded_file = await event.client.upload_file(path)
                        await event.client.send_file(event.client._cached_my_id, uploaded_file, caption=caption, parse_mode="html")
                        os.remove(path)
        except:
            pass

    # ==========================================
    # ۳. شنود اختصاصی پیام‌های ویرایش شده (Raw Engine)
    # ==========================================
    @bot.on(events.Raw())
    async def on_raw_update(event):
        if not isinstance(event, (types.UpdateEditMessage, types.UpdateEditChannelMessage)): 
            return
            
        message = event.message
        if not message or message.out or not isinstance(message.peer_id, types.PeerUser): 
            return

        current_bot = event._client
        if not current_bot: return
        
        data = await init_and_get_client_data(current_bot)
        if not data or not data["guard_config"] or not data["guard_config"].get("save_edited", False): 
            return
            
        try:
            if message.id in data["msg_history_cache"]:
                old_data = data["msg_history_cache"][message.id]
                new_text = message.message
                
                if not new_text or old_data["text"] == new_text: 
                    return
                
                report = (
                    "✏️ <b>پیام ویرایش شده کشف شد!</b>\n"
                    f"👤 <b>نام فرستنده:</b> {old_data['sender_name']}\n"
                    f"🆔 <b>یوزرنیم:</b> {old_data['username']}\n"
                    f"🔢 <b>آیدی عددی:</b> <code>{message.peer_id.user_id}</code>\n"
                    f"⏱️ زمان ارسال اولیه: {old_data['date']}\n\n"
                    f"📝 <b>متن قدیمی:</b>\n<code>{old_data['text']}</code>\n\n"
                    f"🔄 <b>متن جدید:</b>\n<code>{new_text}</code>"
                )
                
                await current_bot.send_message(current_bot._cached_my_id, report, parse_mode="html")
                data["msg_history_cache"][message.id]["text"] = new_text
        except Exception as e:
            print(f"❌ خطا در ردیابی ادیت: {e}")

    # ==========================================
    # ۴. شنود پیام‌های حذف شده (مستقل)
    # ==========================================
    @bot.on(events.MessageDeleted())
    async def on_message_deleted(event):
        current_bot = event.client
        data = await init_and_get_client_data(current_bot)
        if not data or not data["guard_config"] or not data["guard_config"].get("save_deleted", False): 
            return
            
        try:
            for deleted_id in event.deleted_ids:
                old_data = data["msg_history_cache"].pop(deleted_id, None)
                if old_data:
                    report = (
                        "🗑️ <b>پیام حذف شده نجات یافت!</b>\n"
                        f"👤 <b>نام فرستنده:</b> {old_data['sender_name']}\n"
                        f"🆔 <b>یوزرنیم:</b> {old_data['username']}\n"
                        f"🔢 <b>آیدی عددی:</b> <code>{old_data['sender_id']}</code>\n"
                        f"⏱️ زمان ارسال: {old_data['date']}\n\n"
                        f"💬 <b>متن پیام پاک شده:</b>\n<code>{old_data['text']}</code>"
                    )
                    await current_bot.send_message(current_bot._cached_my_id, report, parse_mode="html")
        except Exception as e:
            print(f"❌ خطا در پردازش حذف: {e}")