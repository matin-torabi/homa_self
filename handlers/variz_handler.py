from telethon import events
# ایمپورت توابع دیتابیس (مطمئن شوید مسیر درست است)
from utils import get_balance, update_balance 

def register_variz_handler(client):
    # پترن با ستاره شروع می‌شود و عدد بعد از آن را می‌گیرد
    @client.on(events.NewMessage(pattern=r'^\*واریز طلا (\d+)$'))
    async def handle_telethon_transfer(event):
        try:
            # گرفتن مقدار عددی از پترن
            amount = int(event.pattern_match.group(1))
            
            # بررسی اینکه حتما روی پیام کسی ریپلای شده باشد
            reply = await event.get_reply_message()
            if not reply:
                await event.edit("❌ برای واریز، روی پیام کاربر مورد نظر ریپلای کنید!")
                return

            sender = await event.get_sender()
            target = await reply.get_sender()

            # جلوگیری از واریز به خود
            if sender.id == target.id:
                await event.edit("❌ شما نمی‌توانید به خودتان طلا واریز کنید!")
                return

            # بررسی موجودی
            from_balance = await get_balance(sender.id)
            if from_balance < amount:
                await event.edit(f"❌ موجودی کافی نیست. موجودی فعلی: {from_balance:,}")
                return

            # اعمال تراکنش
            await update_balance(sender.id, -amount)
            await update_balance(target.id, amount)

            # ارسال پیام موفقیت و ویرایش پیام دستور
            await event.edit(
                f"✅ <b>واریز موفقیت‌آمیز!</b>\n\n"
                f"👤 گیرنده: {target.first_name}\n"
                f"💰 مقدار: {amount:,} طلا", 
                parse_mode='html'
            )
            
        except Exception as e:
            print(f"Error in telethon transfer: {e}")
            await event.edit("⚠️ خطایی در انجام تراکنش رخ داد.")