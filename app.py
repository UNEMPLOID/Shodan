import asyncio
import logging
from datetime import datetime, timedelta
import aiogram
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import start_polling
import shodan
from collections import defaultdict
import httpx
import os

# Replace with your actual credentials and details
TELEGRAM_BOT_TOKEN = 'your_bot_token_here'
SHODAN_API_KEYS = ['your_shodan_api_key1', 'your_shodan_api_key2', 'your_shodan_api_key3']
GROUP_USERNAME = '@Indian_hacker_group'
CHANNEL_USERNAME = '@Falcon_Security'
OWNER_ID = 123456789  # Replace with the actual owner's user ID

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

current_shodan_api_index = 0
shodan_api = shodan.Shodan(SHODAN_API_KEYS[current_shodan_api_index])

# Store user data and queries
user_data = defaultdict(lambda: {'free_searches': 5, 'premium_searches': 15, 'subscription_end': None, 'active': True, 'last_reset': datetime.now()})
user_queries = {}

# Ensure directories for storing IPs exist
if not os.path.exists('ips'):
    os.makedirs('ips')
if not os.path.exists('sent_ips'):
    os.makedirs('sent_ips')

# Command handler to start the bot
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    
    keyboard = InlineKeyboardMarkup()
    join_chat_button = InlineKeyboardButton("Join Chat", url=f"https://t.me/Indian_Hacker_Group")
    join_channel_button = InlineKeyboardButton("Join Channel", url=f"https://t.me/Falcon_Security")
    joined_button = InlineKeyboardButton("Joined", callback_data="check_joined")
    help_button = InlineKeyboardButton("Help", url=f"https://t.me/Moon_God_Khonsu")

    keyboard.add(join_chat_button, join_channel_button)
    keyboard.add(joined_button)
    keyboard.add(help_button)

    await message.answer("Welcome to the bot!", reply_markup=keyboard)

# Check if user has joined required group and channel
@dp.callback_query_handler(lambda call: call.data == "check_joined")
async def check_joined(call: types.CallbackQuery):
    user_id = call.from_user.id
    try:
        is_in_group = (await bot.get_chat_member(GROUP_USERNAME, user_id)).status in ['member', 'administrator', 'creator']
        is_in_channel = (await bot.get_chat_member(CHANNEL_USERNAME, user_id)).status in ['member', 'administrator', 'creator']
        if is_in_group and is_in_channel:
            await call.message.answer("Welcome! Use /search <query> to search Shodan. You can make up to 5 searches per day for free.")
        else:
            await call.message.answer("Please join the required group and channel first.")
    except Exception as e:
        await call.message.answer(f"Error checking membership: {str(e)}")

# Command handler for Shodan search
@dp.message_handler(commands=['search'])
async def search_shodan(message: types.Message):
    user_id = message.from_user.id
    if not await check_membership(user_id):
        await message.reply("You must join our group and channel to use this bot.")
        return

    user_info = user_data[user_id]
    current_time = datetime.now()
    if (current_time - user_info['last_reset']).days >= 1:
        user_info['free_searches'] = 5
        user_info['premium_searches'] = 15
        user_info['last_reset'] = current_time
        user_data[user_id] = user_info

    if is_premium(user_id):
        if user_info['premium_searches'] <= 0:
            await message.reply("You have reached your daily search limit. Please wait until tomorrow for more searches.")
            return
    else:
        if user_info['free_searches'] <= 0:
            await message.reply("You have reached your daily search limit. Please subscribe for more searches.")
            return

    query = message.text[len('/search '):].strip()
    if not query:
        await message.reply("Please provide a query to search.")
        return

    await message.reply("Searching Shodan...")

    try:
        query_results = await check_and_search_query(query)

        if is_premium(user_id):
            user_info['premium_searches'] -= 1
        else:
            user_info['free_searches'] -= 1

        user_data[user_id] = user_info
        user_queries[user_id] = {
            'query': query,
            'results': query_results,
            'index': 0,
            'initial_ip_limit': 10,
            'additional_ip_limit': 20,
            'total_ips': len(query_results),
            'ips_sent': set()
        }
        await send_results(user_id, message.chat.id)
    except Exception as e:
        await message.reply(f"Error: {str(e)}")

async def send_results(user_id, chat_id):
    if user_id not in user_queries:
        return

    data = user_queries[user_id]
    index = data['index']
    results = data['results']
    ip_limit = data['initial_ip_limit']

    if index >= len(results):
        await bot.send_message(chat_id, "No more results.")
        return

    for i in range(index, min(index + ip_limit, len(results))):
        result = results[i]
        message = f"""
General Information:
Hostnames: {', '.join(result.get('hostnames', []))}
Domains: {', '.join(result.get('domains', []))}
Country: {result.get('location', {}).get('country_name', 'N/A')}
City: {result.get('location', {}).get('city', 'N/A')}
Organization: {result.get('org', 'N/A')}
ISP: {result.get('isp', 'N/A')}
ASN: {result.get('asn', 'N/A')}
IP: {result.get('ip_str')}
"""
        await bot.send_message(chat_id, message)
        await save_sent_ip(result['ip_str'], data['query'])

    data['index'] += ip_limit

    if data['index'] < len(results):
        if is_premium(user_id):
            if data['index'] < 60:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("Get More IPs (20)", callback_data="get_more_ips_20"))
                await bot.send_message(chat_id, f"Click 'Get More IPs (20)' to get more results. You have left {data['total_ips'] - data['index']} queries.")
            else:
                await bot.send_message(chat_id, f"Search another query. You have left {data['total_ips'] - data['index']} queries.")
        else:
            await bot.send_message(chat_id, f"Search another query. You have left {data['total_ips'] - data['index']} queries.")
    else:
        await bot.send_message(chat_id, "No more results.")

@dp.callback_query_handler(lambda call: call.data == "get_more_ips_20")
async def callback_get_more_ips_20(call: types.CallbackQuery):
    user_id = call.from_user.id
    if user_id not in user_queries:
        await call.answer("No more results.")
        return

    data = user_queries[user_id]

    if data['index'] >= len(data['results']):
        await call.answer("No more results.")
        return

    data['initial_ip_limit'] = 30  # Increase initial limit to 30 for the next batch
    await send_results(user_id, call.message.chat.id)

async def check_and_search_query(query):
    ip_file = f'ips/{query}.txt'
    sent_ip_file = f'sent_ips/{query}.txt'

    # If IPs for the query are already stored, read them from the file
    if os.path.exists(ip_file):
        with open(ip_file, 'r') as f:
            ips = [line.strip() for line in f]
    else:
        ips = []

    # Read sent IPs to avoid duplicates
    if os.path.exists(sent_ip_file):
        with open(sent_ip_file, 'r') as f:
            sent_ips = {line.strip() for line in f}
    else:
        sent_ips = set()

    # Filter out already sent IPs
    ips = [ip for ip in ips if ip not in sent_ips]

    # If there are no IPs left, search Shodan
    if not ips:
        async with httpx.AsyncClient() as client:
            response = await client.get(f'https://api.shodan.io/shodan/host/search?key={SHODAN_API_KEYS[current_shodan_api_index]}&query={query}')
            response.raise_for_status()
            results = response.json()['matches']
            ips = [result['ip_str'] for result in results]

        # Save new IPs to the file
        with open(ip_file, 'a') as f:
            for ip in ips:
                f.write(f"{ip}\n")

    return ips

async def save_sent_ip(ip, query):
    ip_file = f'ips/{query}.txt'
    sent_ip_file = f'sent_ips/{query}.txt'

    # Remove IP from the original file
    with open(ip_file, 'r') as f:
        ips = f.readlines()

    with open(ip_file, 'w') as f:
        for line in ips:
            if line.strip() != ip:
                f.write(line)

    # Save IP to the sent IP file
    with open(sent_ip_file, 'a') as f:
        f.write(f"{ip}\n")

async def rotate_shodan_api_key():
    global current_shodan_api_index
    current_shodan_api_index = (current_shodan_api_index + 1) % len(SHODAN_API_KEYS)
    global shodan_api
    shodan_api = shodan.Shodan(SHODAN_API_KEYS[current_shodan_api_index])

def is_premium(user_id):
    user_info = user_data[user_id]
    return user_info['subscription_end'] and user_info['subscription_end'] > datetime.now()

async def check_membership(user_id):
    try:
        is_in_group = (await bot.get_chat_member(GROUP_USERNAME, user_id)).status in ['member', 'administrator', 'creator']
        is_in_channel = (await bot.get_chat_member(CHANNEL_USERNAME, user_id)).status in ['member', 'administrator', 'creator']
        return is_in_group and is_in_channel
    except Exception:
        return False

# Command handler to add premium subscription to a user (owner feature)
@dp.message_handler(commands=['add_premium'])
async def add_premium(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("You are not authorized to use this command.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply("Usage: /add_premium <user_id> <days>")
        return

    user_id = int(args[1])
    days = int(args[2])
    if user_id in user_data:
        user_data[user_id]['subscription_end'] = datetime.now() + timedelta(days=days)
        await message.reply(f"Added {days} days of premium subscription for user {user_id}.")
    else:
        await message.reply("User not found.")

# Command handler to get user statistics (owner feature)
@dp.message_handler(commands=['stats'])
async def stats(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("You are not authorized to use this command.")
        return

    total_users = len(user_data)
    premium_users = sum(1 for user_id, user in user_data.items() if 'user_id' in user and is_premium(user_id))
    free_users = total_users - premium_users

    await message.reply(f"Total Users: {total_users}\nPremium Users: {premium_users}\nFree Users: {free_users}")

# Command handler to broadcast a message to all users (owner feature)
@dp.message_handler(commands=['broadcast'])
async def broadcast_message(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("You are not authorized to use this command.")
        return

    broadcast_text = message.text[len('/broadcast '):].strip()
    if not broadcast_text:
        await message.reply("Please provide a message to broadcast.")
        return

    for user_id in user_data:
        if user_data[user_id]['active']:
            try:
                await bot.send_message(user_id, broadcast_text)
            except Exception:
                user_data[user_id]['active'] = False

    await message.reply("Broadcast message sent.")

# Log and notify errors
async def log_and_notify_error(error_message):
    with open("error.log", "a") as f:
        f.write(f"{datetime.now()} - {error_message}\n")
    await bot.send_message(OWNER_ID, f"Error: {error_message}")

# Function to start bot with error handling and retries
async def start_bot():
    while True:
        try:
            await dp.start_polling()
        except Exception as e:
            await log_and_notify_error(f"Bot polling error: {str(e)}")
            await asyncio.sleep(15)

# Start bot in an asynchronous event loop
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_bot())
