import os
import asyncio
import threading

import telebot
from telebot import types

from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError
)
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantCreator
)


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
# TELETHON
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


async def login_with_code(phone, code):

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


async def login_with_password(password):

    try:

        await client.sign_in(
            password=password
        )

        return "OK"

    except Exception as e:

        return f"ERROR:{e}"


# =========================================================
# GET GROUPS
# =========================================================

async def get_groups():

    await connect_client()

    dialogs = await client.get_dialogs()

    groups = []

    for dialog in dialogs:

        if dialog.is_group:

            groups.append(dialog)

    return groups


# =========================================================
# CHECK IF USER IS ADMIN / CREATOR
# =========================================================

async def is_admin_or_creator(entity):

    try:

        me = await client.get_me()

        participant = await client.get_participant(
            entity,
            me
        )

        # منشئ المجموعة
        if isinstance(
            participant,
            ChannelParticipantCreator
        ):
            return True

        # أدمن / مشرف
        if isinstance(
            participant,
            ChannelParticipantAdmin
        ):
            return True

        return False

    except Exception:

        # إذا تعذر معرفة الصلاحية
        # نعتبره عضوًا عاديًا للحذر من تركه
        return False


# =========================================================
# LEAVE NORMAL MEMBER GROUPS
# =========================================================

async def leave_normal_groups():

    await connect_client()

    dialogs = await client.get_dialogs()

    total_groups = 0
    protected_groups = 0
    left_groups = 0
    failed_groups = 0

    protected_names = []
    left_names = []
    failed_names = []

    for dialog in dialogs:

        # المجموعات فقط
        if not dialog.is_group:
            continue

        total_groups += 1

        title = dialog.name or "بدون اسم"

        # -----------------------------------------
        # CHECK ADMIN / CREATOR
        # -----------------------------------------

        protected = await is_admin_or_creator(
            dialog.entity
        )

        if protected:

            protected_groups += 1

            protected_names.append(
                title
            )

            continue

        # -----------------------------------------
        # LEAVE
        # -----------------------------------------

        try:

            await client.delete_dialog(
                dialog.entity
            )

            left_groups += 1

            left_names.append(
                title
            )

            # تأخير بسيط
            await asyncio.sleep(1)

        except FloodWaitError as e:

            try:

                await asyncio.sleep(
                    e.seconds
                )

                await client.delete_dialog(
                    dialog.entity
                )

                left_groups += 1

                left_names.append(
                    title
                )

            except Exception:

                failed_groups += 1

                failed_names.append(
                    title
                )

        except Exception:

            failed_groups += 1

            failed_names.append(
                title
            )

    return {
        "total": total_groups,
        "protected": protected_groups,
        "left": left_groups,
        "failed": failed_groups,
        "protected_names": protected_names,
        "left_names": left_names,
        "failed_names": failed_names
    }


# =========================================================
# MAIN KEYBOARD
# =========================================================

def main_keyboard():

    keyboard = types.InlineKeyboardMarkup(
        row_width=1
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📊 فحص الكروبات",
            callback_data="check"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🚪 خروج من كروبات العضو العادي",
            callback_data="leave_normal"
        )
    )

    return keyboard


# =========================================================
# CONFIRM KEYBOARD
# =========================================================

def confirm_keyboard():

    keyboard = types.InlineKeyboardMarkup(
        row_width=1
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🚨 نعم، نفّذ الخروج",
            callback_data="confirm_leave"
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

    # أول شخص يشغل البوت يصبح المسموح له
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
            f"❌ خطأ:\n<code>{e}</code>"
        )

        return

    if not logged_in:

        waiting_phone = True

        bot.send_message(
            message.chat.id,
            """
🔐 <b>تسجيل حساب Telegram</b>

أرسل رقم هاتف الحساب الذي تريد إدارته.

مثال:

<code>+905xxxxxxxxx</code>
"""
        )

        return

    bot.send_message(
        message.chat.id,
        """
🤖 <b>مدير الكروبات</b>

الحساب الشخصي متصل.

سيتم الحفاظ على:
👑 المجموعات التي أنت منشئها
🛡️ المجموعات التي أنت مشرف/أدمن فيها

وسيتم الخروج من:
👤 المجموعات التي أنت عضو عادي فيها
""",
        reply_markup=main_keyboard()
    )


# =========================================================
# TEXT HANDLER
# =========================================================

@bot.message_handler(
    content_types=["text"]
)
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
                send_login_code(
                    phone_number
                )
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
❌ فشل إرسال الكود:

<code>{e}</code>
"""
            )

        return

    # =====================================================
    # CODE
    # =====================================================

    if waiting_code:

        result = run_async(
            login_with_code(
                phone_number,
                text
            )
        )

        if result == "OK":

            waiting_code = False

            bot.send_message(
                message.chat.id,
                "✅ تم تسجيل الدخول بنجاح.",
                reply_markup=main_keyboard()
            )

        elif result == "PASSWORD":

            waiting_code = False
            waiting_password = True

            bot.send_message(
                message.chat.id,
                """
🔐 الحساب محمي بالتحقق بخطوتين.

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
    # 2FA
    # =====================================================

    if waiting_password:

        result = run_async(
            login_with_password(text)
        )

        if result == "OK":

            waiting_password = False

            bot.send_message(
                message.chat.id,
                "✅ تم تسجيل الدخول بنجاح.",
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
# CALLBACK HANDLER
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
    # CHECK
    # =====================================================

    if call.data == "check":

        try:

            groups = run_async(
                get_groups()
            )

            normal = 0
            protected = 0

            for dialog in groups:

                if run_async(
                    is_admin_or_creator(
                        dialog.entity
                    )
                ):
                    protected += 1
                else:
                    normal += 1

            bot.edit_message_text(
                f"""
📊 <b>نتيجة الفحص</b>

👥 مجموع الكروبات:
<b>{len(groups)}</b>

👤 عضو عادي:
<b>{normal}</b>

🛡️ مشرف/أدمن أو منشئ:
<b>{protected}</b>

✅ المشرف والمنشئ لن يتم الخروج منهما.
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
    # LEAVE NORMAL
    # =====================================================

    elif call.data == "leave_normal":

        try:

            groups = run_async(
                get_groups()
            )

            normal = 0
            protected = 0

            for dialog in groups:

                if run_async(
                    is_admin_or_creator(
                        dialog.entity
                    )
                ):
                    protected += 1
                else:
                    normal += 1

            if normal == 0:

                bot.edit_message_text(
                    f"""
✅ <b>لا يوجد كروبات للخروج منها.</b>

👥 إجمالي الكروبات: {len(groups)}
🛡️ المحمية: {protected}
""",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=main_keyboard()
                )

                return

            bot.edit_message_text(
                f"""
⚠️ <b>تأكيد العملية</b>

👤 كروبات العضو العادي:
<b>{normal}</b>

🛡️ كروباتك كمنشئ/مشرف:
<b>{protected}</b>

الكروبات التي أنت فيها كمنشئ أو مشرف <b>لن يتم لمسها</b>.

هل تريد المتابعة؟
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=confirm_keyboard()
            )

        except Exception as e:

            bot.edit_message_text(
                f"❌ خطأ:\n<code>{e}</code>",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

    # =====================================================
    # CONFIRM
    # =====================================================

    elif call.data == "confirm_leave":

        bot.edit_message_text(
            """
🚪 <b>جاري فحص الكروبات والخروج من كروبات العضو العادي...</b>

🛡️ المشرف والمنشئ سيتم الحفاظ عليهم.
"""
        ,
            call.message.chat.id,
            call.message.message_id
        )

        try:

            result = run_async(
                leave_normal_groups()
            )

            bot.edit_message_text(
                f"""
✅ <b>اكتملت العملية</b>

👥 إجمالي الكروبات:
<b>{result["total"]}</b>

🚪 تم الخروج من:
<b>{result["left"]}</b>

🛡️ تم الحفاظ على:
<b>{result["protected"]}</b>

❌ فشل الخروج من:
<b>{result["failed"]}</b>

👑 المنشئ والمشرف لم يتم الخروج منهم.
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
    # CANCEL
    # =====================================================

    elif call.data == "cancel":

        bot.edit_message_text(
            """
❌ <b>تم إلغاء العملية.</b>
""",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=main_keyboard()
        )


# =========================================================
# RUN
# =========================================================

print("🤖 Bot is running...")

bot.infinity_polling(
    skip_pending=True
            )
