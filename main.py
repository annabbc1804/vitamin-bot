import logging
import json
import os
from datetime import datetime, time
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext
)
import pytz

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Твой часовой пояс
TIMEZONE = pytz.timezone('Europe/Moscow')

# Файл для сохранения данных
DATA_FILE = 'vitamin_data.json'

class VitaminState:
    def __init__(self):
        self.morning_taken = False
        self.lunch_taken = False
        self.morning_reminder_count = 0
        self.lunch_reminder_count = 0
        self.last_reset = datetime.now(TIMEZONE).date().isoformat()
    
    def reset_if_new_day(self):
        today = datetime.now(TIMEZONE).date().isoformat()
        if today != self.last_reset:
            self.morning_taken = False
            self.lunch_taken = False
            self.morning_reminder_count = 0
            self.lunch_reminder_count = 0
            self.last_reset = today
    
    def to_dict(self):
        return {
            'morning_taken': self.morning_taken,
            'lunch_taken': self.lunch_taken,
            'morning_reminder_count': self.morning_reminder_count,
            'lunch_reminder_count': self.lunch_reminder_count,
            'last_reset': self.last_reset
        }
    
    @classmethod
    def from_dict(cls, data):
        state = cls()
        state.morning_taken = data.get('morning_taken', False)
        state.lunch_taken = data.get('lunch_taken', False)
        state.morning_reminder_count = data.get('morning_reminder_count', 0)
        state.lunch_reminder_count = data.get('lunch_reminder_count', 0)
        state.last_reset = data.get('last_reset', datetime.now(TIMEZONE).date().isoformat())
        return state

# Хранилище состояний
user_states = {}
registered_users = set()

def load_data():
    """Загружает данные из файла"""
    global user_states, registered_users
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_states = {
                    int(user_id): VitaminState.from_dict(state_data)
                    for user_id, state_data in data.get('states', {}).items()
                }
                registered_users = set(data.get('registered_users', []))
                logger.info(f"Загружены данные для {len(registered_users)} пользователей")
        except Exception as e:
            logger.error(f"Ошибка при загрузке данных: {e}")

def save_data():
    """Сохраняет данные в файл"""
    try:
        data = {
            'states': {
                str(user_id): state.to_dict()
                for user_id, state in user_states.items()
            },
            'registered_users': list(registered_users)
        }
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

def get_user_state(user_id):
    """Получает состояние пользователя"""
    if user_id not in user_states:
        user_states[user_id] = VitaminState()
    user_states[user_id].reset_if_new_day()
    save_data()
    return user_states[user_id]

def is_weekend():
    """Проверяет, выходной ли день"""
    return datetime.now(TIMEZONE).weekday() >= 5

def get_schedule_times():
    """Возвращает расписание напоминаний"""
    if is_weekend():
        return {
            'morning_first': time(13, 20),
            'morning_second': time(13, 40),
            'lunch_first': time(16, 0),
            'lunch_second': time(16, 20),
            'final': time(18, 45)
        }
    else:
        return {
            'morning_first': time(12, 20),
            'morning_second': time(12, 40),
            'lunch_first': time(15, 0),
            'lunch_second': time(15, 20),
            'final': time(17, 45)
        }

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Инициализируем состояние
    get_user_state(user_id)
    
    # Регистрируем пользователя
    if user_id not in registered_users:
        registered_users.add(user_id)
        save_data()
        
        # Создаём расписание для нового пользователя
        schedule_daily_reminders(context.application, user_id)
        logger.info(f"Новый пользователь зарегистрирован: {user_id} ({user_name})")
    
    day_type = "выходные" if is_weekend() else "будни"
    schedule = get_schedule_times()
    
    await update.message.reply_text(
        f"Привет, {user_name}! 🌟\n\n"
        f"Я буду напоминать тебе о витаминах!\n\n"
        f"📅 Расписание на {day_type}:\n"
        f"• {schedule['morning_first'].strftime('%H:%M')} - утренние витамины\n"
        f"• {schedule['lunch_first'].strftime('%H:%M')} - обеденные витамины\n"
        f"• {schedule['final'].strftime('%H:%M')} - последнее напоминание\n\n"
        f"Команды:\n"
        f"/status - посмотреть статус\n"
        f"/reset - сбросить на сегодня\n"
        f"/schedule - показать расписание"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статус витаминов"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    
    morning_icon = "✅" if state.morning_taken else "❌"
    lunch_icon = "✅" if state.lunch_taken else "❌"
    
    message = (
        f"Статус на сегодня ({datetime.now(TIMEZONE).strftime('%d.%m.%Y')}):\n\n"
        f"{morning_icon} Утренние витамины\n"
        f"{lunch_icon} Обеденные витамины"
    )
    
    if state.morning_taken and state.lunch_taken:
        message += "\n\n🎉 Все витамины приняты! Молодец!"
    
    await update.message.reply_text(message)

async def schedule_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает расписание напоминаний"""
    schedule = get_schedule_times()
    day_type = "выходные" if is_weekend() else "будни"
    
    await update.message.reply_text(
        f"📅 Расписание на {day_type}:\n\n"
        f"⏰ Утренние витамины:\n"
        f"  • {schedule['morning_first'].strftime('%H:%M')} - первое напоминание\n"
        f"  • {schedule['morning_second'].strftime('%H:%M')} - повтор\n\n"
        f"⏰ Обеденные витамины:\n"
        f"  • {schedule['lunch_first'].strftime('%H:%M')} - первое напоминание\n"
        f"  • {schedule['lunch_second'].strftime('%H:%M')} - повтор\n\n"
        f"⏰ Финальное:\n"
        f"  • {schedule['final'].strftime('%H:%M')} - последний шанс! 😊"
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросивает статус витаминов"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    state.morning_taken = False
    state.lunch_taken = False
    state.morning_reminder_count = 0
    state.lunch_reminder_count = 0
    save_data()
    
    await update.message.reply_text("Статус сброшен! Можно начинать заново 🔄")

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ответы пользователя"""
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    text = update.message.text.lower().strip()
    
    if text == "да":
        if not state.morning_taken:
            state.morning_taken = True
            save_data()
            await update.message.reply_text("Супер! Утренние витамины приняты! 💊✨")
        elif not state.lunch_taken:
            state.lunch_taken = True
            save_data()
            await update.message.reply_text("Супер! Обеденные витамины приняты! 💊✨")
        else:
            await update.message.reply_text("Всё уже принято на сегодня! 🎉")
    
    elif text == "нет":
        await update.message.reply_text("Хорошо, напомню позже! ⏰")
    
    else:
        await update.message.reply_text(
            "Пожалуйста, используй кнопки 'Да' или 'Нет', "
            "или команды /status, /reset, /schedule 😊"
        )

async def send_vitamin_reminder(context: CallbackContext):
    """Отправляет напоминание о витаминах"""
    user_id = context.job.chat_id
    state = get_user_state(user_id)
    
    keyboard = [['Да', 'Нет']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    reminder_type = context.job.data.get('type')
    
    try:
        if reminder_type == 'morning_first':
            if not state.morning_taken:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🌅 Доброе утро! Время утренних витаминов! 💊\n\nУспеваешь принять?",
                    reply_markup=reply_markup
                )
                state.morning_reminder_count = 1
        
        elif reminder_type == 'morning_second':
            if not state.morning_taken:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏰ Напоминаю про утренние витамины! 💊\n\nУспеваешь принять?",
                    reply_markup=reply_markup
                )
                state.morning_reminder_count = 2
        
        elif reminder_type == 'lunch_first':
            if not state.morning_taken and not state.lunch_taken:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "🍽 Время обеденных витаминов! 💊\n\n"
                        "⚠️ Кажется, утренние витамины ещё не приняты!\n\n"
                        "Успеваешь принять ОБА вида?"
                    ),
                    reply_markup=reply_markup
                )
            elif not state.lunch_taken:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🍽 Время обеденных витаминов! 💊\n\nУспеваешь принять?",
                    reply_markup=reply_markup
                )
            state.lunch_reminder_count = 1
        
        elif reminder_type == 'lunch_second':
            if not state.morning_taken and not state.lunch_taken:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⏰ Напоминаю про витамины! 💊\n\n"
                        "⚠️ Утренние и обеденные ещё не приняты!\n\n"
                        "Успеваешь принять оба вида?"
                    ),
                    reply_markup=reply_markup
                )
            elif not state.lunch_taken:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⏰ Напоминаю про обеденные витамины! 💊\n\nУспеваешь принять?",
                    reply_markup=reply_markup
                )
        
        elif reminder_type == 'final':
            messages = []
            if not state.morning_taken:
                messages.append("утренние 🌅")
            if not state.lunch_taken:
                messages.append("обеденные 🍽")
            
            if messages:
                vitamins_text = " и ".join(messages)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🚨 Последнее напоминание на сегодня! 🚨\n\n"
                        f"Не забыты {vitamins_text} витамины!\n\n"
                        f"Успеваешь принять?"
                    ),
                    reply_markup=reply_markup
                )
            else:
                # Все приняты - поздравляем!
                await context.bot.send_message(
                    chat_id=user_id,
                    text="🎉 Отлично! Сегодня все витамины приняты! Молодец! 💪✨"
                )
        
        save_data()
    
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")

def schedule_daily_reminders(application, user_id):
    """Создаёт расписание напоминаний"""
    job_queue = application.job_queue
    
    # Удаляем старые задания для этого пользователя
    current_jobs = job_queue.get_jobs_by_name(f'morning_first_{user_id}')
    for job in current_jobs:
        job.schedule_removal()
    
    # Создаём новые задания
    times_weekday = {
        'morning_first': time(12, 20),
        'morning_second': time(12, 40),
        'lunch_first': time(15, 0),
        'lunch_second': time(15, 20),
        'final': time(17, 45)
    }
    
    times_weekend = {
        'morning_first': time(13, 20),
        'morning_second': time(13, 40),
        'lunch_first': time(16, 0),
        'lunch_second': time(16, 20),
        'final': time(18, 45)
    }
    
    # Будние дни
    for reminder_type, reminder_time in times_weekday.items():
        job_queue.run_daily(
            send_vitamin_reminder,
            time=reminder_time,
            days=(0, 1, 2, 3, 4),  # пн-пт
            chat_id=user_id,
            data={'type': reminder_type},
            name=f'{reminder_type}_{user_id}_weekday'
        )
    
    # Выходные
    for reminder_type, reminder_time in times_weekend.items():
        job_queue.run_daily(
            send_vitamin_reminder,
            time=reminder_time,
            days=(5, 6),  # сб-вс
            chat_id=user_id,
            data={'type': reminder_type},
            name=f'{reminder_type}_{user_id}_weekend'
        )

async def post_init(application: Application):
    """Инициализация после запуска бота"""
    load_data()
    
    # Создаём расписание для всех зарегистрированных пользователей
    for user_id in registered_users:
        schedule_daily_reminders(application, user_id)
    
    logger.info(f"Бот запущен! Зарегистрировано пользователей: {len(registered_users)}")

def main():
    """Запуск бота"""
    # Получаем токен из переменной окружения
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not TOKEN:
        logger.error("ОШИБКА: Не найдена переменная окружения TELEGRAM_BOT_TOKEN!")
        logger.error("Установите токен в настройках Render в разделе Environment Variables")
        return
    
    # Создаём приложение
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("schedule", schedule_info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_response))
    
    logger.info("Запуск бота...")
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
