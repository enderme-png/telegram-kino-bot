import asyncio
import logging
import sys
import json
import os
import re
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from aiohttp import web  # Uyg'oq turish uchun veb-server

# --- BOT SOZLAMALARI ---
TOKEN = "8813479035:AAFP5cbi2CxiMmnfDMH16MrASH1McSAg6vU"
ADMIN_ID = 7479405739

CHANNELS_FILE = "channels_db.json"
ANIME_FILE = "anime_db.json"
USERS_FILE = "users_db.json"


# --- BAZALAR BILAN TEZKOR ISHLASH ---
def load_json(filename, default_factory):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"{filename} o'qishda xatolik: {e}")
    return default_factory()


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"{filename} yozishda xatolik: {e}")


CHANNELS = load_json(CHANNELS_FILE, list)
ANIMES = load_json(ANIME_FILE, dict)
USERS = load_json(USERS_FILE, list)


def save_channels(): save_json(CHANNELS_FILE, CHANNELS)


def save_animes(): save_json(ANIME_FILE, ANIMES)


def save_users(): save_json(USERS_FILE, USERS)


def add_or_update_user(user_id: int, name: str, username: str):
    clean_name = html.quote(name) if name else "Foydalanuvchi"
    clean_username = html.quote(username) if username else "Mavjud emas"
    user_exists = False
    for i, user in enumerate(USERS):
        if isinstance(user, dict) and user.get("id") == user_id:
            USERS[i]["name"] = clean_name
            USERS[i]["username"] = clean_username
            user_exists = True
            break
        elif isinstance(user, int) and user == user_id:
            USERS.remove(user)
            break
    if not user_exists:
        USERS.append({"id": user_id, "name": clean_name, "username": clean_username})
    save_users()


def get_user_ids():
    ids = []
    for u in USERS:
        if isinstance(u, dict):
            ids.append(u["id"])
        elif isinstance(u, int):
            ids.append(u)
    return ids


dp = Dispatcher()


class AdminStates(StatesGroup):
    waiting_for_channel_input = State()
    waiting_for_anime_code = State()
    waiting_for_anime_photo = State()
    waiting_for_anime_caption = State()
    waiting_for_part_code = State()
    waiting_for_part_number = State()
    waiting_for_part_video = State()
    waiting_for_delete_code = State()
    waiting_for_broadcast_msg = State()
    waiting_for_movie_code = State()
    waiting_for_movie_photo = State()
    waiting_for_movie_video = State()
    waiting_for_movie_caption = State()
    waiting_for_edit_code = State()
    waiting_for_new_caption = State()


# --- OBUNANI PARALLEL TEKSHIRISH ---
async def check_single_subscription(bot: Bot, chat_id: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception:
        return True


async def check_all_subscriptions(bot: Bot, user_id: int) -> bool:
    if not CHANNELS: return True
    tasks = [check_single_subscription(bot, ch.get("username", ""), user_id) for ch in CHANNELS if ch.get("username")]
    results = await asyncio.gather(*tasks)
    return all(results)


# --- INLINE KLAVIATURALAR ---
def get_subscription_keyboard():
    inline_keyboard = []
    for n, channel in enumerate(CHANNELS, start=1):
        inline_keyboard.append([InlineKeyboardButton(text=f"📢 {n}-KANALGA OBUNA BO'LISH", url=channel.get("link", ""))])
    inline_keyboard.append([InlineKeyboardButton(text="✅ OBUNANI TEKSHIRISH", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="admin_add_channel"),
         InlineKeyboardButton(text="❌ Kanalni o'chirish", callback_data="admin_select_delete")],
        [InlineKeyboardButton(text="🧸 Yangi Multfilm", callback_data="admin_add_anime_main"),
         InlineKeyboardButton(text="🎬 Qism qo'shish", callback_data="admin_add_anime_part")],
        [InlineKeyboardButton(text="🎥 Yangi Kino / Film", callback_data="admin_add_movie"),
         InlineKeyboardButton(text="📝 Ta'rifni tahrirlash", callback_data="admin_edit_caption")],
        [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_view_users_list"),
         InlineKeyboardButton(text="📊 Statistika", callback_data="admin_status_view")],
        [InlineKeyboardButton(text="🗑 Loyihani o'chirish", callback_data="admin_delete_anime"),
         InlineKeyboardButton(text="📢 Reklama", callback_data="admin_broadcast")]
    ])


def get_parts_keyboard(anime_code: str, parts_dict: dict):
    inline_keyboard = []
    row = []
    sorted_parts = sorted([int(k) for k in parts_dict.keys()])
    for part in sorted_parts:
        row.append(InlineKeyboardButton(text=f"🍿 {part}-qism", callback_data=f"show_part_{anime_code}_{part}"))
        if len(row) == 3:
            inline_keyboard.append(row)
            row = []
    if row: inline_keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def build_admin_text():
    return f"⚡ <b>Admin Panel</b>\n\n👥 Obunachilar: {len(USERS)} ta\n📢 Kanallar: {len(CHANNELS)} ta\n🎬 Kinolar: {len(ANIMES)} ta"


# ----------------- ADMIN PANEL BOSHQARUVI -----------------
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer(text=build_admin_text(), reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)


@dp.callback_query(lambda c: c.data == "admin_back_to_panel")
async def back_to_panel(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await state.clear()
    await callback_query.message.edit_text(text=build_admin_text(), reply_markup=get_admin_keyboard(),
                                           parse_mode=ParseMode.HTML)


@dp.callback_query(lambda c: c.data == "admin_view_users_list")
async def admin_view_users_list(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID: return
    try:
        await callback_query.answer()
        if not USERS:
            await callback_query.message.edit_text("👥 Foydalanuvchilar yo'q.", reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[[InlineKeyboardButton(text="Orqaga", callback_data="admin_back_to_panel")]]]))
            return
        text = "<b>👥 Foydalanuvchilar ro'yxati:</b>\n\n"
        for n, user in enumerate(USERS, start=1):
            if isinstance(user, dict):
                u_name, u_user = html.quote(str(user.get('name', 'User'))), user.get('username', 'Mavjud emas')
                username_text = f"@{u_user}" if u_user and u_user != "Mavjud emas" else f"ID: {user.get('id')}"
                text += f"{n}. 👤 {u_name} — {username_text}\n"
            else:
                text += f"{n}. ID: {user}\n"
            if len(text) > 3800: text += "\n⚠️ *Ro'yxat uzun...*"; break
        await callback_query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[[InlineKeyboardButton(text="Orqaga", callback_data="admin_back_to_panel")]]]),
                                               parse_mode=ParseMode.HTML)
    except Exception:
        pass


# --- TA'RIFNI TAHRIRLASH ---
@dp.callback_query(lambda c: c.data == "admin_edit_caption")
async def admin_edit_caption_start(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await callback_query.answer()
    await callback_query.message.answer("📝 Ta'rifini o'zgartirmoqchi bo'lgan loyihaning **KODINI** yuboring:")
    await state.set_state(AdminStates.waiting_for_edit_code)


@dp.message(AdminStates.waiting_for_edit_code)
async def process_edit_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if code not in ANIMES:
        await message.answer("❌ Bunday kodli loyiha topilmadi!");
        await state.clear();
        return
    await state.update_data(edit_code=code)
    current_caption = ANIMES[code].get("caption", "Ta'rif mavjud emas.")
    await message.answer(f"🔍 Kod: `{code}`\n\n📝 **Yangi ta'rifni kiriting:**")
    await state.set_state(AdminStates.waiting_for_new_caption)


@dp.message(AdminStates.waiting_for_new_caption)
async def process_new_caption(message: Message, state: FSMContext):
    new_caption = message.html_text
    data = await state.get_data();
    code = data['edit_code']
    ANIMES[code]["caption"] = new_caption;
    save_animes();
    await state.clear()
    await message.answer(f"✅ `{code}` kodli loyihaning ta'rifi yangilandi!")


# --- KINOLAR QO'SHISH TIZIMI ---
@dp.callback_query(lambda c: c.data == "admin_add_movie")
async def admin_add_movie_start(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await callback_query.answer()
    await callback_query.message.answer("🔢 Kino / Film uchun **KOD** kiriting:")
    await state.set_state(AdminStates.waiting_for_movie_code)


@dp.message(AdminStates.waiting_for_movie_code)
async def process_movie_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if code in ANIMES: await message.answer("⚠️ Bu kod band!"); return
    await state.update_data(movie_code=code)
    await message.answer(f"🖼 Kod: `{code}`. Endi uning **POSTERINI** yuboring:")
    await state.set_state(AdminStates.waiting_for_movie_photo)


@dp.message(AdminStates.waiting_for_movie_photo)
async def process_movie_photo(message: Message, state: FSMContext):
    if not message.photo: await message.answer("❌ Poster rasm bo'lishi shart!"); return
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("📹 Endi filmning **VIDEOFAYLINI** yuboring:")
    await state.set_state(AdminStates.waiting_for_movie_video)


@dp.message(AdminStates.waiting_for_movie_video)
async def process_movie_video(message: Message, state: FSMContext):
    video_id = message.video.file_id if message.video else (
        message.document.file_id if message.document and message.document.mime_type and message.document.mime_type.startswith(
            "video/") else None)
    if not video_id: await message.answer("❌ Bu video fayl emas!"); return
    await state.update_data(video_id=video_id)
    await message.answer("📝 Endi film uchun **TA'RIF** kiriting:")
    await state.set_state(AdminStates.waiting_for_movie_caption)


@dp.message(AdminStates.waiting_for_movie_caption)
async def process_movie_caption(message: Message, state: FSMContext):
    caption = message.html_text
    data = await state.get_data();
    code = data['movie_code']
    ANIMES[code] = {"type": "movie", "photo_id": data['photo_id'], "video_id": data['video_id'], "caption": caption}
    save_animes();
    await state.clear()
    await message.answer(f"✅ Kino saqlandi! Kod: `{code}`")


# --- MULTFILMLAR QO'SHISH TIZIMI (KO'P QISMLI) ---
@dp.callback_query(lambda c: c.data == "admin_add_anime_main")
async def admin_add_anime_main_start(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await callback_query.answer()
    await callback_query.message.answer("🔢 Ko'p qismli multfilm uchun **KOD** kiriting:")
    await state.set_state(AdminStates.waiting_for_anime_code)


@dp.message(AdminStates.waiting_for_anime_code)
async def process_main_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if code in ANIMES: await message.answer("⚠️ Bu kod band!"); return
    await state.update_data(anime_code=code)
    await message.answer(f"🖼 Kod: `{code}`. Endi uning **POSTERINI** yuboring:")
    await state.set_state(AdminStates.waiting_for_anime_photo)


@dp.message(AdminStates.waiting_for_anime_photo)
async def process_main_photo(message: Message, state: FSMContext):
    if not message.photo: await message.answer("❌ Faqat rasm yuboring!"); return
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("📝 Endi multfilm haqida **UMUMIY TA'RIF** yuboring:")
    await state.set_state(AdminStates.waiting_for_anime_caption)


@dp.message(AdminStates.waiting_for_anime_caption)
async def process_main_caption(message: Message, state: FSMContext):
    caption = message.html_text
    data = await state.get_data();
    code = data['anime_code']
    ANIMES[code] = {"type": "serial", "photo_id": data['photo_id'], "caption": caption, "parts": {}}
    save_animes();
    await state.clear()
    await message.answer(f"✅ Multfilm loyihasi yaratildi! Kod: `{code}`.")


@dp.callback_query(lambda c: c.data == "admin_add_anime_part")
async def admin_add_part_start(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await callback_query.answer()
    await callback_query.message.answer("🔢 Qaysi kodga qism qo'shasiz?")
    await state.set_state(AdminStates.waiting_for_part_code)


@dp.message(AdminStates.waiting_for_part_code)
async def process_part_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if code not in ANIMES or ANIMES[code].get("type") == "movie":
        await message.answer("❌ Bunday multfilm topilmadi!");
        return
    await state.update_data(part_code=code)
    await message.answer(f"🎬 Multfilm: `{code}`. Nechanchi **QISM** raqamini yozing:")
    await state.set_state(AdminStates.waiting_for_part_number)


@dp.message(AdminStates.waiting_for_part_number)
async def process_part_number(message: Message, state: FSMContext):
    part_num = message.text.strip()
    if not part_num.isdigit(): await message.answer("❌ Faqat raqam yozing!"); return
    await state.update_data(part_number=part_num)
    await message.answer(f"📹 Endi {part_num}-qism **VIDEOFAYLINI** yuboring:")
    await state.set_state(AdminStates.waiting_for_part_video)


@dp.message(AdminStates.waiting_for_part_video)
async def process_part_video(message: Message, state: FSMContext):
    video_id = message.video.file_id if message.video else (
        message.document.file_id if message.document and message.document.mime_type and message.document.mime_type.startswith(
            "video/") else None)
    if not video_id: await message.answer("❌ Bu video fayl emas!"); return
    data = await state.get_data();
    code = data['part_code'];
    part_num = data['part_number']
    ANIMES[code]["parts"][part_num] = video_id;
    save_animes();
    await state.clear()
    await message.answer(f"✅ `{code}` kodiga `{part_num}-qism` qo'shildi!")


# --- REKLAMA TARQATISH TIZIMI ---
@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast_start(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await callback_query.answer()
    await callback_query.message.answer("📢 Reklama xabarini yuboring:\n/cancel - bekor qilish")
    await state.set_state(AdminStates.waiting_for_broadcast_msg)


@dp.message(AdminStates.waiting_for_broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear();
    await message.answer("🚀 Reklama tarqatilmoqda...");
    success, failed = 0, 0
    for user_id in get_user_ids():
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=message.chat.id,
                                   message_id=message.message_id); success += 1; await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await message.answer(f"✅ Eshittirish tugadi! Muvaffaqiyatli: {success} ta, Bloklagan: {failed} ta")


@dp.callback_query(lambda c: c.data == "admin_status_view")
async def admin_status_view(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID: return
    text = f"📊 **Statistika:**\n\n👥 Obunachilar: {len(USERS)} ta\n🔑 **Kodlar:**\n"
    for k, v in ANIMES.items():
        t = "To'liq Film" if v.get("type") == "movie" else f"{len(v.get('parts', {}))} qism"
        text += f"• `{k}` ({t})\n"
    await callback_query.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[[InlineKeyboardButton(text="Orqaga", callback_data="admin_back_to_panel")]]]))


# --- MAJBURIY OBUNA KANALLARI ---
@dp.callback_query(lambda c: c.data == "admin_add_channel")
async def admin_add_channel_callback(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await callback_query.answer()
    await callback_query.message.answer("➕ Kanal havolasini yuboring:")
    await state.set_state(AdminStates.waiting_for_channel_input)


@dp.message(AdminStates.waiting_for_channel_input)
async def process_channel_input(message: Message, state: FSMContext):
    user_input = message.text.strip();
    match = re.search(r'(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,})', user_input)
    if match:
        username, link = "@" + match.group(1), f"https://t.me/{match.group(1)}"
    elif user_input.startswith("@"):
        username, link = user_input, f"https://t.me/{user_input[1:]}"
    else:
        await message.answer("❌ Xato!"); return
    CHANNELS.append({"username": username, "link": link});
    save_channels();
    await state.clear()
    await message.answer(f"✅ Kanal qo'shildi: {username}")


@dp.callback_query(lambda c: c.data == "admin_select_delete")
async def admin_select_delete_callback(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID: return
    if not CHANNELS: await callback_query.answer("Hozircha majburiy kanallar yo'q!", show_alert=True); return
    await callback_query.answer()
    text = "❌ O'chirish uchun kanalni tanlang:\n\n";
    inline_keyboard = []
    for n, ch in enumerate(CHANNELS):
        text += f"{n + 1}. `{ch['username']}`\n"
        inline_keyboard.append([InlineKeyboardButton(text=f"{ch['username']}", callback_data=f"delete_ch_{n}")])
    inline_keyboard.append([InlineKeyboardButton(text="Orqaga", callback_data="admin_back_to_panel")])
    await callback_query.message.edit_text(text=text,
                                           reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard))


@dp.callback_query(lambda c: c.data.startswith("delete_ch_"))
async def admin_delete_specific_channel(callback_query: CallbackQuery):
    idx = int(callback_query.data.split("_")[2])
    if 0 <= idx < len(CHANNELS): deleted = CHANNELS.pop(idx); save_channels(); await callback_query.answer(
        f"{deleted['username']} o'chirildi!", show_alert=True)
    await callback_query.message.edit_text(text=build_admin_text(), reply_markup=get_admin_keyboard(),
                                           parse_mode=ParseMode.HTML)


@dp.callback_query(lambda c: c.data == "admin_delete_anime")
async def admin_delete_anime_start(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID: return
    await callback_query.answer();
    await callback_query.message.answer("🗑 O'chiriladigan loyihaning kodini yuboring:")
    await state.set_state(AdminStates.waiting_for_delete_code)


@dp.message(AdminStates.waiting_for_delete_code)
async def process_delete_anime(message: Message, state: FSMContext):
    code = message.text.strip()
    if code in ANIMES:
        del ANIMES[code]; save_animes(); await message.answer("🗑 O'chirildi.")
    else:
        await message.answer("❌ Bazada topilmadi.")
    await state.clear()


@dp.message(Command("cancel"))
async def cancel_action(message: Message, state: FSMContext):
    await state.clear();
    await message.answer("❌ Bekor qilindi.")


# ----------------- FOYDALANUVCHILAR QISMI INTERFEYSI -----------------
@dp.message(CommandStart())
async def command_start_handler(message: Message, bot: Bot) -> None:
    add_or_update_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    if await check_all_subscriptions(bot, message.from_user.id):
        await message.answer(f"👋 **Xush kelibsiz!**\n\n🍿 Film yoki multfilm **KODINI** yuboring:")
    else:
        await message.answer("⚠️ Botdan foydalanish uchun kanallarimizga obuna bo'ling:",
                             reply_markup=get_subscription_keyboard())


@dp.callback_query(lambda c: c.data == "check_sub")
async def process_check_sub(callback_query: CallbackQuery, bot: Bot):
    add_or_update_user(callback_query.from_user.id, callback_query.from_user.first_name,
                       callback_query.from_user.username)
    if await check_all_subscriptions(bot, callback_query.from_user.id):
        await callback_query.answer("Obuna tasdiqlandi! 🎉")
        await callback_query.message.answer("🍿 **Marhamat, KODNI yuboring:**");
        await callback_query.message.delete()
    else:
        await callback_query.answer("Siz barcha kanallarga a'zo bo'lmadingiz! ❌", show_alert=True)


@dp.message()
async def anime_search_handler(message: Message, bot: Bot) -> None:
    search_code = message.text.strip()
    if search_code.startswith("/"): return
    add_or_update_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    if search_code not in ANIMES:
        await message.answer(f"🔍 Kechirasiz, <b>{search_code}</b> kodli loyiha topilmadi.");
        return
    if not await check_all_subscriptions(bot, message.from_user.id):
        await message.answer("⚠️ Avval kanallarga a'zo bo'ling:", reply_markup=get_subscription_keyboard());
        return
    item = ANIMES[search_code]
    if item.get("type") == "movie":
        movie_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎥 Videoni ko'rish", callback_data=f"get_movie_{search_code}")]])
        await bot.send_photo(chat_id=message.chat.id, photo=item["photo_id"], caption=item["caption"],
                             reply_markup=movie_kb, parse_mode=ParseMode.HTML)
    else:
        if not item.get("parts"): await message.answer("🎬 Multfilm topildi, biroq qismlari yo'q."); return
        await bot.send_photo(chat_id=message.chat.id, photo=item["photo_id"], caption=item["caption"],
                             reply_markup=get_parts_keyboard(search_code, item["parts"]), parse_mode=ParseMode.HTML)


@dp.callback_query(lambda c: c.data.startswith("get_movie_"))
async def process_get_movie(callback_query: CallbackQuery, bot: Bot):
    if not await check_all_subscriptions(bot, callback_query.from_user.id): await callback_query.answer(
        "Obuna bo'linmagan!", show_alert=True); return
    movie_code = callback_query.data.split("_")[2];
    item = ANIMES.get(movie_code)
    if not item or "video_id" not in item: await callback_query.answer("Video topilmadi!", show_alert=True); return
    await callback_query.answer("Kino yuklanmoqda...");
    asyncio.create_task(bot.send_chat_action(chat_id=callback_query.message.chat.id, action="upload_video"))
    try:
        await bot.send_video(chat_id=callback_query.message.chat.id, video=item["video_id"],
                             caption=f"🎬 Kod: {movie_code}", parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await bot.send_document(chat_id=callback_query.message.chat.id, document=item["video_id"],
                                    caption=f"🎬 Kod: {movie_code}", parse_mode=ParseMode.HTML)
        except Exception:
            await callback_query.message.answer("❌ Muammo yuz berdi.")


@dp.callback_query(lambda c: c.data.startswith("show_part_"))
async def process_show_part(callback_query: CallbackQuery, bot: Bot):
    if not await check_all_subscriptions(bot, callback_query.from_user.id): await callback_query.answer(
        "Obuna bo'linmagan!", show_alert=True); return
    data_parts = callback_query.data.split("_");
    anime_code, part_num = data_parts[2], data_parts[3]
    anime = ANIMES.get(anime_code)
    if not anime or part_num not in anime["parts"]: await callback_query.answer("Qism topilmadi!",
                                                                                show_alert=True); return
    await callback_query.answer(f"{part_num}-qism yuklanmoqda...");
    asyncio.create_task(bot.send_chat_action(chat_id=callback_query.message.chat.id, action="upload_video"))
    next_part = str(int(part_num) + 1);
    video_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ Keyingi qism",
                                                                           callback_data=f"show_part_{anime_code}_{next_part}")]]) if next_part in \
                                                                                                                                      anime[
                                                                                                                                          "parts"] else None
    try:
        await bot.send_video(chat_id=callback_query.message.chat.id, video=anime["parts"][part_num],
                             caption=f"🧸 {anime_code} — {part_num}-qism", reply_markup=video_kb,
                             parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await bot.send_document(chat_id=callback_query.message.chat.id, document=anime["parts"][part_num],
                                    caption=f"🧸 {anime_code} — {part_num}-qism", reply_markup=video_kb,
                                    parse_mode=ParseMode.HTML)
        except Exception:
            await callback_query.message.answer("❌ Muammo yuz berdi.")


# --- MULTIFUNKSIONAL UYG'OQ TURISH SERVERI ---
# Bu qism `Render.com` loyihani "uxlatmasligi" uchun kerak.
# U orqa fonda kichik veb-server ochadi, unga `cron-job.org` kabi servis
# orqali har 10 daqiqada signal yuborib tursa, bot o'chmaydi.
async def handle_ping(request):
    """Veb-serverga kelgan so'rovlarga javob beradi."""
    return web.Response(text="Bot ishlayapti, men uyg'oqman!")


async def start_web_server():
    """Uyg'otgich veb-serverini ishga tushiradi."""
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render o'zi beradigan PORT ni o'qiydi yoki 8080 ni oladi.
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Veb-server {port}-portda ishga tushdi.")


async def main() -> None:
    bot = Bot(token=TOKEN, properties=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.set_my_commands([
        BotCommand(command="start", description="Ishga tushirish"),
        BotCommand(command="admin", description="Admin panel"),
        BotCommand(command="cancel", description="Bekor qilish")
    ])

    # Orqa fonda uyg'otib turuvchi veb-serverni yoqish
    await start_web_server()

    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass