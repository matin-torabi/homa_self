import re
from telethon import events
from config import supabase
from utils import db_execute  # اجرای غیرهمزمان کوئری‌های sync سوپابیس در thread pool

# لیست آیدی‌های مجاز برای اجرای دستورات ادمینی
ALLOWED_ADMINS = {8004897709, 8668275780, 1632503299}

def is_admin(sender_id):
    return sender_id in ALLOWED_ADMINS

async def get_user_diamonds(user_id: int) -> int:
    try:
        query = supabase.table("users_diamonds").select("diamonds").eq("user_id", user_id)
        res = await db_execute(query)
        return res.data[0]["diamonds"] if res.data else 0
    except Exception as e:
        print(f"Error getting diamonds for {user_id}: {e}")
        return 0

async def update_diamonds(user_id: int, amount: int):
    try:
        current = await get_user_diamonds(user_id)
        new_balance = max(0, current + amount)
        query = supabase.table("users_diamonds").upsert({"user_id": user_id, "diamonds": new_balance})
        await db_execute(query)
        return new_balance
    except Exception as e:
        print(f"Error updating diamonds for {user_id}: {e}")
        return None


def register_admin_handlers(bot):
    """ثبت هندلرهای سلف‌بات (با قابلیت ادیت روی پیام ادمین)"""

    # 🏆 ۱. دستور نمایش رنکینگ برتر با ادیت پیام: *رنکینگ
    @bot.on(events.NewMessage(outgoing=True, pattern=r'^\*رنکینگ$'))
    async def show_admin_ranking(event):
        # بررسی دسترسی ادمین
        if not is_admin(event.sender_id):
            return

        try:
            # تغییر limit از 10 به 15 برای نمایش 15 نفر برتر
            query = supabase.table("rps_rankings")\
                          .select("*")\
                          .order("wins_count", desc=True)\
                          .limit(15)
            res = await db_execute(query)
            
            if not res.data:
                await event.edit("📭 هنوز هیچ اطلاعاتی در جدول رنکینگ ثبت نشده است.")
                return
            
            lines = ["🏆 **جدول ۱۵ نفر برتر بازی سنگ، کاغذ، قیچی** 🏆\n"]
            for i, row in enumerate(res.data, 1):
                # استفاده از نام کاربری یا آیدی برای نمایش تمیزتر
                name = row.get('username', 'کاربر ناشناس')
                wins = row.get('wins_count', 0)
                lines.append(f"🏅 {i}. {name} (`{row['user_id']}`) ➔ **{wins} برد**")
                
            # ادیت پیام دستور به لیست رنکینگ
            await event.edit("\n".join(lines))
            
        except Exception as e:
            await event.edit("❌ خطا در دریافت اطلاعات رنکینگ از سوپابیس!")
            print(f"Error in ranking: {e}")


    @bot.on(events.NewMessage(outgoing=True, pattern=r'^\*پاکسازی رنک$'))
    async def reset_all_rankings(event):
        # فقط ادمین‌های لیست مجاز باشند
        if not is_admin(event.sender_id):
            return

        try:
            query = supabase.table("rps_rankings")\
                        .update({"wins_count": 0})\
                        .neq("wins_count", -1)
            await db_execute(query)
            
            await event.edit("✅ **پاکسازی انجام شد!**\n\nتمام رکوردها در جدول با موفقیت صفر شدند.")
            
        except Exception as e:
            await event.edit("❌ خطا در اجرای دستور پاکسازی!")
            print(f"Error resetting rankings: {e}")

    # 🪙 ۲. دستور کسر   با ریپلای و ادیت پیام: *کسر طلا [عدد]
    @bot.on(events.NewMessage(incoming=False, pattern=r'^\*کسر طلا\s+(\d+)$'))
    async def deduct_user_diamonds(event):
        if not is_admin(event.sender_id):
            return

        # بررسی اینکه آیا پیام روی شخص دیگری ریپلای شده است یا خیر
        if not event.is_reply:
            await event.edit("⚠️ لطفاً این دستور را با ریپلای روی پیام کاربر مورد نظر ارسال کنید!")
            return

        try:
            amount_to_deduct = int(event.pattern_match.group(1))
            
            # دریافت اطلاعات پیام ریپلای شده برای پیدا کردن آیدی کاربر هدف
            reply_msg = await event.get_reply_message()
            target_user_id = reply_msg.sender_id
            
            if not target_user_id:
                await event.edit("❌ موفق به دریافت آیدی کاربر از روی ریپلای نشدم.")
                return

            # کسر طلا از دیتابیس
            new_balance = await update_diamonds(target_user_id, -amount_to_deduct)
            
            if new_balance is not None:
                # دریافت نام کاربر هدف از تلگرام
                try:
                    target_user = await bot.get_entity(target_user_id)
                    target_name = f"@{target_user.username}" if target_user.username else (target_user.first_name or "کاربر")
                except Exception:
                    target_name = f"کاربر ({target_user_id})"
                
                # 🔄 پیام کسر طلا ادیت میشه و نتیجه نهایی رو نشون میده
                await event.edit(
                    f"✅ مقدار `{amount_to_deduct}` طلا از حساب {target_name} کسر شد.\n"
                    f" موجودی جدید کاربر: `{new_balance}`"
                )
            else:
                await event.edit("❌ مشکلی در اتصال یا به‌روزرسانی دیتابیس به وجود آمد.")

        except Exception as e:
            await event.edit("❌ خطایی در فرآیند کسر طلا رخ داد!")
            print(e)