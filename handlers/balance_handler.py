from telethon import events

# ایمپورت کردن تابع get_balance از فایل utils خودت که متصل به سوپابیس هست
from utils import get_balance


def register_balance_handler(client):

    # رگکس کلمه *موجودی را فیلتر می‌کند
    @client.on(events.NewMessage(pattern=r"^\*موجودی"))
    async def handle_balance_request(event):
        # 🔴 شرط حیاتی: ربات فقط و فقط اگر دستور از طرف خودِ صاحب اکانت (تو) بود پاسخ دهد
        if not event.out:
            return

        user = await event.get_sender()
        if not user:
            return

        # گرفتن موجودی به صورت مستقیم و آنلاین از سوپابیس
        current_balance = await get_balance(user.id)

        # فرمت کردن عدد (مثلا ۱,۰۰۰)
        formatted_balance = "{:,}".format(current_balance)

        text = (
            f"👤 <b>کاربر:</b> {user.username if user.username else user.first_name}\n"
            f"🆔 <b>آیدی عددی:</b> <code>{user.id}</code>\n"
            f"💰 <b>طلای شما:</b> <code>{formatted_balance}</code> طلا"
        )

        # پاسخ به صورت ریپلای
        await event.reply(text, parse_mode="html")