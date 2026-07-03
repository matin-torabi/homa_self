import asyncio
from email.mime import text
import random
from turtle import update
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
# HANDLE GAME REQUEST
# =========================================
async def handle_game_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر شروع بازی وقتی کسی پیام 'بازی' یا 'بازی 50 طلا' می‌فرستد"""
    message_text = update.message.text
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    user_mention = get_user_mention(user)


    amount = 50 # پیش‌فرض
    words = message_text.split()
    for word in words:
        if word.isdigit():
            amount = int(word)
            break
            
    # ⚡ اضافه کردن شرط حداقل ۳۰ طلا
    if amount < 30:
        await update.message.reply_text("⚠️ حداقل مبلغ شرط برای بازی 30 طلا می‌باشد.")
        return

    # ۱. بررسی موجودی سازنده بازی از سوپابیس
    creator_bal = get_balance(user.id)
    if creator_bal < amount:
        await update.message.reply_text(
            f"❌ {user_mention} طلای شما برای این بازی کافی نیست!\n"
            f"💰 موجودی شما: <code>{creator_bal:,}</code> طلا",
            parse_mode="HTML"
        )
        return

    # ۲. کسر طلا از سازنده به صورت موقت در سوپابیس
    update_balance(user.id, -amount)
    
    # ۳. ذخیره بازی در دیتابیس سوپابیس (جدول active_games)
    game_id = update.message.message_id
    game_data = {
        "creator_id": user.id,
        "creator_name": user.first_name,
        "creator_mention": user_mention,
        "player_2_id": None,
        "player_2_name": None,
        "player_2_mention": None,
        "amount": amount,
        "status": "waiting",
        "chat_id": chat_id
    }
    await save_game(game_id, game_data)

    keyboard = [
            [InlineKeyboardButton("✅ قبول", callback_data=f"join_{game_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data=f"cancel_{game_id}")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ۵. ارسال متن فرم بازی (فقط متنی - بدون عکس)
    text = (
        f"🎲 <b>Homa selfbot Game</b>\n\n"
        f"💰 مقدار طلای بازی: <b>{amount:,}</b> طلا\n"
        f"👤 سازنده بازی: {user_mention} (<code>{user.id}</code>)\n\n"
        f"👇 برای پیوستن روی دکمه <b>قبول</b> کلیک کنید."
    )
    
    # ارسال فقط متن
    await update.message.reply_text(
        text=text, 
        reply_markup=reply_markup, 
        parse_mode="HTML"
    )

# =========================================
# GAME BUTTONS CALLBACK
# =========================================
async def game_buttons_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت دکمه‌های قبول و لغو با پوشش کامل خطاهای زمان‌بندی"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    user_mention = get_user_mention(user)

    action, game_id = data.rsplit("_", 1)
    game = await get_game(game_id)

    if not game:
        try:
            await query.answer("❌ این بازی دیگر وجود ندارد یا منقضی شده است.", show_alert=True)
            await query.message.delete()
        except Exception:
            pass
        return

    # 🛑 حالت اول: کلیک روی دکمه لغو
    if action == "cancel":
        if user.id != game["creator_id"]:
            try:
                await query.answer(
                    "سلف ساز هوما | homa self\n\nفقط سازنده بازی می‌تواند لغو کند", 
                    show_alert=True
                )
            except Exception:
                pass
            return
        
        # بازگرداندن طلا به موجودی سازنده در سوپابیس
        update_balance(game["creator_id"], game["amount"])
        await delete_game(game_id)
        try:
            await query.answer("❌ بازی لغو شد و طلای شما بازگشت.")
            await query.message.delete()
        except Exception:
            pass
        return

    # 🤝 حالت دوم: کلیک روی دکمه قبول 
    if action == "join":
        if user.id == game["creator_id"]:
            try:
                await query.answer(
                    "سلف ساز هوما | homa self\n\nبا خودت نمیتونی بازی کنی", 
                    show_alert=True
                )
            except Exception:
                pass
            return

        if game["status"] != "waiting":
            try:
                await query.answer(
                    "سلف ساز هوما | homa self\n\nاین بازی قبلاً شروع شده یا پر است.", 
                    show_alert=True
                )
            except Exception:
                pass
            return

        # بررسی موجودی نفر دوم از سوپابیس
        player_bal = get_balance(user.id)
        if player_bal < game["amount"]:
            try:
                await query.answer(
                    f"سلف ساز هوما | homa self\n\nطلای شما کافی نیست!\n💰 موجودی شما: {player_bal:,} طلا", 
                    show_alert=True
                )
            except Exception:
                pass
            return

        try:
            await query.answer("🎲 وارد بازی شدید! در حال چرخاندن تاس...")
        except Exception:
            pass

        # کسر طلا از بازیکن دوم در سوپابیس
        update_balance(user.id, -game["amount"])
        game["player_2_id"] = user.id
        game["player_2_name"] = user.first_name
        game["player_2_mention"] = user_mention
        game["status"] = "rolling"
        await save_game(game_id, game)

        # 🔄 انیمیشن چرخیدن تاس‌ها
        dice_emojis = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
        last_text = ""

        for _ in range(3):
            frame_emoji1 = random.choice(dice_emojis)
            frame_emoji2 = random.choice(dice_emojis)
            
            current_text = (
                f"👤 سازنده: {game['creator_mention']} [ {frame_emoji1} ]\n"
                f"👤 بازیکن: {user_mention} [ {frame_emoji2} ]\n\n"
                f"🔄 <b>تاس در حال چرخیدن است... 🔄</b>"
            )
            
            if current_text != last_text:
                try:
                    await query.edit_message_caption(caption=current_text, parse_mode="HTML")
                    last_text = current_text
                except telegram.error.BadRequest as e:
                    if "Message is not modified" in str(e):
                        pass
                    else:
                        break
                except Exception:
                    break
            
            await asyncio.sleep(0.6)

        # محاسبات نهایی تاس
        dice_1 = random.randint(1, 6)
        dice_2 = random.randint(1, 6)
        # حذف حلقه while dice_1 == dice_2 (چون تساوی در تاس با تاس ریختن واقعی ممکن است 
        # و اگر می‌خواهید حتما برنده داشته باشید، می‌توانید نگهش دارید)

        total_prize = game["amount"] * 2

        if dice_1 > dice_2:
            winner_id = game["creator_id"]
            winner_mention = game["creator_mention"]
            loser_mention = game["player_2_mention"]
        elif dice_2 > dice_1:
            winner_id = game["player_2_id"]
            winner_mention = game["player_2_mention"]
            loser_mention = game["creator_mention"]
        else:
            # حالت تساوی: بازگشت طلا به هر دو نفر
            update_balance(game["creator_id"], game["amount"])
            update_balance(game["player_2_id"], game["amount"])
            await query.edit_message_caption(caption="🤝 بازی مساوی شد! طلا به هر دو بازگشت.")
            await delete_game(game_id)
            return

        # واریز جایزه به برنده
        update_balance(winner_id, total_prize)
        await delete_game(game_id)

        result_text = (
            f"🏁 <b>نتیجه نهایی رقابت:</b>\n\n"
            f"🏆 <b>برنده:</b> {winner_mention}\n"
            f"💀 <b>بازنده:</b> {loser_mention}\n\n"
            f"🎲 تاس برنده: <b>{max(dice_1, dice_2)}</b> | تاس بازنده: <b>{min(dice_1, dice_2)}</b>\n\n"
            f"💰 جایزه <b>{total_prize:,}</b> طلا به حساب برنده واریز شد!"
        )

        try:
            await query.edit_message_caption(caption=result_text, parse_mode="HTML")
        except Exception:
            try:
                await context.bot.send_message(chat_id=game["chat_id"], text=result_text, parse_mode="HTML")
            except Exception:
                pass


# =========================================
# HANDLE BALANCE REQUEST
# =========================================
async def handle_balance_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش موجودی طلا از سوپابیس"""
    user = update.effective_user
    current_balance = get_balance(user.id)
    user_mention = get_user_mention(user)
    
    text = (
        f"👤 <b>کاربر:</b> {user_mention}\n"
        f"🆔 <b>آیدی عددی:</b> <code>{user.id}</code>\n"
        f"💰 <b>طلای شما:</b> <code>{current_balance:,}</code> طلا"
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

    from_balance = get_balance(from_user.id)
    if from_balance < amount:
        await message.reply_text(f"❌ موجودی طلای شما کافی نیست!\n💰 طلای شما: {from_balance:,} طلا")
        return

    # اعمال ترکنش در دیتابیس آنلاین سوپابیس
    update_balance(from_user.id, -amount)
    update_balance(to_user.id, amount)

    success_text = (
        f"✅ <b>واریز موفقیت‌آمیز بود!</b>\n\n"
        f"👤 <b>فرستنده:</b> {from_mention} (<code>{from_user.id}</code>)\n"
        f"👤 <b>گیرنده:</b> {to_mention} (<code>{to_user.id}</code>)\n"
        f"💰 <b>مقدار منتقل شده:</b> {amount:,} طلا\n"
        f"🔹 <b>موجودی جدید شما:</b> {get_balance(from_user.id):,} طلا"
    )
    await message.reply_text(success_text, parse_mode="HTML")

