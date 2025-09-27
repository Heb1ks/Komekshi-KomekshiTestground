import aiogram
import python_weather as pw
import asyncio, random
import datetime

from database import Database
import config

import aiogram.filters as filters
import aiogram.types as types

from aiogram.fsm.storage.memory import MemoryStorage  # NEW
from aiogram.fsm.context import FSMContext           # NEW
from aiogram.fsm.state import State, StatesGroup     # NEW

from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import types as t
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter  # make sure you import this

from aiogram.fsm.state import State, StatesGroup

class DeadlineState(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()

# Инициализация
storage = MemoryStorage()                            # NEW
dp = aiogram.Dispatcher(storage=storage)             # MODIFIED
database = Database(config.DB_PATH)

# State machine for notification setup (NEW)
class NotificationState(StatesGroup):
    choosing_type = State()
    setting_exact_time = State()
    setting_interval = State()

user_latest_deadline = {}  # NEW

@dp.message(filters.Command("phrase"))
async def send_random_phrase(msg: types.Message):
    await msg.answer(random.choice(config.PHRASES))


@dp.message(filters.Command("weather"))
async def send_weather(msg: types.Message):
    args = msg.text.split(" ")[1:]
    if not args:
        await msg.answer("Please use /weather [city]")
        return

    city = " ".join(args)
    async with pw.Client(unit=pw.METRIC) as client:
        try:
            weather = await client.get(city)
            await msg.answer(f"Temperature in {weather.location} is {weather.temperature}°C, {weather.kind}")
        except pw.RequestError:
            await msg.answer("Incorrect city")


@dp.message(filters.CommandStart())
async def send_answer(msg: types.Message):
    database.addUser(msg.from_user.id, msg.from_user.username)
    await msg.answer("Hello!\nCommands:\n" +
                     "1. /phrase - Display a random phrase\n" +
                     "2. /weather [city] - Show the weather in the city\n" +
                     "3. /deadline [add/display/remove] - Manage deadlines")


@dp.message(filters.Command("deadline"))
async def deadline_handler(msg: types.Message, state: FSMContext):
    args = msg.text.split(" ")[1:]
    user_id = msg.from_user.id

    if not args:
        await msg.answer("Please use /deadline [add/display/remove]")
        return

    command = args[0]

    if command == "add":
        await msg.answer("Give the name of the task:")
        await state.set_state(DeadlineState.waiting_for_name)

    elif command == "display":
        deadlines = database.showDeadlines(user_id)
        if not deadlines:
            await msg.answer("No deadlines found.")
            return

        message = "Deadlines:\n"
        for i, deadline in enumerate(deadlines):
            try:
                deadline_date = datetime.datetime.strptime(deadline[4], "%Y-%m-%d")
                time_left = str(deadline_date - datetime.datetime.now()).split(".")[0]
            except ValueError:
                time_left = "Unknown"

            message += f"{i + 1}. {deadline[2]} | Date: {deadline[4]}\nTime left: {time_left}\n\n"
        await msg.answer(message)

    elif command == "remove":
        if len(args) < 2:
            await msg.answer("Please enter a Deadline ID to remove!")
            return

        try:
            deadline_id = int(args[1]) - 1
            deadlines = database.showDeadlines(user_id)
            if deadline_id < 0 or deadline_id >= len(deadlines):
                await msg.answer("Invalid deadline ID!")
                return

            database.removeDeadline(user_id, deadlines[deadline_id][0])
            await msg.answer(f"Deadline '{deadlines[deadline_id][2]}' removed!")
        except ValueError:
            await msg.answer("Please enter a valid numeric Deadline ID!")
        except Exception as e:
            await msg.answer(f"Error removing deadline: {str(e)}")
    else:
        await msg.answer("Invalid subcommand. Use: add, display, or remove.")


@dp.message(DeadlineState.waiting_for_name)
async def process_name(msg: types.Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("Specify the deadline date in the YYYY-MM-DD format:")
    await state.set_state(DeadlineState.waiting_for_date)



@dp.message(DeadlineState.waiting_for_date)
async def process_date(msg: types.Message, state: FSMContext):
    user_data = await state.get_data()
    user_id = msg.from_user.id
    name = user_data['name']

    try:
        date_end = datetime.datetime.strptime(msg.text, "%Y-%m-%d")
        if date_end < datetime.datetime.now():
            await msg.answer("The deadline is already expired!")
            return

        database.createDeadline(user_id, name, datetime.datetime.now().strftime('%Y-%m-%d'),
                                date_end.strftime('%Y-%m-%d'))

        deadline_id = database.get_latest_deadline_id(user_id)
        user_latest_deadline[user_id] = (deadline_id, name, date_end)

        await msg.answer(f"Deadline '{name}' added!\nDo you want to receive a task reminder?\nChoose one option:\n1.The exact time\n2. Every X hours\n3.Without reminder")
        await state.set_state(NotificationState.choosing_type)
    except ValueError:
        await msg.answer("Incorrect date format! Use YYYY-MM-DD.")



# --- Notification Flow ---

@dp.message(NotificationState.choosing_type)
async def choose_notification_type(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    choice = msg.text.strip()
    if choice == "1":
        await msg.answer("Send the exact notification time (YYYY-MM-DD HH:MM):")
        await state.set_state(NotificationState.setting_exact_time)
    elif choice == "2":
        await msg.answer("How often do you want to be reminded? (every X hours):")
        await state.set_state(NotificationState.setting_interval)
    else:
        await msg.answer("No reminder set.")
        await state.clear()


@dp.message(NotificationState.setting_exact_time)
async def set_exact_time(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    try:
        notify_time = datetime.datetime.strptime(msg.text.strip(), "%Y-%m-%d %H:%M")
        deadline_id, task_name, _ = user_latest_deadline[user_id]
        database.add_notification(user_id, deadline_id, notify_time.strftime("%Y-%m-%d %H:%M"), None)
        await msg.answer(f"You will be reminded about '{task_name}' at {notify_time}.")
    except ValueError:
        await msg.answer("Invalid time format! Use YYYY-MM-DD HH:MM")
    await state.clear()


@dp.message(NotificationState.setting_interval)
async def set_interval(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id
    try:
        interval = int(msg.text.strip())
        deadline_id, task_name, _ = user_latest_deadline[user_id]
        database.add_notification(user_id, deadline_id, None, interval)
        await msg.answer(f"You will be reminded about '{task_name}' every {interval} hours.")
    except ValueError:
        await msg.answer("Please enter a valid number of hours")
    await state.clear()

@dp.message(filters.Command("phrase"))
async def phrase_command_handler(msg: t.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Every 5 min", callback_data="phrase_5")],
        [InlineKeyboardButton(text="Every 15 min", callback_data="phrase_15")],
        [InlineKeyboardButton(text="Every 30 min", callback_data="phrase_30")],
        [InlineKeyboardButton(text="Every hour", callback_data="phrase_60")],
        [InlineKeyboardButton(text="Every 2 hours", callback_data="phrase_120")],
        [InlineKeyboardButton(text="Custom time", callback_data="phrase_custom")]
    ])
    await msg.answer("How often do you want to receive motivational quotes?", reply_markup=kb)


@dp.callback_query(lambda c: c.data.startswith("phrase_"))
async def handle_phrase_schedule_choice(query: t.CallbackQuery, state: FSMContext):
    user_id = query.from_user.id
    choice = query.data.replace("phrase_", "")
    if choice == "custom":
        await query.message.answer("Send the exact time to receive the quote (format: YYYY-MM-DD HH:MM)")
        await state.set_state("setting_custom_phrase_time")
    else:
        interval = int(choice)
        database.set_phrase_timer(user_id, interval_minutes=interval)
        await query.message.answer(f"You will now receive a quote every {interval} minutes!")
        await state.clear()


@dp.message(StateFilter("setting_custom_phrase_time"))
async def set_custom_phrase_time(msg: t.Message, state: FSMContext):
    user_id = msg.from_user.id
    try:
        dt = datetime.datetime.strptime(msg.text.strip(), "%Y-%m-%d %H:%M")
        database.set_phrase_timer(user_id, interval_minutes=None, custom_time=dt.strftime("%Y-%m-%d %H:%M"))
        await msg.answer(f"You will receive your next quote at {dt.strftime('%Y-%m-%d %H:%M')}.")
    except ValueError:
        await msg.answer("Invalid format! Please use YYYY-MM-DD HH:MM")
    await state.clear()


# --- Notification Background Task ---

async def send_phrase_quotes(bot, db):
    while True:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        user_ids = db.get_due_phrase_users(now)
        for uid in user_ids:
            await bot.send_message(uid, random.choice(config.PHRASES))
        await asyncio.sleep(60)


async def notification_loop(bot, db):
    while True:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        notifications = db.get_due_notifications(now)
        for notif in notifications:
            user_id, task_name = notif
            await bot.send_message(user_id, f"You have a reminder about {task_name}")
        await asyncio.sleep(60)


async def main():
    bot = aiogram.Bot(config.AIOGRAM_TOKEN)
    asyncio.create_task(notification_loop(bot, database))         # existing
    asyncio.create_task(send_phrase_quotes(bot, database))       # NEW
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
