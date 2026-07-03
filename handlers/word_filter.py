import asyncio
from telethon import events

# ایمپورت توابع دیتابیس آنلاین شما
from utils import get_user_filters_from_db, save_user_filters_to_db


def register_word_filter(bot):
    """ثبت هندلرهای فیلتر کلمات به صورت کاملاً ایزوله برای مالتی‌کلاینت"""
    
    # تعریف کش اختصاصی سیستم فیلتر برای هر کلاینت
    bot.filter_config = None
    bot.my_own_id = None

    # تابع اطمینان از لود شدن کش تنظیمات کلاینت
    async def ensure_filters_loaded(client):
        if client.my_own_id is None:
            try:
                me = await client.get_me()
                client.my_own_id = me.id
            except Exception as e:
                print(f" خطا در دریافت اطلاعات کلاینت در بخش فیلتر: {e}")
                return

        res = await get_user_filters_from_db(client.my_own_id)
        if res is not None:
            client.filter_config = res
        else:
            client.filter_config = {"enabled": False, "words": []}
        print(f"[*] تنظیمات فیلتر کلاینت {client.my_own_id} با موفقیت لود شد.")


    @bot.on(events.NewMessage(pattern=r'^\*فیلتر روشن$', outgoing=True))
    async def enable_filter(event):
        if bot.filter_config is None: await ensure_filters_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        update_data = {"enabled": True}
        if await save_user_filters_to_db(bot.my_own_id, update_data):
            bot.filter_config["enabled"] = True
            words = bot.filter_config.get("words", [])
            
            await event.edit(
                "✅ <b>فیلتر کلمات روشن شد!</b>\n"
                f"📝 تعداد کلمات فیلتر شده: {len(words)}\n"
                f"📋 کلمات: <code>{', '.join(words) if words else 'هیچ کلمه‌ای ثبت نشده'}</code>",
                parse_mode="html"
            )


    @bot.on(events.NewMessage(pattern=r'^\*فیلتر خاموش$', outgoing=True))
    async def disable_filter(event):
        if bot.filter_config is None: await ensure_filters_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        update_data = {"enabled": False}
        if await save_user_filters_to_db(bot.my_own_id, update_data):
            bot.filter_config["enabled"] = False
            await event.edit("❌ <b>فیلتر کلمات خاموش شد!</b>", parse_mode="html")


    @bot.on(events.NewMessage(pattern=r'^\*فیلتر کلمه (.+)', outgoing=True))
    async def add_filter_word(event):
        if bot.filter_config is None: await ensure_filters_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        word = event.pattern_match.group(1).strip().lower()
        if not word:
            await event.edit("❌ لطفاً یک کلمه بنویسید!")
            return

        words = bot.filter_config.get("words", [])
        if words is None: words = []

        if word in words:
            await event.edit(f"⚠️ کلمه <code>{word}</code> قبلاً در لیست فیلتر وجود دارد!", parse_mode="html")
            return

        # اضافه کردن به لیست و آپدیت دیتابیس
        words.append(word)
        update_data = {"words": words}
        
        if await save_user_filters_to_db(bot.my_own_id, update_data):
            bot.filter_config["words"] = words
            await event.edit(
                f"✅ کلمه <code>{word}</code> به لیست فیلتر اضافه شد!\n"
                f"📊 تعداد کل کلمات: {len(words)}",
                parse_mode="html"
            )


    @bot.on(events.NewMessage(pattern=r'^\*حذف فیلتر (.+)', outgoing=True))
    async def remove_filter_word(event):
        if bot.filter_config is None: await ensure_filters_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        word = event.pattern_match.group(1).strip().lower()
        words = bot.filter_config.get("words", [])
        if words is None: words = []

        if word not in words:
            await event.edit(f"⚠️ کلمه <code>{word}</code> در لیست فیلتر وجود ندارد!", parse_mode="html")
            return

        words.remove(word)
        update_data = {"words": words}
        
        if await save_user_filters_to_db(bot.my_own_id, update_data):
            bot.filter_config["words"] = words
            await event.edit(
                f"🗑️ کلمه <code>{word}</code> از لیست فیلتر حذف شد!\n"
                f"📊 تعداد باقیمانده: {len(words)}",
                parse_mode="html"
            )


    @bot.on(events.NewMessage(pattern=r'^\*لیست فیلتر$', outgoing=True))
    async def show_filter_list(event):
        if bot.filter_config is None: await ensure_filters_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        # همگام‌سازی کش جهت دقت خروجی
        bot.filter_config = await get_user_filters_from_db(bot.my_own_id)
        config = bot.filter_config

        words = config.get("words", [])
        if not words:
            await event.edit("📭 لیست فیلتر شما خالی است!")
            return

        words_list = '\n'.join([f"• <code>{w}</code>" for w in words])
        status_fa = '✅ روشن' if config.get("enabled", False) else '❌ خاموش'
        
        await event.edit(
            f"📋 <b>لیست کلمات فیلتر شده شما ({len(words)} کلمه):</b>\n\n"
            f"{words_list}\n\n"
            f"💡 وضعیت سیستم فیلتر: {status_fa}",
            parse_mode="html"
        )


    @bot.on(events.NewMessage(pattern=r'^\*پاکسازی فیلتر$', outgoing=True))
    async def clear_filter(event):
        if bot.filter_config is None: await ensure_filters_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        update_data = {"words": []}
        if await save_user_filters_to_db(bot.my_own_id, update_data):
            bot.filter_config["words"] = []
            await event.edit("🗑️ <b>تمام کلمات از لیست فیلتر شما پاک شدند!</b>", parse_mode="html")


    # ********** هندلر اصلی فیلتر پیام‌های ورودی **********
    @bot.on(events.NewMessage(incoming=True))
    async def filter_messages(event):
        if event.out: 
            return

        if bot.filter_config is None: 
            await ensure_filters_loaded(bot)

        # دفاع در برابر ساختار NoneType احتمالی
        if bot.filter_config is None:
            bot.filter_config = {"enabled": False, "words": []}

        config = bot.filter_config

        # اگه فیلتر کلاینت کلاً خاموشه یا کلمه‌ای نداره رد بشه
        if not config.get("enabled", False):
            return

        words = config.get("words", [])
        if not words:
            return

        clean_text = event.message.text.lower() if event.message.text else ""
        for char in [' ', '‌', '-', '_', '.', '\n', '\t']:
            clean_text = clean_text.replace(char, '')

        found_word = None
        for word in words:
            clean_word = word.replace(' ', '')
            if clean_word in clean_text:
                found_word = word
                break

        # بررسی سریع کلمات فیلتر شده از روی رَم سرور
        found_word = None
        for word in words:
            if word in clean_text:
                found_word = word
                break

        if not found_word:
            return

        try:
            # 🛑 حالت اول: در گروه یا کانال دیگران
            if event.is_group or event.is_channel:
                await event.message.delete()
                
                sender = await event.get_sender()
                sender_name = getattr(sender, 'first_name', "کاربر") or "کاربر"
                
                warning = await event.respond(
                    f"⚠️ {sender_name}، کلمه <code>{found_word}</code> فیلتر شده است!\n"
                    f"پیام شما حذف شد.",
                    parse_mode="html"
                )
                await asyncio.sleep(3)
                await warning.delete()
            
            # 🛑 حالت دوم: در چت خصوصی (پیوی)
            elif event.is_private:
                await event.message.delete()
                
                # await event.respond(
                #     f"⚠️ کلمه <code>{found_word}</code> در لیست فیلتر من قرار دارد!\n"
                #     f"پیام شما حذف شد.",
                #     parse_mode="html"
                # )
                
                # ارسال نسخه کپی پیام فیلتر شده به پیوی خودش (صاحب سلف‌بات)
                sender = await event.get_sender()
                sender_name = getattr(sender, 'first_name', "کاربر") or "کاربر"
                
                await bot.send_message(
                    bot.my_own_id,
                    f"🚫 <b>پیام فیلتر شده از {sender_name} (<code>{event.sender_id}</code>):</b>\n\n"
                    f"🔑 کلمه کشف شده: <code>{found_word}</code>\n"
                    f"📄 متن پیام: {event.message.text[:200]}",
                    parse_mode="html"
                )
        
        except Exception as e:
            print(f"Error in word filter execution for {bot.my_own_id}: {e}")


    @bot.on(events.NewMessage(pattern=r'^\*راهنمای فیلتر$', outgoing=True))
    async def filter_help(event):
        if event.sender_id != bot.my_own_id: return
        help_text = """
🎯 <b>راهنمای سیستم فیلتر کلمات اختصاصی شما</b>

⚡ <b>عملکرد:</b> حذف خودکار پیام‌های حاوی کلمات ممنوعه در پیوی و گروه‌ها

<b>دستورات مدیریت (ارسال توسط خودتان):</b>
• <code>*فیلتر روشن</code> - فعال کردن فیلتر
• <code>*فیلتر خاموش</code> - غیرفعال کردن فیلتر
• <code>*فیلتر کلمه [کلمه]</code> - اضافه کردن به لیست
• <code>*حذف فیلتر [کلمه]</code> - حذف از لیست
• <code>*لیست فیلتر</code> - نمایش کلمات ممنوعه شما
• <code>*پاکسازی فیلتر</code> - حذف کل کلمات
"""
        await event.edit(help_text, parse_mode="html")