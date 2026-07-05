import time
import asyncio
from telethon import events

from utils import get_balance

def register_utils_handlers(client):
    """
    این تابع هندلرهای کاربردی (پینگ و آیدی) را به کلاینت اضافه می‌کند.
    """
    @client.on(events.NewMessage(outgoing=True, pattern=r'^\*آیدی$'))
    async def handle_id(event):
        # حالت اول: ریپلای روی پیام یک کاربر دیگر (نمایش اطلاعات کامل او)
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            user_id = reply_msg.sender_id
            
            if user_id:
                try:
                    # گرفتن اطلاعات کامل کاربر از سرور تلگرام
                    user = await client.get_entity(user_id)
                    
                    first_name = user.first_name if user.first_name else "❌ ندارد"
                    last_name = user.last_name if user.last_name else "❌ ندارد"
                    username = f"@{user.username}" if user.username else "❌ ندارد"
                    balance = await get_balance(user_id)
                    toman_balance = balance * 35

                    response = (
                        "👤 **اطلاعات کاربر مورد نظر:**\n\n"
                        f"🔹 **نام:** {first_name}\n"
                        f"🔹 **نام خانوادگی:** {last_name}\n"
                        f"🔹 **یوزرنیم:** {username}\n"
                        f"🆔 **آیدی عددی:** `{user.id}`\n"
                        f"💰 **موجودی:** {balance:,} طلا\n"
                        f"💵 **معادل تومان:** {toman_balance:,} تومان"
                    )
                except Exception as e:
                    print(f"Error fetching user entity: {e}")
                    response = "❌ خطایی در دریافت اطلاعات کامل کاربر رخ داد."
            else:
                response = "❌ نتوانستم آیدی کاربر را دریافت کنم (شاید پیام از یک کانال یا ربات ناشناس است)."
        
        # حالت دوم: دستور بدون ریپلای (آیدی خودت و چت فعلی)
        else:
            my_id = event.sender_id
            chat_id = event.chat_id
            response = f"🆔 **آیدی شما:** `{my_id}`\n💬 **آیدی این چت:** `{chat_id}`"
        
        # ویرایش پیام دستور به متن پاسخ
        msg = await event.edit(response)
        
