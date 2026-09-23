import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Загружаем переменные из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")

# Преобразуем строку с ID из .env в список чисел
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_RAW.split(",") if admin_id.strip()]

if not BOT_TOKEN:
    exit("ОШИБКА: BOT_TOKEN не найден в .env файле!")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Связка: (receiver_id, message_id) -> sender_user_object
anon_map = {}


class AnonState(StatesGroup):
    waiting_for_message = State()


# 1. СТАРТ И ПОЛУЧЕНИЕ ССЫЛКИ
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    args = command.args

    if args and args.isdigit():
        target_id = int(args)
        if target_id == message.from_user.id:
            await message.answer("Нельзя отправлять анонимки самому себе!")
            return

        await state.update_data(target_id=target_id)
        await state.set_state(AnonState.waiting_for_message)
        await message.answer("Напиши **одно** сообщение (текст, фото или кружок). Оно улетит анонимно!")
    else:
        bot_info = await bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
        await message.answer(
            f"Привет! Это бот анонимных сообщений.\n\n"
            f"Твоя личная ссылка для приема сообщений:\n`{share_link}`",
            parse_mode="Markdown"
        )


# 2. КОМАНДА /WHO (только для админов из ADMIN_IDS)
@dp.message(Command("who"))
async def cmd_who(message: types.Message, state: FSMContext):
    await state.clear()

    if message.from_user.id not in ADMIN_IDS:
        return

    if not message.reply_to_message:
        await message.answer("Используй команду /who в ответ на анонимное сообщение.")
        return

    target_key = (message.chat.id, message.reply_to_message.message_id)
    sender = anon_map.get(target_key)

    if not sender:
        await message.answer("Информация об отправителе не найдена в памяти бота.")
        return

    info_text = (
        f"🕵️‍♂️ *Сведения об анониме:*\n\n"
        f"👤 *Имя:* {sender.full_name}\n"
        f"🆔 *ID:* `{sender.id}`\n"
        f"🏷 *Username:* @{sender.username if sender.username else 'отсутствует'}\n"
        f"🌐 *Языковой код:* `{sender.language_code}`\n"
        f"🤖 *Это бот:* {'Да' if sender.is_bot else 'Нет'}\n"
        f"⭐ *Premium:* {'Да' if sender.is_premium else 'Нет'}"
    )

    await message.answer(info_text, parse_mode="Markdown")


# 3. СБРОС ОТПРАВКИ ПРИ ЛЮБОЙ КОМАНДЕ (начинающейся с "/")
@dp.message(AnonState.waiting_for_message, F.text.startswith("/"))
async def cancel_anon_on_command(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Ввод анонимного сообщения отменен, так как была введена команда.")


# 4. ОБРАБОТКА И ОТПРАВКА ОДНОГО СООБЩЕНИЯ
@dp.message(AnonState.waiting_for_message)
async def process_anon_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("target_id")

    # Сразу сбрасываем состояние
    await state.clear()

    try:
        sent_msg = await message.copy_to(
            chat_id=target_id,
            caption=(
                        message.caption + "\n\n📩 *Вам новое анонимное сообщение!*") if message.caption else "📩 *Вам новое анонимное сообщение!*",
            parse_mode="Markdown"
        )

        anon_map[(target_id, sent_msg.message_id)] = message.from_user

        await message.answer(
            "Сообщение успешно отправлено! Чтобы отправить ещё одно, нужно снова перейти по ссылке получателя.")
    except Exception:
        await message.answer("Не удалось отправить сообщение. Возможно, получатель заблокировал бота.")


# 5. ЗАГЛУШКА ДЛЯ ОБЫЧНЫХ СООБЩЕНИЙ БЕЗ ССЫЛКИ
@dp.message(StateFilter(None))
async def fallback_message(message: types.Message):
    await message.answer("Чтобы отправить анонимное сообщение, перейди по персональной ссылке нужного человека!")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())