import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler,
    MessageHandler,
    filters,
)
from datetime import datetime, timedelta

from config import BOT_TOKEN, ADMIN_ID
from database.database_operations import (
    create_tables,
    add_user_to_db,
    set_user_group_status,
    get_available_us_email,
    mark_us_email_as_sent,
    mark_us_email_as_available,
    store_user_submitted_email,
    delete_sent_us_email,
    add_email_to_stock,
    # ... دوال قاعدة البيانات الأخرى التي ستحتاجها (تأكد من وجودها)
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# حالات محادثة شحن الرصيد
RECHARGE_CHOOSING_METHOD, RECHARGE_ENTERING_AMOUNT, RECHARGE_CONFIRMING_AMOUNT, RECHARGE_ENTERING_TRANSACTION_ID, CONFIRMING_RECHARGE_INFO, SENDING_REJECTION_RECHARGE = map(
    chr, range(6)
)

# حالات محادثة بيع الإيميلات
SELL_EMAIL_CHOOSING_TYPE, SELL_US_EMAIL_WAITING_REPLY, SELL_EMAIL_ENTERING_ADDRESS, SENDING_REJECTION_REASON_US, SENDING_REJECTION_REASON_RANDOM = map(
    chr, range(5)
)

# عناوين المحافظ الصحيحة
SYRIATEL_CASH_ADDRESS = "21938770"
PAYEER_ADDRESS = "P1081677253"

# قاموس لتخزين الإيميلات الأمريكية المرسلة مؤقتًا وتواريخ إرسالها (بديل مؤقت لقاعدة البيانات)
US_EMAILS_SENT = {}  # user_id: {'email': '...', 'password': '...', 'sent_at': datetime}


async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user_to_db(user)  # إضافة المستخدم الجديد إلى قاعدة البيانات
    group_link = "https://t.me/workonline8465"
    welcome_message = (
        f"👋 مرحبًا بك يا {user.first_name} في [اسم البوت]!\n\n"
        f"للاستفادة الكاملة من البوت والحصول على الدعم والمساعدة، يرجى الانضمام إلى مجموعتنا الرسمية عبر الرابط التالي:\n\n"
        f"🔗 {group_link}\n\n"
        f"**هام:** لن يتم تفعيل حسابك بالكامل ولن تحتسب أي إحالات تقوم بها إلا بعد الانضمام إلى المجموعة.\n\n"
        f"بمجرد الانضمام، اضغط على الزر أدناه للمتابعة إلى القائمة الرئيسية."
    )
    keyboard = [[InlineKeyboardButton("✅ لقد انضممت إلى المجموعة", callback_data='joined_group')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    logging.info(f"Sent welcome message with join button to user {update.effective_user.id}")


async def joined_group_callback(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    set_user_group_status(user_id, True)
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🎉 شكرًا لك على الانضمام! إليك القائمة الرئيسية:")
    await show_main_menu(update, context)
    logging.info(f"User {user_id} pressed 'joined_group' and main menu shown.")


async def show_main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("💰 شحن رصيد", callback_data='recharge')],
        [InlineKeyboardButton("🕹️ ألعاب نسبة", callback_data='ratio_games')],
        [InlineKeyboardButton("🛒 شراء حسابات", callback_data='buy_accounts')],
        [InlineKeyboardButton("🔑 شراء بروكسيات", callback_data='buy_proxies')],
        [InlineKeyboardButton("📧 بيع ايميلات", callback_data='sell_emails')],
        [InlineKeyboardButton("💳 بيع بطاقات", callback_data='sell_cards')],
        [InlineKeyboardButton("📞 الدعم الفني", callback_data='support')],
        [InlineKeyboardButton("🎬 فيديوهات تعليمية", callback_data='educational_videos')],
        [InlineKeyboardButton("👤 رصيدي ومعلوماتي", callback_data='my_info')],
        [InlineKeyboardButton("🎮 ألعابي", callback_data='my_games')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data['main_menu_keyboard'] = reply_markup  # حفظ لوحة المفاتيح الرئيسية للرجوع
    if update.message:
        await update.message.reply_text("اختر الخدمة التي تريدها:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text("اختر الخدمة التي تريدها:", reply_markup=reply_markup)
    logging.info(f"Main menu shown to user {update.effective_user.id}.")


async def sell_emails_callback(update: Update, context: CallbackContext) -> str:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📧 بيع ايميل Gmail أمريكي", callback_data='sell_gmail_us')],
        [InlineKeyboardButton("📧 بيع ايميل Gmail عشوائي", callback_data='sell_gmail_random')],
        [InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("📤 اختر نوع إيميل Gmail الذي تود بيعه:", reply_markup=reply_markup)
    return SELL_EMAIL_CHOOSING_TYPE


async def sell_gmail_choose_type(update: Update, context: CallbackContext) -> str:
    query = update.callback_query
    await query.answer()
    if query.data == 'sell_gmail_us':
        user_id = update.effective_user.id
        available_email = get_available_us_email()  # يجب أن تعيد قاموس {'email': '...', 'password': '...'} أو None
        if available_email:
            US_EMAILS_SENT[user_id] = {
                'email': available_email['email'],
                'password': available_email['password'],
                'sent_at': datetime.now(),
            }
            mark_us_email_as_sent(available_email['email'], user_id)  # تحديث قاعدة البيانات
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"✉️ إليك إيميل أمريكي:\nالايميل: {available_email['email']}\nكلمة السر: {available_email['password']}\n\n"
                "سيتم حذف هذا الإيميل تلقائيًا وإتاحته لمستخدم آخر خلال 24 ساعة إذا لم تقم بالرد عليه.\n"
                "يرجى إرسال الإيميل وكلمة السر الجديدين اللذين تود بيعهما.",
                reply_markup=reply_markup,
            )
            return SELL_US_EMAIL_WAITING_REPLY
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID, text="⚠️ تنبيه! قائمة الإيميلات الأمريكية المتاحة فارغة. يرجى إضافة المزيد."
            )
            await query.edit_message_text(
                "⚠️ لا يوجد حاليًا أي إيميلات أمريكية متاحة للبيع. يرجى المحاولة لاحقًا.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]),
            )
            return ConversationHandler.END
    elif query.data == 'sell_gmail_random':
        await query.edit_message_text(
            "✉️ يرجى إرسال الإيميل العشوائي وكلمة السر الذي تود بيعه بالصيغة:\n\nالايميل\nكلمة السر",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]),
        )
        return SELL_EMAIL_ENTERING_ADDRESS
    elif query.data == 'main_menu':
        await show_main_menu(update, context)
        return ConversationHandler.END
    else:
        await query.edit_message_text(
            "❌ خيار غير صالح.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]])
        )
        return ConversationHandler.END


async def sell_us_email_reply(update: Update, context: CallbackContext) -> str:
    user = update.effective_user
    user_id = user.id
    reply = update.message.text.strip().split('\n')
    if len(reply) == 2:
        offered_email, offered_password = reply[0].strip(), reply[1].strip()
        sent_email_data = US_EMAILS_SENT.get(user_id)
        if sent_email_data:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📧 طلب بيع إيميل أمريكي جديد:\n"
                f"المستخدم: {user.full_name} (@{user.username})\n"
                f"الإيميل الأمريكي المرسل: {sent_email_data['email']}\n"
                f"كلمة السر المرسلة: {sent_email_data['password']}\n"
                f"الإيميل المعروض: {offered_email}\n"
                f"كلمة السر المعروضة: {offered_password}\n"
                f"المعرف: {user_id}\n"
                f"الرصيد: [رصيد المستخدم]\n\n"  # سيتم تحديثها لاحقًا
                f"خيارات:\n"
                f"/confirm_us_email {user_id} {sent_email_data['email']} {offered_email} {offered_password}\n"
                f"/reject_us_email {user_id} {sent_email_data['email']}",
            )
            store_user_submitted_email(user_id, sent_email_data['email'], offered_email, offered_password)  # حفظ البيانات
            del US_EMAILS_SENT[user_id]  # إزالة البيانات المؤقتة
            await update.message.reply_text(
                "✅ تم استلام الإيميل الذي أرسلته وسيتم إرساله للمشرف للمراجعة.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]),
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text(
                "⚠️ حدث خطأ. لم يتم العثور على الإيميل الأمريكي الذي أرسلناه لك.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]),
            )
            return ConversationHandler.END
    else:
        await update.message.reply_text(
            "⚠️ يرجى إرسال الإيميل وكلمة السر في سطرين منفصلين.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]),
        )
        return SELL_US_EMAIL_WAITING_REPLY


async def sell_email_enter_address(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    email_password = update.message.text.strip().split('\n')
    if len(email_password) == 2:
        email_address, password = email_password[0].strip(), email_password[1].strip()
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📧 طلب بيع إيميل عشوائي جديد:\n"
            f"المستخدم: {user.full_name} (@{user.username})\n"
            f"الإيميل: {email_address}\n"
            f"كلمة السر: {password}\n"
            f"المعرف: {user.id}\n"
            f"الرصيد: [رصيد المستخدم]\n\n"  # سيتم تحديثها لاحقًا
            f"خيارات:\n"
            f"/confirm_random_email {user.id} {email_address} {password}\n"
            f"/reject_random_email {user.id} {email_address}",
        )
        await update.message.reply_text(
            "✅ تم استلام الإيميل وسيتم إرساله للمشرف للمراجعة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]),
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "⚠️ يرجى إرسال الإيميل وكلمة السر في سطرين منفصلين.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='sell_emails_back')]]),
        )
        return SELL_EMAIL_ENTERING_ADDRESS


async def confirm_us_email(update: Update, context: CallbackContext):
    user_id, sent_email, offered_email, offered_password = context.args
    delete_sent_us_email(sent_email)  # حذف الإيميل الأمريكي الأصلي
    # قم بتحديث رصيد المستخدم هنا (سيتم تنفيذه لاحقًا)
    await update.message.reply_text(f"✅ تم تأكيد الإيميل الأمريكي ({offered_email}) من قبل المشرف.")
    await context.bot.send_message(chat_id=int(user_id), text="💰 تم إضافة رصيد إلى حسابك مقابل بيع الإيميل الأمريكي.")


async def reject_us_email(update: Update, context: CallbackContext):
    user_id, sent_email = context.args
    mark_us_email_as_available(sent_email)  # إتاحة الإيميل الأمريكي لإعادة الإرسال
    await update.message.reply_text(f"❌ تم رفض الإيميل الأمريكي ({sent_email}). يرجى إرسال سبب الرفض إلى المستخدم.")
    context.user_data['reject_user_id'] = int(user_id)
    return "SENDING_REJECTION_REASON_US"


async def send_rejection_reason_us(update: Update, context: CallbackContext):
    reason = update.message.text
    user_id = context.user_data.get('reject_user_id')
    if user_id:
        keyboard = [
            [InlineKeyboardButton("📧 بيع إيميل عشوائي", callback_data='sell_gmail_random')],
            [InlineKeyboardButton("❌ إلغاء البيع", callback_data='sell_email_cancel')],
            [InlineKeyboardButton("🔙 رجوع إلى قائمة بيع الايميلات", callback_data='sell_emails_back')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🚫 تم رفض الإيميل الأمريكي الذي أرسلته.\nسبب الرفض: {reason}\n\nيمكنك الآن اختيار أحد الخيارات التالية:",
            reply_markup=reply_markup,
        )
        del context.user_data['reject_user_id']
        return ConversationHandler.END
    else:
        await update.message.reply_text("⚠️ حدث خطأ في إرسال سبب الرفض.")
        return ConversationHandler.END


async def sell_email_cancel(update: Update, context: CallbackContext) -> None:
    await update.callback_query.answer()
    user_id = update.effective_user.id
    sent_email_data = US_EMAILS_SENT.get(user_id)
    if sent_email_data:
        await update.callback_query.edit_message_text(
            f"🔒 لحماية خصوصيتك، يرجى تغيير كلمة سر الإيميل الأمريكي الذي تم إرساله إليك (`{sent_email_data['email']}`).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى قائمة بيع الايميلات", callback_data='sell_emails_back')]]),
        )
        mark_us_email_as_available(sent_email_data['email'])  # إتاحة الإيميل الأمريكي لإعادة الإرسال
        del US_EMAILS_SENT[user_id]
    else:
        await update.callback_query.edit_message_text(
            "⚠️ لم يتم العثور على معلومات الإيميل الأمريكي المرسل.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى قائمة بيع الايميلات", callback_data='sell_emails_back')]]),
        )
    return ConversationHandler.END


async def confirm_random_email(update: Update, context: CallbackContext):
    user_id, email, password = context.args
    # قم بتحديث رصيد المستخدم هنا (سيتم تنفيذه لاحقًا)
    await update.message.reply_text(f"✅ تم تأكيد الإيميل العشوائي ({email}) من قبل المشرف.")
    await context.bot.send_message(chat_id=int(user_id), text="💰 تم إضافة رصيد إلى حسابك مقابل بيع الإيميل العشوائي.")


async def reject_random_email(update: Update, context: CallbackContext):
    user_id, email = context.args
    await update.message.reply_text(f"❌ تم رفض الإيميل العشوائي ({email}). يرجى إرسال سبب الرفض إلى المستخدم.")
    context.user_data['reject_random_user_id'] = int(user_id)
    return "SENDING_REJECTION_REASON_RANDOM"


async def send_rejection_reason_random(update: Update, context: CallbackContext):
    reason = update.message.text
    user_id = context.user_data.get('reject_random_user_id')
    if user_id:
        keyboard = [[InlineKeyboardButton("🔄 إعادة إرسال إيميل عشوائي", callback_data='sell_gmail_random')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🚫 تم رفض الإيميل العشوائي الذي أرسلته.\nسبب الرفض: {reason}\n\nيمكنك الآن اختيار إعادة إرسال إيميل عشوائي:",
            reply_markup=reply_markup,
        )
        del context.user_data['reject_random_user_id']
        return ConversationHandler.END
    else:
        await update.message.reply_text("⚠️ حدث خطأ في إرسال سبب الرفض.")
        return ConversationHandler.END


async def add_required_email(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and len(context.args) == 2:
        email_to_add = context.args[0]
        password_to_add = context.args[1]
        add_email_to_stock(email_to_add, password_to_add)  # إضافة الإيميل وكلمة السر إلى المخزون
        await update.message.reply_text(f"➕ تم إضافة الإيميل الأمريكي: {email_to_add} مع كلمة السر: {password_to_add}")
    else:
        await update.message.reply_text("⚠️ استخدام الأمر: `/add_required_email <الايميل> <كلمة السر>`")


async def delete_required_email(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and context.args:
        email_to_delete = context.args[0]
        # سيتم إضافة وظيفة قاعدة البيانات هنا لاحقًا
        await update.message.reply_text(f"➖ سيتم حذف الإيميل الأمريكي المطلوب: {email_to_delete}")
    else:
        await update.message.reply_text("⚠️ استخدام الأمر: `/delete_required_email <الايميل>`")


async def verify_pay_random_email(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and len(context.args) == 1:
        email_to_verify = context.args[0]
        # هنا سيتم إضافة وظيفة قاعدة البيانات للدفع والإشعار
        await update.message.reply_text(f"✅ تم التحقق ودفع 300 ل.س. للإيميل العشوائي: {email_to_verify}")
    else:
        await update.message.reply_text("⚠️ استخدام الأمر: `/verify_pay_random_email <الايميل>`")


async def verify_pay_facebook(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID and len(context.args) == 2:
        email_or_username = context.args[0]
        password = context.args[1]
        # هنا سيتم إضافة وظيفة قاعدة البيانات للدفع والإشعار لحسابات الفيسبوك
        await update.message.reply_text(f"✅ تم التحقق ودفع 400 ل.س. لحساب الفيسبوك: {email_or_username}")
    else:
        await update.message.reply_text("⚠️ استخدام الأمر: `/verify_pay_facebook <الايميل/اسم المستخدم> <كلمة السر>`")


async def buy_proxies_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🔑 صفحة شراء البروكسيات قيد التطوير...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} pressed 'buy_proxies'.")


async def buy_accounts_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🛒 صفحة شراء الحسابات قيد التطوير...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} pressed 'buy_accounts'.")


async def sell_cards_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "💳 صفحة بيع البطاقات قيد التطوير...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} pressed 'sell_cards'.")


async def support_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "📞 يمكنك التواصل مع الدعم الفني عبر [رابط الدعم]...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} pressed 'support'.")


async def educational_videos_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🎬 قائمة الفيديوهات التعليمية قيد الإعداد...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} pressed 'educational_videos'.")


async def my_info_callback(update: Update, context: CallbackContext):
    user = update.effective_user
    # هنا سيتم استرداد معلومات المستخدم من قاعدة البيانات
    user_info = f"👤 معلومات المستخدم:\n"
    user_info += f"الاسم: {user.first_name} {user.last_name if user.last_name else ''}\n"
    user_info += f"المعرف: {user.id}\n"
    user_info += f"اسم المستخدم: @{user.username if user.username else 'غير متوفر'}\n"
    user_info += f"الرصيد: [سيتم استرداده من قاعدة البيانات]\n"
    user_info += f"الحالة في المجموعة: {'✅' if True else '❌'}\n" # سيتم استردادها من قاعدة البيانات

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        user_info,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} requested their info.")


async def my_games_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🎮 صفحة ألعابي قيد التطوير...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} pressed 'my_games'.")


async def main_menu_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await show_main_menu(update, context)
    logging.info(f"User {update.effective_user.id} returned to the main menu.")


async def recharge_callback(update: Update, context: CallbackContext) -> str:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Syriatel Cash", callback_data='recharge_syriatel')],
        [InlineKeyboardButton("Payeer", callback_data='recharge_payeer')],
        [InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("💳 اختر طريقة شحن الرصيد:", reply_markup=reply_markup)
    return RECHARGE_CHOOSING_METHOD


async def recharge_choose_method(update: Update, context: CallbackContext) -> str:
    query = update.callback_query
    await query.answer()
    context.user_data['recharge_method'] = query.data.split('_')[1]
    await query.edit_message_text(f"💰 يرجى إدخال مبلغ الشحن المطلوب (بالليرة السورية):",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='recharge')]]))
    return RECHARGE_ENTERING_AMOUNT


async def recharge_enter_amount(update: Update, context: CallbackContext) -> str:
    amount = update.message.text.strip()
    if amount.isdigit():
        context.user_data['recharge_amount'] = int(amount)
        method = context.user_data['recharge_method']
        if method == 'syriatel':
            address = SYRIATEL_CASH_ADDRESS
        elif method == 'payeer':
            address = PAYEER_ADDRESS
        else:
            address = "غير محدد"

        keyboard = [
            [InlineKeyboardButton("✅ تأكيد", callback_data='confirm_recharge_amount')],
            [InlineKeyboardButton("🔙 تعديل المبلغ", callback_data='recharge_back_amount')],
            [InlineKeyboardButton("❌ إلغاء", callback_data='recharge_cancel')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"💸 هل أنت متأكد أنك تريد شحن مبلغ {amount} ليرة سورية عبر {method.capitalize()}؟\n"
            f"يرجى التحويل إلى العنوان التالي: `{address}`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return RECHARGE_CONFIRMING_AMOUNT
    else:
        await update.message.reply_text("⚠️ يرجى إدخال مبلغ الشحن كرقم صحيح.")
        return RECHARGE_ENTERING_AMOUNT


async def recharge_confirm_amount(update: Update, context: CallbackContext) -> str:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔄 يرجى إرسال صورة أو معرف عملية التحويل لتأكيد الدفع.",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='recharge_back_amount')]]))
    return RECHARGE_ENTERING_TRANSACTION_ID


async def recharge_enter_transaction_id(update: Update, context: CallbackContext) -> int:
    transaction_info = update.message.text.strip()
    context.user_data['transaction_info'] = transaction_info  # حفظ معلومات التحويل مؤقتًا

    keyboard = [
        [InlineKeyboardButton("✅ تأكيد الإرسال للمشرف", callback_data='confirm_send_recharge_info')],
        [InlineKeyboardButton("🔙 رجوع لتعديل الإثبات", callback_data='recharge_back_transaction')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "❓ هل أنت متأكد من إرسال هذه المعلومات للمشرف؟",
        reply_markup=reply_markup,
    )
    return "CONFIRMING_RECHARGE_INFO"  # حالة جديدة لانتظار تأكيد الإرسال


async def confirm_send_recharge_info(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    amount = context.user_data.get('recharge_amount', 'غير محدد')
    method = context.user_data.get('recharge_method', 'غير محدد').capitalize()
    transaction_info = context.user_data.get('transaction_info', 'لا يوجد')

    message_to_admin = (
        f"💰 طلب شحن رصيد جديد:\n"
        f"الاسم: {user.full_name} (@{user.username})\n"
        f"المعرف: {user.id}\n"
        f"المبلغ: {amount} ليرة سورية\n"
        f"الطريقة: {method}\n"
        f"معلومات التحويل: {transaction_info}\n\n"
        f"/confirm_recharge {user.id} {amount}\n"
        f"/reject_recharge {user.id}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=message_to_admin)
    await query.edit_message_text(
        "✅ تم إرسال معلومات الدفع للمشرف للمراجعة.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    return ConversationHandler.END


async def recharge_back_transaction(update: Update, context: CallbackContext) -> str:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🔄 يرجى إرسال صورة أو معرف عملية التحويل لتأكيد الدفع.",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='recharge_back_amount')]]))
    return RECHARGE_ENTERING_TRANSACTION_ID


async def confirm_recharge(update: Update, context: CallbackContext):
    user_id, amount = context.args
    # هنا سيتم إضافة وظيفة قاعدة البيانات لتحديث رصيد المستخدم
    await update.message.reply_text(f"✅ تم تأكيد شحن رصيد المستخدم {user_id} بمبلغ {amount} ليرة سورية.")
    await context.bot.send_message(chat_id=int(user_id), text=f"🎉 تم شحن رصيدك بنجاح بمبلغ {amount} ليرة سورية.")


async def reject_recharge(update: Update, context: CallbackContext):
    user_id = context.args[0]
    await update.message.reply_text(f"❌ تم رفض طلب شحن رصيد المستخدم {user_id}.")
    context.user_data['reject_recharge_user_id'] = int(user_id)
    return "SENDING_REJECTION_RECHARGE"


async def send_rejection_reason_recharge(update: Update, context: CallbackContext):
    reason = update.message.text
    user_id = context.user_data.get('reject_recharge_user_id')
    if user_id:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🚫 تم رفض طلب شحن الرصيد الخاص بك.\nسبب الرفض: {reason}\n\nيرجى المحاولة مرة أخرى وإرسال معلومات دفع صحيحة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💰 شحن رصيد", callback_data='recharge')]]),
        )
        del context.user_data['reject_recharge_user_id']
        return ConversationHandler.END
    else:
        await update.message.reply_text("⚠️ حدث خطأ في إرسال سبب الرفض.")
        return ConversationHandler.END


async def recharge_back_amount(update: Update, context: CallbackContext) -> str:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("💰 يرجى إدخال مبلغ الشحن المطلوب (بالليرة السورية):",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى طرق الشحن", callback_data='recharge')]]))
    return RECHARGE_ENTERING_AMOUNT


async def recharge_cancel(update: Update, context: CallbackContext) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("🚫 تم إلغاء عملية شحن الرصيد.",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]))
    return ConversationHandler.END


async def ratio_games_callback(update: Update, context: CallbackContext):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "🕹️ صفحة ألعاب النسبة قيد التطوير...",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع إلى القائمة الرئيسية", callback_data='main_menu')]]),
    )
    logging.info(f"User {update.effective_user.id} pressed 'ratio_games'.")


async def sell_emails_back_callback(update: Update, context: CallbackContext) -> str:
    await update.callback_query.answer()
    return await sell_emails_callback(update, context)


def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # محادثة بيع الإيميلات
    sell_email_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(sell_emails_callback, pattern='^sell_emails$')],
        states={
            SELL_EMAIL_CHOOSING_TYPE: [CallbackQueryHandler(sell_gmail_choose_type, pattern='^sell_gmail_us$|^sell_gmail_random$|^main_menu$|^sell_emails_back$')],
            SELL_US_EMAIL_WAITING_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_us_email_reply)],
            SELL_EMAIL_ENTERING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_email_enter_address)],
            SENDING_REJECTION_REASON_US: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_rejection_reason_us)],
            SENDING_REJECTION_REASON_RANDOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_rejection_reason_random)],
        },
        fallbacks=[CallbackQueryHandler(main_menu_callback, pattern='^main_menu$'),
                   CallbackQueryHandler(sell_emails_back_callback, pattern='^sell_emails_back$')],
    )

    # محادثة شحن الرصيد
    recharge_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(recharge_callback, pattern='^recharge$')],
        states={
            RECHARGE_CHOOSING_METHOD: [CallbackQueryHandler(recharge_choose_method, pattern='^recharge_syriatel$|^recharge_payeer$|^main_menu$')],
            RECHARGE_ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_enter_amount)],
            RECHARGE_CONFIRMING_AMOUNT: [CallbackQueryHandler(recharge_confirm_amount, pattern='^confirm_recharge_amount$|^recharge_back_amount$|^recharge_cancel$')],
            RECHARGE_ENTERING_TRANSACTION_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, recharge_enter_transaction_id)],
            "CONFIRMING_RECHARGE_INFO": [CallbackQueryHandler(confirm_send_recharge_info, pattern='^confirm_send_recharge_info$'),
                                        CallbackQueryHandler(recharge_back_transaction, pattern='^recharge_back_transaction$')],
            "SENDING_REJECTION_RECHARGE": [MessageHandler(filters.TEXT & ~filters.COMMAND, send_rejection_reason_recharge)],
        },
        fallbacks=[CallbackQueryHandler(main_menu_callback, pattern='^main_menu$'),
                   CallbackQueryHandler(recharge_callback, pattern='^recharge$')],
    )

    # معالجات الأوامر
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('add_required_email', add_required_email))
    application.add_handler(CommandHandler('delete_required_email', delete_required_email))
    application.add_handler(CommandHandler('verify_pay_random_email', verify_pay_random_email))
    application.add_handler(CommandHandler('verify_pay_facebook', verify_pay_facebook))
    application.add_handler(CommandHandler('confirm_us_email', confirm_us_email))
    application.add_handler(CommandHandler('reject_us_email', reject_us_email))
    application.add_handler(CommandHandler('confirm_random_email', confirm_random_email))
    application.add_handler(CommandHandler('reject_random_email', reject_random_email))
    application.add_handler(CommandHandler('confirm_recharge', confirm_recharge))
    application.add_handler(CommandHandler('reject_recharge', reject_recharge))

    # معالجات الاستدعاءات (الكيبورد المضمن)
    application.add_handler(CallbackQueryHandler(joined_group_callback, pattern='^joined_group$'))
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern='^main_menu$'))
    application.add_handler(CallbackQueryHandler(buy_proxies_callback, pattern='^buy_proxies$'))
    application.add_handler(CallbackQueryHandler(buy_accounts_callback, pattern='^buy_accounts$'))
    application.add_handler(CallbackQueryHandler(sell_cards_callback, pattern='^sell_cards$'))
    application.add_handler(CallbackQueryHandler(support_callback, pattern='^support$'))
    application.add_handler(CallbackQueryHandler(educational_videos_callback, pattern='^educational_videos$'))
    application.add_handler(CallbackQueryHandler(my_info_callback, pattern='^my_info$'))
    application.add_handler(CallbackQueryHandler(my_games_callback, pattern='^my_games$'))
    application.add_handler(CallbackQueryHandler(sell_emails_back_callback, pattern='^sell_emails_back$'))
    application.add_handler(CallbackQueryHandler(confirm_send_recharge_info, pattern='^confirm_send_recharge_info$'))
    application.add_handler(CallbackQueryHandler(recharge_back_transaction, pattern='^recharge_back_transaction$'))

    # إضافة المحادثات
    application.add_handler(sell_email_conversation)
    application.add_handler(recharge_conversation)

    # تشغيل البوت
    application.run_polling()


if __name__ == '__main__':
    create_tables()  # إنشاء الجداول عند تشغيل البوت
    main()

