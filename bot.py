import os
import time
import asyncio
import threading

import telebot
from telebot import types
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError


# =========================================================
# CONFIG
# =========================================================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not API_ID:
    raise RuntimeError("API_ID غير موجود")

if not API_HASH:
    raise RuntimeError("API_HASH غير موجود")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN غير موجود")


# =========================================================
# BOT
# =========================================================

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)


# =========================================================
# TELETHON LOOP
# =========================================================

telegram_loop = asyncio.new_event_loop()


def telegram_worker():
    asyncio.set_event_loop(telegram_loop)
    telegram_loop.run_forever()


threading.Thread(
    target=telegram_worker,
    daemon=True
).start()


client = TelegramClient(
    "user_session",
    API_ID,
    API_HASH
)


def run_async(coro):
    future = asyncio.run_coroutine_threadsafe(
        coro,
        telegram_loop
    )

    return future.result()


# =========================================================
# AUTH STATE
# =========================================================

ADMIN_ID = None

phone_number = None

waiting_phone = False
waiting_code = False
waiting_password = False


# =========================================================
# TELEGRAM FUNCTIONS
# =========================================================

async def connect_client():

    if not client.is_connected():
        await client.connect()


async def is_logged_in():

    await connect_client()

    return await client.is_user_authorized()


async def send_login_code(phone):

    await connect_client()

    return await client.send_code_request(phone)


async def login_code(phone, code):

    try:

        await client.sign_in(
            phone=phone,
            code=code
        )

        return "OK"

    except SessionPasswordNeededError:

        return "PASSWORD"

    except Exception as e:

        return f"ERROR:{e}"


async def login_password(password):

    try:

        await client.sign_in(
            password=password
        )

        return "OK"

    except Exception as e:

        return f"ERROR:{e}"


async def get_all_groups():

    await connect_client()

    dialogs = await client.get_dialogs()

    groups = []

    for dialog in dialogs:

        # المجموعات فقط
        if dialog.is_group:

            groups.append(dialog)

    return groups


async def leave_all_groups():

    await connect_client()

    dialogs = await client.get_dialogs()

    groups = [
        dialog
        for dialog in dialogs
        if dialog.is_group
    ]

    success = 0
    failed = 0

    results = []

    for dialog in groups:

        try:

            title = dialog.name or "بدون اسم"

            await client.delete_dialog(
                dialog.entity
            )

            success += 1

            results.append(
                f"✅ {title}"
            )

            # تأخير بسيط
            await asyncio.sleep(1)

        except FloodWaitError as e:

            wait_time = e.seconds

            results.append(
                f"⏳ FloodWait: انتظار {wait_time} ثانية"
            )

            await asyncio.sleep(
                wait_time
            )

            try:

                await client.delete_dialog(
                    dialog.entity
                )

                success += 1

            except Exception:

                failed += 1

        except Exception as e:

            failed += 1

            results.append(
                f"❌ {dialog.name}: {e}"
            )

    return success, failed, results


# =========================================================
# KEYBOARD
# =========================================================

def main_keyboard():

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "🚨 خروج من جميع الكروبات",
            callback_data="leave_all"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📊 عدد الكروبات",
            callback_data="count"
        )
    )

    return keyboard


def confirm_keyboard():

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(
            "🚨 نعم، اخرج من الكل",
            callback_data="confirm_leave_all"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "❌ إلغاء",
            callback_data="cancel"
        )
    )

    return keyboard


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):

    global ADMIN_ID
    global waiting_phone

    user_id = message.from_user.id

    # أول مستخدم يصبح الأدمن
    if ADMIN_ID is None:
        ADMIN_ID = user_id

    if user_id != ADMIN_ID:

        bot.reply_to(
            message,
            "⛔ غير مسموح لك باستخدام هذا البوت."
        )

        return

    try:

        logged_in = run_async(
            is_logged_in()
        )

    except Exception as e:

        bot.send_message(
            message.chat.id,
            f"❌ خطأ في الاتصال:\n<code>{e}</code>"
        )

        return

    if not logged_in:

        waiting_phone = True

        bot.send_message(
            message.chat.id,
            """
🔐 <b>تسجيل حساب Telegram</b>

أرسل رقم هاتف الحساب الذي تريد إخراجه من الكروبات.

مثال:

<code>+905xxxxxxxxx</code>
"""
        )

        return

    bot.send_message(
        message.chat.id,
        """
🤖 <b>مدير الكروبات</b>

حسابك متصل بنجاح.

اختر العملية:
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# TEXT
# =========================================================

@bot.message_handler(content_types=["text"])
def text_handler(message):

    global phone_number
    global waiting_phone
    global waiting_code
    global waiting_password

    if ADMIN_ID is None:
        return

    if message.from_user.id != ADMIN_ID:
        return

    text = message.text.strip()

    # =====================================================
    # PHONE
    # =====================================================

    if waiting_phone:

        phone_number = text

        try:

            run_async(
                send_login_code(phone_number)
            )

            waiting_phone = False
            waiting_code = True

            bot.send_message(
                message.chat.id,
                """
📩 <b>تم إرسال الكود</b>

أرسل كود تسجيل الدخول الذي وصلك من Telegram.
"""
            )

        except Exception as e:

            bot.send_message(
                message.chat.id,
                f"""
❌ لم أستطع إرسال الكود.

<code>{e}</code>
"""
            )

        return

    # =====================================================
    # CODE
    # =====================================================

    if waiting_code:

        result = run_async(
            login_code(
                phone_number,
                text
            )
        )

        if result == "OK":

            waiting_code = False

            bot.send_message(
                message.chat.id,
                """
✅ <b>تم تسجيل الدخول</b>

يمكنك الآن التحكم بالحساب.
""",
                reply_markup=main_keyboard()
            )

        elif result == "PASSWORD":

            waiting_code = False
            waiting_password = True

            bot.send_message(
                message.chat.id,
                """
🔐 حسابك محمي بالتحقق بخطوتين.

أرسل كلمة مرور Telegram.
"""
            )

        else:

            bot.send_message(
                message.chat.id,
                f"""
❌ الكود غير صحيح.

<code>{result}</code>
"""
            )

        return

    # =====================================================
    # 2FA PASSWORD
    # =====================================================

    if waiting_password:

        result = run_async(
            login_password(text)
        )

        if result == "OK":

            waiting_password = False

            bot.send_message(
                message.chat.id,
                """
✅ <b>تم تسجيل الدخول بنجاح</b>
""",
                reply_markup=main_keyboard()
            )

        else:

            bot.send_message(
                message.chat.id,
                f"""
❌ كلمة المرور غير صحيحة.

<code>{result}</code>
"""
            )

        return


# =========================================================
# CALLBACK
# =========================================================

@bot.callback_query_handler(
    func=lambda call: True
)
def callback_handler(call):

    if ADMIN_ID is None:
        return

    if call.from_user.id != ADMIN_ID:

        bot.answer_callback_query(
            call.id,
            "⛔ غير مسموح",
            show_alert=True
        )

        return

    bot.answer_callback_query(call.id)

    # =====================================================
    # LEAVE ALL
    # =====================================================

    if call.data == "leave_all":

        try:

            groups = run_async(
                get_all_groups()
            )

            count = len(groups)

        except Exception as e:

            bot.edit_message_text(
                f"❌ خطأ:\n<code>{e}</code>",
                call.message.chat.id,
                call.message.message_id
            )

            return

        if count == 0:

            bot.edit_message_text(
                """
📭 <b>لا يوجد كروبات</b>

حسابك لا يوجد فيه أي مجموعة.
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

            return

        bot.edit_message_text(
            f"""
⚠️ <b>تحذير</b>

تم العثور على:

<b>{count}</b> كروب

إذا أكدت، سيخرج حسابك الشخصي من <b>جميع الكروبات</b>.

هذه العملية لا يمكن التراجع عنها تلقائيًا.
""",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=confirm_keyboard()
        )

    # =====================================================
    # CONFIRM
    # =====================================================

    elif call.data == "confirm_leave_all":

        bot.edit_message_text(
            """
🚪 <b>جاري الخروج من الكروبات...</b>

يرجى الانتظار.
""",
            call.message.chat.id,
            call.message.message_id
        )

        try:

            success, failed, results = run_async(
                leave_all_groups()
            )

            bot.edit_message_text(
                f"""
✅ <b>اكتملت العملية</b>

🚪 خرج من الكروبات:
<b>{success}</b>

❌ فشل:
<b>{failed}</b>

📌 القنوات والمحادثات الخاصة لم يتم لمسها.
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

        except Exception as e:

            bot.edit_message_text(
                f"""
❌ حدث خطأ أثناء العملية:

<code>{e}</code>
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

    # =====================================================
    # COUNT
    # =====================================================

    elif call.data == "count":

        try:

            groups = run_async(
                get_all_groups()
            )

            count = len(groups)

            bot.edit_message_text(
                f"""
📊 <b>إحصائيات الحساب</b>

👥 عدد الكروبات:
<b>{count}</b>
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

        except Exception as e:

            bot.edit_message_text(
                f"❌ خطأ:\n<code>{e}</code>",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

    # =====================================================
    # CANCEL
    # =====================================================

    elif call.data == "cancel":

        bot.edit_message_text(
            """
❌ <b>تم إلغاء العملية</b>
""",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_keyboard()
        )


# =========================================================
# RUN
# =========================================================

print("🤖 Bot started...")

bot.infinity_polling(
    skip_pending=True
  )
