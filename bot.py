import os
import asyncio
import threading
import time

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
    raise RuntimeError("❌ API_ID غير موجود في Environment Variables")

if not API_HASH:
    raise RuntimeError("❌ API_HASH غير موجود في Environment Variables")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN غير موجود في Environment Variables")


# =========================================================
# TELEGRAM BOT
# =========================================================

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)


# =========================================================
# TELETHON EVENT LOOP
# =========================================================

telegram_loop = asyncio.new_event_loop()


def telegram_worker():

    asyncio.set_event_loop(
        telegram_loop
    )

    telegram_loop.run_forever()


telegram_thread = threading.Thread(
    target=telegram_worker,
    daemon=True
)

telegram_thread.start()


# =========================================================
# USER SESSION
# =========================================================

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
# SECURITY
# =========================================================

ADMIN_ID = None


# =========================================================
# LOGIN STATE
# =========================================================

phone_number = None

waiting_phone = False
waiting_code = False
waiting_password = False


# =========================================================
# TELETHON CONNECTION
# =========================================================

async def connect_client():

    if not client.is_connected():

        await client.connect()


# =========================================================
# CHECK LOGIN
# =========================================================

async def is_logged_in():

    await connect_client()

    return await client.is_user_authorized()


# =========================================================
# SEND LOGIN CODE
# =========================================================

async def send_login_code(phone):

    await connect_client()

    return await client.send_code_request(
        phone
    )


# =========================================================
# LOGIN WITH CODE
# =========================================================

async def login_with_code(
    phone,
    code
):

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


# =========================================================
# LOGIN WITH 2FA
# =========================================================

async def login_with_password(
    password
):

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
# CHECK ADMIN / CREATOR
# =========================================================

async def is_admin_or_creator(entity):

    try:

        me = await client.get_me()

        participant = await client.get_participant(
            entity,
            me
        )

        # صاحب / منشئ المجموعة
        if isinstance(
            participant,
            ChannelParticipantCreator
        ):

            return True

        # مشرف / أدمن
        if isinstance(
            participant,
            ChannelParticipantAdmin
        ):

            return True

        return False

    except Exception as e:

        print(
            f"Could not check permissions: {e}"
        )

        # حماية إضافية:
        # إذا لم نستطع معرفة الصلاحية
        # لا نخرج الحساب من المجموعة.
        return True


# =========================================================
# ANALYZE GROUPS
# =========================================================

async def analyze_groups():

    await connect_client()

    dialogs = await client.get_dialogs()

    total = 0
    normal = 0
    protected = 0

    normal_groups = []
    protected_groups = []

    for dialog in dialogs:

        if not dialog.is_group:
            continue

        total += 1

        title = dialog.name or "بدون اسم"

        is_protected = await is_admin_or_creator(
            dialog.entity
        )

        if is_protected:

            protected += 1

            protected_groups.append(
                {
                    "entity": dialog.entity,
                    "title": title
                }
            )

        else:

            normal += 1

            normal_groups.append(
                {
                    "entity": dialog.entity,
                    "title": title
                }
            )

    return {
        "total": total,
        "normal": normal,
        "protected": protected,
        "normal_groups": normal_groups,
        "protected_groups": protected_groups
    }


# =========================================================
# LEAVE NORMAL GROUPS
# =========================================================

async def leave_normal_groups():

    data = await analyze_groups()

    success = 0
    failed = 0

    left_names = []
    failed_names = []

    for group in data["normal_groups"]:

        entity = group["entity"]
        title = group["title"]

        try:

            await client.delete_dialog(
                entity
            )

            success += 1

            left_names.append(
                title
            )

            print(
                f"LEFT: {title}"
            )

            await asyncio.sleep(1)

        except FloodWaitError as e:

            print(
                f"FloodWait: {e.seconds} seconds"
            )

            await asyncio.sleep(
                e.seconds
            )

            try:

                await client.delete_dialog(
                    entity
                )

                success += 1

                left_names.append(
                    title
                )

            except Exception as retry_error:

                failed += 1

                failed_names.append(
                    title
                )

                print(
                    f"FAILED AFTER RETRY: {title} | {retry_error}"
                )

        except Exception as e:

            failed += 1

            failed_names.append(
                title
            )

            print(
                f"FAILED: {title} | {e}"
            )

    return {
        "total": data["total"],
        "normal": data["normal"],
        "protected": data["protected"],
        "success": success,
        "failed": failed,
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
            "🚪 خروج من كروبات الأعضاء",
            callback_data="leave"
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
            "🚨 نعم، اخرج من كروبات الأعضاء",
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
# /START
# =========================================================

@bot.message_handler(
    commands=["start"]
)
def start(message):

    global ADMIN_ID
    global waiting_phone

    user_id = message.from_user.id

    # أول مستخدم يصبح المستخدم المسموح له
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
            f"""
❌ خطأ في الاتصال بحساب Telegram:

<code>{e}</code>
"""
        )

        return

    if not logged_in:

        waiting_phone = True

        bot.send_message(
            message.chat.id,
            """
🔐 <b>تسجيل الدخول</b>

أرسل رقم هاتف حساب Telegram الذي تريد إدارة كروباته.

مثال:

<code>+905xxxxxxxxx</code>
"""
        )

        return

    bot.send_message(
        message.chat.id,
        """
🤖 <b>مدير الكروبات</b>

الحساب الشخصي متصل بنجاح.

🛡️ <b>لن يتم الخروج من:</b>

👑 المجموعات التي أنت منشئها
🛡️ المجموعات التي أنت مشرف/أدمن فيها

🚪 <b>سيتم الخروج فقط من:</b>

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
📩 <b>تم إرسال كود Telegram</b>

أرسل الكود الذي وصلك.
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
                """
✅ <b>تم تسجيل الدخول بنجاح</b>
""",
                reply_markup=main_keyboard()
            )

        elif result == "PASSWORD":

            waiting_code = False
            waiting_password = True

            bot.send_message(
                message.chat.id,
                """
🔐 حسابك يستخدم التحقق بخطوتين.

أرسل كلمة مرور Telegram.
"""
            )

        else:

            bot.send_message(
                message.chat.id,
                f"""
❌ فشل تسجيل الدخول:

<code>{result}</code>
"""
            )

        return

    # =====================================================
    # 2FA
    # =====================================================

    if waiting_password:

        result = run_async(
            login_with_password(
                text
            )
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
❌ كلمة المرور غير صحيحة:

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

    bot.answer_callback_query(
        call.id
    )

    # =====================================================
    # CHECK
    # =====================================================

    if call.data == "check":

        try:

            data = run_async(
                analyze_groups()
            )

            bot.edit_message_text(
                f"""
📊 <b>نتيجة الفحص</b>

👥 إجمالي الكروبات:
<b>{data["total"]}</b>

👤 عضو عادي:
<b>{data["normal"]}</b>

🛡️ مشرف/أدمن أو منشئ:
<b>{data["protected"]}</b>

✅ المشرف والمنشئ لن يتم الخروج منهما.
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

        except Exception as e:

            bot.edit_message_text(
                f"""
❌ حدث خطأ:

<code>{e}</code>
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

    # =====================================================
    # LEAVE
    # =====================================================

    elif call.data == "leave":

        try:

            data = run_async(
                analyze_groups()
            )

            if data["normal"] == 0:

                bot.edit_message_text(
                    f"""
✅ <b>لا يوجد كروبات عضو عادي فيها.</b>

👥 إجمالي الكروبات:
<b>{data["total"]}</b>

🛡️ المحمية:
<b>{data["protected"]}</b>
""",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=main_keyboard()
                )

                return

            bot.edit_message_text(
                f"""
⚠️ <b>تأكيد العملية</b>

👤 كروبات سيتم الخروج منها:
<b>{data["normal"]}</b>

🛡️ كروبات سيتم الحفاظ عليها:
<b>{data["protected"]}</b>

👑 المنشئ محفوظ.
🛡️ المشرف محفوظ.

هل تريد المتابعة؟
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=confirm_keyboard()
            )

        except Exception as e:

            bot.edit_message_text(
                f"""
❌ حدث خطأ:

<code>{e}</code>
""",
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
🚪 <b>جاري الفحص...</b>

سيتم الخروج فقط من المجموعات التي أنت فيها كعضو عادي.

🛡️ المنشئ والمشرف لن يتم لمسهم.
""",
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
<b>{result["success"]}</b>

🛡️ تم الحفاظ على:
<b>{result["protected"]}</b>

❌ فشل:
<b>{result["failed"]}</b>

👑 كروبات المنشئ محفوظة.
🛡️ كروبات المشرف محفوظة.
""",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_keyboard()
            )

        except Exception as e:

            bot.edit_message_text(
                f"""
❌ حدث خطأ أثناء الخروج:

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
# DELETE WEBHOOK
# =========================================================

print("🧹 Removing Telegram webhook...")

try:

    bot.remove_webhook()

    time.sleep(2)

    print("✅ Webhook removed.")

except Exception as e:

    print(
        f"⚠️ Could not remove webhook: {e}"
    )


# =========================================================
# START BOT
# =========================================================

print("🤖 Bot is running...")

bot.infinity_polling(
    skip_pending=True,
    timeout=60,
    long_polling_timeout=60
            )
