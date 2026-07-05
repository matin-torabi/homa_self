import asyncio
from email.mime import text
import random
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# وارد کردن توابع کمکی دیتابیس آنلاین شما از سوپابیس
from utils import get_balance, update_balance, save_game, get_game, delete_game

# آدرس عکس پنل بازی

def get_user_mention(user) -> str:
    """ساخت منشن کاربر سازگار با متد HTML"""
    if user.username:
        return f"@{user.username}"
    # استفاده از منشن HTML استاندارد برای کاربران بدون یوزرنیم
    return f'<a href="tg://user?id={user.id}">{user.first_name}</a>'


# =========================================
# HANDLE BALANCE REQUEST
# =========================================
async def handle_balance_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش موجودی طلا از سوپابیس"""
    user = update.effective_user
    current_balance = await get_balance(user.id)
    user_mention = get_user_mention(user)
    
    text = (
        f"👤 <b>کاربر:</b> {user_mention}\n"
        f"🆔 <b>آیدی عددی:</b> <code>{user.id}</code>\n"
        f"💰 <b>طلای شما:</b> <code>{current_balance:,}</code> طلا\n"
        f"💵 <b>معادل تومان:</b> <code>{current_balance * 35:,}</code> تومان"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# =========================================
# HANDLE TRANSFER REQUEST
# =========================================
async def handle_transfer_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر انتقال طلا با ریپلای روی پیام کاربر دیگر"""
    message = update.effective_message
    from_user = update.effective_user
    from_mention = get_user_mention(from_user)

    if not message.reply_to_message:
        await message.reply_text("❌ برای واریز طلا، باید این دستور را روی پیام کاربر مورد نظر ریپلای کنید!")
        return

    to_user = message.reply_to_message.from_user
    to_mention = get_user_mention(to_user)

    if from_user.id == to_user.id:
        await message.reply_text("❌ شما نمی‌توانید به خودتان طلا واریز کنید!")
        return

    text_parts = message.text.split()
    if len(text_parts) < 3:
        await message.reply_text("❌ فرمت دستور اشتباه است!\nنمونه درست: <code>واریز طلا 50</code>", parse_mode="HTML")
        return

    amount_str = text_parts[2]
    if not amount_str.isdigit():
        await message.reply_text("❌ لطفا مقدار طلا را به صورت یک عدد معتبر و مثبت وارد کنید!")
        return

    amount = int(amount_str)
    if amount <= 0:
        await message.reply_text("❌ مقدار واریز باید بیشتر از 0 باشد!")
        return

    from_balance = await get_balance(from_user.id)
    if from_balance < amount:
        await message.reply_text(f"❌ موجودی طلای شما کافی نیست!\n💰 طلای شما: {from_balance:,} طلا")
        return

    # اعمال ترکنش در دیتابیس آنلاین سوپابیس
    await update_balance(from_user.id, -amount)
    await update_balance(to_user.id, amount)

    new_balance = await get_balance(from_user.id)

    success_text = (
        f"✅ <b>واریز موفقیت‌آمیز بود!</b>\n\n"
        f"👤 <b>فرستنده:</b> {from_mention} (<code>{from_user.id}</code>)\n"
        f"👤 <b>گیرنده:</b> {to_mention} (<code>{to_user.id}</code>)\n"
        f"💰 <b>مقدار منتقل شده:</b> {amount:,} طلا\n"
        f"💵 <b>معادل تومان:</b> {(amount * 35):,} تومان\n\n"
        f"💰 <b>موجودی جدید شما:</b> {new_balance:,} طلا\n"
        f"💵 <b>معادل تومان:</b> {(new_balance * 35):,} تومان"
    )
    await message.reply_text(success_text, parse_mode="HTML")

