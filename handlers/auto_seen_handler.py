import asyncio
from telethon import events, functions

# دیتابیس موقت در رم سرور
AUTO_SEEN_CACHE = {}

def register_auto_seen_handler(client):

    # ۱. هندلر پردازش سین خودکار
    @client.on(events.NewMessage(incoming=True))
    async def auto_seen_worker(event):
        # اگر کانال بود یا پیام از طرف خودمان بود، کاری انجام نده
        if event.is_channel or event.out: 
            return 
        
        try:
            # استخراج آیدی کلاینت (بهینه شده)
            if not hasattr(event.client, '_cached_my_id') or event.client._cached_my_id is None:
                me = await event.client.get_me()
                event.client._cached_my_id = me.id
            owner_id = event.client._cached_my_id
            
            # بررسی وضعیت از دیتابیس لوکال
            if owner_id not in AUTO_SEEN_CACHE:
                try:
                    from utils import get_auto_seen_from_db
                    db_status = get_auto_seen_from_db(owner_id)
                    AUTO_SEEN_CACHE[owner_id] = bool(db_status) if db_status is not None else False
                except:
                    AUTO_SEEN_CACHE[owner_id] = False
            
            is_active = AUTO_SEEN_CACHE.get(owner_id, False)
            
            # 🛑 اصلاح اصلی: 
            # اگر خاموش بود، فقط return کن تا بقیه هندلرها (منشی و...) کارشون رو انجام بدن.
            # دیگر از StopPropagation استفاده نمی‌کنیم.
            if not is_active:
                return 
                
            # ارسال آنی درخواست سین به تلگرام
            await event.client(functions.messages.ReadHistoryRequest(
                peer=event.peer_id,
                max_id=event.id
            ))
            
        except Exception as e:
            # مدیریت خطاهای احتمالی در سین کردن
            if "FloodWaitError" in str(e):
                await asyncio.sleep(5)

    # ۲. دستور تغییر وضعیت با متن
    @client.on(events.NewMessage(pattern=r"^\*?(سین خودکار) (روشن|خاموش)$", outgoing=True))
    async def toggle_seen_via_text(event):
        if not hasattr(event.client, '_cached_my_id') or event.client._cached_my_id is None:
            me = await event.client.get_me()
            event.client._cached_my_id = me.id
        owner_id = event.client._cached_my_id
        
        raw_status = event.pattern_match.group(2).strip()
        status = True if raw_status == "روشن" else False
        
        # آپدیت کش و دیتابیس
        AUTO_SEEN_CACHE[owner_id] = status
        try:
            from utils import save_auto_seen_to_db
            save_auto_seen_to_db(owner_id, status)
        except Exception as db_err:
            print(f"Error saving auto seen status: {db_err}")
        
        emoji = "🟢" if status else "🔴"
        msg_word = "روشن" if status else "خاموش"
        await event.edit(f"{emoji} <b>سین خودکار {msg_word} شد.</b>", parse_mode="html")