import json
from requests import get
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
import logging
from datetime import datetime

api_token = 'uMJqLYKFvfdmhpPmouRsvolTID66hl1obk7XFEU_Qza8'
filename = 'dataRUSLAN.json'
backup_filename = 'dataRUSLAN_prev.json'
currency_filename = 'currency.json'
telegram_token = '7857285822:AAEDqun5b7bpH77taeI7s5CdFy8pEZWPKtU'
users_filename = 'bot_users.json'
banned_filename = 'banned_users.json'

currency_map = {
    980: 'UAH',
    840: 'USD',
    978: 'EUR'
}

OWNER_ID = 752113604  # <-- замените на свой Telegram user_id

# --- Logging setup ---
LOG_FILENAME = 'bot.log'
logging.basicConfig(
    filename=LOG_FILENAME,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    encoding='utf-8'
)

def log_event(msg):
    logging.info(msg)

def get_currency_rates():
    currency_data = get("https://api.monobank.ua/bank/currency").json()
    # Исправление: если currency_data - это dict, а не список, берем список по ключу
    if isinstance(currency_data, dict):
        # Иногда API возвращает ошибку или сообщение, а не список валют
        # В этом случае пробуем взять из бэкапа
        try:
            with open(currency_filename, 'r', encoding='utf-8') as f:
                currency_data = json.load(f)
        except Exception:
            return [], None, None
        # Если после этого currency_data всё ещё не список, возвращаем пусто
        if not isinstance(currency_data, list):
            return [], None, None
    with open(currency_filename, 'w', encoding='utf-8') as f:
        json.dump(currency_data, f, indent=4, ensure_ascii=False)
    usd_uah = next((c for c in currency_data if isinstance(c, dict) and c.get('currencyCodeA') == 840 and c.get('currencyCodeB') == 980), None)
    eur_uah = next((c for c in currency_data if isinstance(c, dict) and c.get('currencyCodeA') == 978 and c.get('currencyCodeB') == 980), None)
    return currency_data, usd_uah, eur_uah

def get_accounts_info(new_data, old_data):
    # Если не удалось получить новые данные, используем данные из бэкапа
    if not new_data or 'accounts' not in new_data or not isinstance(new_data['accounts'], list):
        try:
            with open(backup_filename, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
        except Exception:
            new_data = {"accounts": []}
    if not old_data or 'accounts' not in old_data or not isinstance(old_data['accounts'], list):
        old_data = {"accounts": []}
    accounts_info = []
    for acc in new_data.get('accounts', []):
        acc_id = acc.get('id')
        new_balance = acc.get('balance', 0)
        old_balance = next((a.get('balance', 0) for a in old_data.get('accounts', []) if a.get('id') == acc_id), new_balance)
        # Если старых данных нет, считаем что баланс не изменился
        diff = (new_balance - old_balance) / 100
        masked_pan = acc.get('maskedPan', ['----'])
        last4 = masked_pan[0][-4:] if masked_pan else '----'
        currency = currency_map.get(acc.get('currencyCode'), str(acc.get('currencyCode')))
        accounts_info.append({
            'id': acc_id,
            'last4': last4,
            'currency': currency,
            'old_balance': old_balance,
            'new_balance': new_balance,
            'diff': diff
        })
    accounts_info.sort(key=lambda x: x['new_balance'], reverse=True)
    return accounts_info

def format_accounts(accounts_info):
    lines = []
    for acc in accounts_info:
        old_b = acc['old_balance'] / 100
        new_b = acc['new_balance'] / 100
        diff = acc['diff']
        last4 = acc['last4']
        currency = acc['currency']
        # Если старый баланс равен новому, не выводим стрелку и изменение
        if old_b != new_b:
            lines.append(f"Карта *{last4} ({currency}): {old_b:.2f} → {new_b:.2f} (изменение: {diff:+.2f} {currency})")
        else:
            lines.append(f"Карта *{last4} ({currency}): {new_b:.2f} (без изменений)")
    return "\n".join(lines)

def format_rates(usd_uah, eur_uah):
    lines = []
    if usd_uah:
        lines.append(f"\nUSD/UAH: цена за покупку: {usd_uah.get('rateBuy', 'N/A')} | цена на продажу: {usd_uah.get('rateSell', 'N/A')}")
    else:
        lines.append("\nUSD/UAH: нет данных")
    if eur_uah:
        lines.append(f"EUR/UAH: цена за покупку: {eur_uah.get('rateBuy', 'N/A')} | цена на продажу: {eur_uah.get('rateSell', 'N/A')}")
    else:
        lines.append("EUR/UAH: нет данных")
    return "\n".join(lines)

# --- Aiogram Bot ---
bot = Bot(token=telegram_token)
dp = Dispatcher()
chat_ids = set()

def save_user(user_id, username=None, first_name=None, last_name=None):
    try:
        with open(users_filename, 'r', encoding='utf-8') as f:
            users = json.load(f)
    except Exception:
        users = []
    # Исправление: поддержка старого формата (список int) и нового (список dict)
    new_users = []
    exists = False
    for user in users:
        if isinstance(user, int):
            # Старый формат, преобразуем в dict
            if user == user_id:
                exists = True
                new_users.append({
                    "id": user_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name
                })
            else:
                new_users.append({"id": user})
        elif isinstance(user, dict):
            if user.get("id") == user_id:
                exists = True
                user["username"] = username
                user["first_name"] = first_name
                user["last_name"] = last_name
            new_users.append(user)
    if not exists:
        new_users.append({
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name
        })
    with open(users_filename, 'w', encoding='utf-8') as f:
        json.dump(new_users, f, indent=4, ensure_ascii=False)

def is_banned(user_id):
    try:
        with open(banned_filename, 'r', encoding='utf-8') as f:
            banned = set(json.load(f))
    except Exception:
        banned = set()
    return user_id in banned

def ban_user(user_id):
    try:
        with open(banned_filename, 'r', encoding='utf-8') as f:
            banned = set(json.load(f))
    except Exception:
        banned = set()
    banned.add(user_id)
    with open(banned_filename, 'w', encoding='utf-8') as f:
        json.dump(list(banned), f, indent=4, ensure_ascii=False)

def unban_user(user_id):
    try:
        with open(banned_filename, 'r', encoding='utf-8') as f:
            banned = set(json.load(f))
    except Exception:
        banned = set()
    banned.discard(user_id)
    with open(banned_filename, 'w', encoding='utf-8') as f:
        json.dump(list(banned), f, indent=4, ensure_ascii=False)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    log_event(f"/start from {message.chat.id}")
    if is_banned(message.chat.id):
        await message.answer("Вам заборонено користуватись ботом.")
        return
    chat_ids.add(message.chat.id)
    save_user(
        message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    await message.answer("Привіт, я проєкт для практики Руслана. Використовуйте /status для актуальної інформації")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    log_event(f"/status from {message.chat.id}")
    if is_banned(message.chat.id):
        await message.answer("Вам заборонено користуватись ботом.")
        return
    chat_ids.add(message.chat.id)
    save_user(
        message.chat.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    # Пробуем получить новые данные, если не получается — используем бэкап
    try:
        new_data = get("https://api.monobank.ua/personal/client-info", headers={'X-Token': api_token}).json()
        # Проверяем, что данные валидные
        if not new_data or 'accounts' not in new_data or not isinstance(new_data['accounts'], list):
            raise Exception("No accounts in new_data")
    except Exception:
        try:
            with open(backup_filename, 'r', encoding='utf-8') as f:
                new_data = json.load(f)
        except Exception:
            new_data = {"accounts": []}
    # Для баланса используем сравнение с предыдущими (бэкап)
    try:
        with open(backup_filename, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
    except Exception:
        old_data = {"accounts": []}
    currency_data, usd_uah, eur_uah = get_currency_rates()
    accounts_info = get_accounts_info(new_data, old_data)
    msg = "--- Текущая информация ---\n"
    msg += format_accounts(accounts_info)
    msg += "\n"
    msg += format_rates(usd_uah, eur_uah)
    await message.answer(msg)

@dp.message(Command("users"))
async def cmd_users(message: Message):
    log_event(f"/users from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас нет доступа к этому списку.")
        return
    try:
        with open(users_filename, 'r', encoding='utf-8') as f:
            users = json.load(f)
        users_list = []
        for u in users:
            info = f"id: {u.get('id')}"
            if u.get('username'):
                info += f", username: @{u['username']}"
            if u.get('first_name'):
                info += f", name: {u['first_name']}"
            if u.get('last_name'):
                info += f" {u['last_name']}"
            users_list.append(info)
        await message.answer("Пользователи бота:\n" + "\n".join(users_list))
    except Exception:
        await message.answer("Не удалось получить список пользователей.")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    log_event(f"/broadcast from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас нет доступа к этой команде.")
        return
    text = message.text.partition(' ')[2].strip()
    if not text:
        await message.answer("Введіть текст для розсилки: /broadcast Ваш текст")
        return
    try:
        with open(users_filename, 'r', encoding='utf-8') as f:
            users = json.load(f)
        count = 0
        for u in users:
            uid = u["id"] if isinstance(u, dict) else u
            if not is_banned(uid):
                try:
                    await bot.send_message(chat_id=uid, text=text)
                    count += 1
                except Exception:
                    pass
        await message.answer(f"Розіслано {count} користувачам.")
    except Exception:
        await message.answer("Не вдалося зробити розсилку.")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    log_event(f"/ban from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас нет доступа к этой команде.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Використання: /ban <user_id>")
        return
    try:
        user_id = int(parts[1])
        ban_user(user_id)
        await message.answer(f"Користувач {user_id} заблокований.")
    except Exception:
        await message.answer("Не вдалося заблокувати користувача.")

@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    log_event(f"/unban from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас нет доступа к этой команде.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Використання: /unban <user_id>")
        return
    try:
        user_id = int(parts[1])
        unban_user(user_id)
        await message.answer(f"Користувач {user_id} розблокований.")
    except Exception:
        await message.answer("Не вдалося розблокувати користувача.")

# --- New admin commands ---

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    log_event(f"/stats from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас немає доступу до цієї команди.")
        return
    try:
        with open(users_filename, 'r', encoding='utf-8') as f:
            users = json.load(f)
        with open(banned_filename, 'r', encoding='utf-8') as f:
            banned = set(json.load(f))
    except Exception:
        users = []
        banned = set()
    total_users = len(users)
    banned_users = len(banned)
    active_users = total_users - banned_users
    try:
        last_update = datetime.fromtimestamp(
            max(
                os.path.getmtime(filename),
                os.path.getmtime(backup_filename)
            )
        ).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        last_update = "Немає даних"
    msg = (
        f"📊 Статистика бота:\n"
        f"Загальна кількість користувачів: {total_users}\n"
        f"Забанено: {banned_users}\n"
        f"Активних: {active_users}\n"
        f"Останнє оновлення: {last_update}"
    )
    await message.answer(msg)

@dp.message(Command("logs"))
async def cmd_logs(message: Message):
    log_event(f"/logs from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас немає доступу до цієї команди.")
        return
    try:
        N = 30  # lines to show
        with open(LOG_FILENAME, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-N:]
        text = ''.join(lines)
        if not text:
            text = "Логи порожні."
        # Telegram message limit: 4096 chars
        if len(text) > 4000:
            text = text[-4000:]
        await message.answer(f"Останні логи:\n<pre>{text}</pre>", parse_mode="HTML")
    except Exception as e:
        await message.answer("Не вдалося отримати логи.")

@dp.message(Command("testmsg"))
async def cmd_testmsg(message: Message):
    log_event(f"/testmsg from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас немає доступу до цієї команди.")
        return
    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Використання: /testmsg <user_id> <текст>")
        return
    try:
        user_id = int(parts[1])
        text = parts[2]
        await bot.send_message(chat_id=user_id, text=text)
        await message.answer(f"Тестове повідомлення надіслано користувачу {user_id}.")
    except Exception as e:
        await message.answer("Не вдалося надіслати повідомлення.")

@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    log_event(f"/ping from {message.chat.id}")
    await message.answer("Я на зв'язку!")

@dp.message(Command("helpadmin"))
async def cmd_helpadmin(message: Message):
    log_event(f"/helpadmin from {message.chat.id}")
    if message.from_user.id != OWNER_ID:
        await message.answer("У вас немає доступу до цієї команди.")
        return
    help_text = (
        "🛠 <b>Адмінські команди:</b>\n"
        "/users — список усіх користувачів бота\n"
        "/broadcast &lt;текст&gt; — розсилка повідомлення всім користувачам\n"
        "/ban &lt;user_id&gt; — заблокувати користувача\n"
        "/unban &lt;user_id&gt; — розблокувати користувача\n"
        "/stats — статистика: кількість користувачів, забанених, активних, останній апдейт\n"
        "/logs — отримати останні логи роботи бота\n"
        "/testmsg &lt;user_id&gt; &lt;текст&gt; — надіслати тестове повідомлення конкретному користувачу\n"
        "/ping — перевірити, чи бот працює\n"
        "/helpadmin — список усіх адмінських команд з коротким описом"
    )
    await message.answer(help_text, parse_mode="HTML")

# --- Error logging for all handlers ---
from aiogram import F
@dp.errors()
async def error_handler(update, exception):
    log_event(f"Error: {exception}")
    return True

async def periodic_update():
    prev_balances = None
    prev_rates = None
    while True:
        old_data = get_old_data()
        new_data = get("https://api.monobank.ua/personal/client-info", headers={'X-Token': api_token}).json()
        save_new_data(new_data)
        currency_data, usd_uah, eur_uah = get_currency_rates()
        accounts_info = get_accounts_info(new_data, old_data)
        curr_balances = balances_snapshot(accounts_info)
        curr_rates = rates_snapshot(usd_uah, eur_uah)

        if curr_balances != prev_balances or curr_rates != prev_rates:
            msg = "--- Обновление данных ---\n"
            msg += format_accounts(accounts_info)
            msg += "\n"
            msg += format_rates(usd_uah, eur_uah)
            # Виправлення: отримуємо chat_id тільки з users_filename, і фільтруємо забанених
            try:
                with open(users_filename, 'r', encoding='utf-8') as f:
                    users = json.load(f)
                for u in users:
                    uid = u["id"] if isinstance(u, dict) else u
                    if not is_banned(uid):
                        try:
                            await bot.send_message(chat_id=uid, text=msg)
                        except Exception:
                            pass
            except Exception:
                pass
            prev_balances = curr_balances
            prev_rates = curr_rates

        await asyncio.sleep(61)

def get_old_data():
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(old_data, f, indent=4, ensure_ascii=False)
    except FileNotFoundError:
        old_data = {"accounts": []}
    return old_data

def save_new_data(new_data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, indent=4, ensure_ascii=False)

def balances_snapshot(accounts_info):
    return [(acc['id'], acc['new_balance']) for acc in accounts_info]

def rates_snapshot(usd_uah, eur_uah):
    return (
        usd_uah.get('rateBuy', None) if usd_uah else None,
        usd_uah.get('rateSell', None) if usd_uah else None,
        eur_uah.get('rateBuy', None) if eur_uah else None,
        eur_uah.get('rateSell', None) if eur_uah else None
    )

async def main():
    # Запуск бота и периодической задачи
    asyncio.create_task(periodic_update())
    await dp.start_polling(bot)

if __name__ == "__main__":
    import sys
    import os
    if sys.platform.startswith('win') and sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # --- Автоматический запуск при старте системы (Windows) ---
    # Создаём ярлык в папке автозагрузки, если его ещё нет
    try:
        import winshell
        from win32com.client import Dispatch

        startup = os.path.join(os.environ["APPDATA"], "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
        script_path = os.path.abspath(__file__)
        shortcut_path = os.path.join(startup, "TelegramBotRuslan.lnk")
        if not os.path.exists(shortcut_path):
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = sys.executable
            shortcut.Arguments = f'"{script_path}"'
            shortcut.WorkingDirectory = os.path.dirname(script_path)
            shortcut.IconLocation = sys.executable
            shortcut.save()
    except Exception:
        pass  # Не критично, если не удалось создать ярлык

    asyncio.run(main())

# --- Адмінські команди ---
# /users - список усіх користувачів бота
# /broadcast <текст> - розсилка повідомлення всім користувачам
# /ban <user_id> - заблокувати користувача
# /unban <user_id> - розблокувати користувача
# /stats - статистика бота
# /logs - останні логи роботи бота
# /testmsg <user_id> <текст> - надіслати тестове повідомлення користувачу
# /ping - перевірка зв'язку з ботом
# /helpadmin - допомога по адмінським командам



