import asyncio
from datetime import datetime, timedelta
from telethon import events

# ایمپورت توابع آنلاین دیتابیس شما
from utils import get_auto_reply_from_db, save_auto_reply_to_db


def register_auto_reply(bot):
    """ثبت هندلرهای منشی خودکار به صورت کاملاً مجزا (Multi-Client) بر پایه سوپابیس"""
    
    # تعریف کش اختصاصی منشی برای هر کلاینت
    bot.reply_config = None
    bot.my_own_id = None
    bot.last_reply_cache = {} # حافظه موقت در رَم برای جلوگیری از اسپم {sender_id: datetime}

    # تابع اطمینان از لود شدن کش تنظیمات کلاینت
    async def ensure_config_loaded(client):
        if client.my_own_id is None:
            try:
                me = await client.get_me()
                client.my_own_id = me.id
            except Exception as e:
                print(f"⚠️ خطا در دریافت اطلاعات کلاینت: {e}")
                return

        res = await get_auto_reply_from_db(client.my_own_id)
        # مهار کردن نهایی مقدار None
        if res is not None:
            client.reply_config = res
        else:
            client.reply_config = {
                "enabled": False,
                "message": "🚫 الان آنلاین نیستم، بعداً پیام میدم!",
                "interval": 30,
                "mode": "once"
            }
        print(f"[*] تنظیمات منشی کلاینت {client.my_own_id} با موفقیت لود شد.")

    @bot.on(events.NewMessage(pattern=r'^\*منشی روشن$', outgoing=True))
    async def enable_reply(event):
        if bot.reply_config is None: await ensure_config_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        update_data = {"enabled": True}
        if await save_auto_reply_to_db(bot.my_own_id, update_data):
            bot.reply_config["enabled"] = True
            bot.last_reply_cache.clear() # ریست کردن حافظه موقت جلوگیری از اسپم
            
            mode_fa = 'همیشه' if bot.reply_config['mode'] == 'always' else 'هر کاربر یکبار'
            await event.edit(
                "✅ <b>منشی خودکار روشن شد!</b>\n\n"
                f"📝 پیام: <code>{bot.reply_config['message']}</code>\n"
                f"⏱️ فاصله: هر {bot.reply_config['interval']} دقیقه\n"
                f"🔄 حالت: <b>{mode_fa}</b>",
                parse_mode="html"
            )


    @bot.on(events.NewMessage(pattern=r'^\*منشی خاموش$', outgoing=True))
    async def disable_reply(event):
        if bot.reply_config is None: await ensure_config_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        update_data = {"enabled": False}
        if await save_auto_reply_to_db(bot.my_own_id, update_data):
            bot.reply_config["enabled"] = False
            bot.last_reply_cache.clear()
            await event.edit("❌ <b>منشی خودکار خاموش شد!</b>", parse_mode="html")


    @bot.on(events.NewMessage(pattern=r'^\*منشی پیام (.+)', outgoing=True))
    async def set_reply_message(event):
        if bot.reply_config is None: await ensure_config_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        message = event.pattern_match.group(1).strip()
        if not message:
            await event.edit("❌ لطفاً یک پیام بنویسید!")
            return
        
        update_data = {"message": message}
        if await save_auto_reply_to_db(bot.my_own_id, update_data):
            bot.reply_config['message'] = message
            await event.edit(
                f"✅ <b>پیام منشی تنظیم شد:</b>\n"
                f"<code>{message}</code>\n\n",
                parse_mode="html"
            )


    @bot.on(events.NewMessage(pattern=r'^\*منشی تایم (\d+)$', outgoing=True))
    async def set_reply_interval(event):
        if bot.reply_config is None: await ensure_config_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        try:
            minutes = int(event.pattern_match.group(1))
            if minutes < 1 or minutes > 1440:
                await event.edit("❌ زمان باید بین 1 تا 1440 دقیقه (24 ساعت) باشد!")
                return
            
            update_data = {"interval": minutes}
            if await save_auto_reply_to_db(bot.my_own_id, update_data):
                bot.reply_config['interval'] = minutes
                bot.last_reply_cache.clear()
                
                time_str = f"{minutes // 60} ساعت" if minutes >= 60 and minutes % 60 == 0 else f"{minutes} دقیقه"
                await event.edit(f"⏱️ <b>فاصله منشی تنظیم شد:</b> هر {time_str}", parse_mode="html")
        except ValueError:
            await event.edit("❌ لطفاً یک عدد معتبر وارد کنید!")


    @bot.on(events.NewMessage(pattern=r'^\*منشی حالت (always|once)$', outgoing=True))
    async def set_reply_mode(event):
        if bot.reply_config is None: await ensure_config_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        mode = event.pattern_match.group(1)
        update_data = {"mode": mode}
        
        if await save_auto_reply_to_db(bot.my_own_id, update_data):
            bot.reply_config['mode'] = mode
            bot.last_reply_cache.clear()
            mode_text = "همیشه (هر بار)" if mode == "always" else "هر کاربر یکبار"
            await event.edit(f"🔄 <b>حالت منشی تغییر کرد به:</b> {mode_text}", parse_mode="html")


    @bot.on(events.NewMessage(pattern=r'^\*وضعیت منشی$', outgoing=True))
    async def show_reply_status(event):
        if bot.reply_config is None: await ensure_config_loaded(bot)
        if event.sender_id != bot.my_own_id: return

        # بروزرسانی کش برای گرفتن آخرین دقیق تغییرات
        bot.reply_config = await get_auto_reply_from_db(bot.my_own_id)
        config = bot.reply_config

        status = "✅ روشن" if config['enabled'] else "❌ خاموش"
        time_str = f"{config['interval']} دقیقه"
        mode_text = "همیشه (هر بار)" if config['mode'] == 'always' else "هر کاربر یکبار"
        
        await event.edit(
            "📊 <b>وضعیت منشی خودکار شما</b>\n\n"
            f"🔹 وضعیت: {status}\n"
            f"📝 پیام: <code>{config['message']}</code>\n"
            f"⏱️ فاصله: هر {time_str}\n"
            f"🔄 حالت: {mode_text}\n"
            f"👥 تعداد کاربران در حافظه موقت امروز: {len(bot.last_reply_cache)}",
            parse_mode="html"
        )


    # هندلر اصلی - پاسخ به پیام‌های دریافتی پیوی
    @bot.on(events.NewMessage(incoming=True))
# هندلر اصلی - پاسخ به پیام‌های دریافتی پیوی
    @bot.on(events.NewMessage(incoming=True))
    async def auto_reply_handler(event):
        if event.out or not event.is_private:
            return

        if event.message.text and event.message.text.startswith('*منشی'):
            return

        # 🔥 پاتک اصلی اینجاست: به جای اتکا به کش قدیمی، دیتابیس رو زنده چک کن
        try:
            me = await event.client.get_me()
            # خواندن زنده از دیتابیس سوپابیس برای مهار تغییرات دکمه شیشه‌ای
            config = await get_auto_reply_from_db(me.id)
            if config:
                bot.reply_config = config # آپدیت کردن همزمان کش رَم
        except Exception as e:
            print(f"Error syncing db with secretary: {e}")
            config = bot.reply_config

        if not config or not config.get('enabled', False):
            return
            
        sender_id = event.sender_id
        if not sender_id: return
        
        current_time = datetime.now()
        
        # منطق کنترل اسپم با کش رَم
        if config.get('mode', 'once') == 'once':
            if sender_id in bot.last_reply_cache:
                return
        else:
            if sender_id in bot.last_reply_cache:
                last_time = bot.last_reply_cache[sender_id]
                if current_time - last_time < timedelta(minutes=config.get('interval', 30)):
                    return
        
        try:
            sender = await event.get_sender()
            first_name = getattr(sender, 'first_name', "کاربر") or "کاربر"
            
            reply_text = config.get('message', "🚫 الان آنلاین نیستم، بعداً پیام میدم!")
            reply_text = reply_text.replace('{name}', first_name)
            reply_text = reply_text.replace('{time}', current_time.strftime("%H:%M"))
            
            await event.reply(reply_text)
            bot.last_reply_cache[sender_id] = current_time
            
            # تمیزکاری کش رم
            for uid, last_t in list(bot.last_reply_cache.items()):
                if current_time - last_t > timedelta(hours=24):
                    del bot.last_reply_cache[uid]
                    
        except Exception as e:
            print(f"Error in auto reply system: {e}")

    @bot.on(events.NewMessage(pattern=r'^\*راهنمای منشی$', outgoing=True))
    async def reply_help(event):
        help_text = """
🤖 <b>راهنمای منشی خودکار</b>

<b>دستورات اصلی:</b>
• <code>*منشی روشن</code> - فعال کردن منشی
• <code>*منشی خاموش</code> - غیرفعال کردن منشی
• <code>*منشی پیام [متن]</code> - تنظیم پیام خودکار
• <code>*منشی تایم [دقیقه]</code> - تنظیم فاصله ارسال
• <code>*منشی حالت [always/once]</code> - حالت ارسال
• <code>*وضعیت منشی</code> - نمایش وضعیت فعلی

<b>متغیرهای قابل استفاده در پیام:</b>
• <code>{name}</code> - نام فرستنده
• <code>{time}</code> - ساعت فعلی
"""
        await event.edit(help_text, parse_mode="html")