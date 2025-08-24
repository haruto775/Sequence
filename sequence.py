import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
import re
from collections import defaultdict
from pymongo import MongoClient
from config import API_HASH, API_ID, BOT_TOKEN, MONGO_URI, START_PIC, START_MSG, HELP_TXT, OWNER_ID

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["sequence_bot"]
users_collection = db["users_sequence"]

app = Client("sequence_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_sequences = {}  # Stores files, resolution order, and sequence mode per user

# Patterns for extracting episode numbers
patterns = [
    re.compile(r'\b(?:EP|E)\s*-\s*(\d{1,3})\b', re.IGNORECASE),
    re.compile(r'\b(?:EP|E)\s*(\d{1,3})\b', re.IGNORECASE),
    re.compile(r'S(\d+)(?:E|EP)(\d+)', re.IGNORECASE),
    re.compile(r'S(\d+)\s*(?:E|EP|-\s*EP)\s*(\d+)', re.IGNORECASE),
    re.compile(r'(?:[([<{]?\s*(?:E|EP)\s*(\d+)\s*[)\]>}]?)', re.IGNORECASE),
    re.compile(r'(?:EP|E)?\s*[-]?\s*(\d{1,3})', re.IGNORECASE),
    re.compile(r'S(\d+)[^\d]*(\d+)', re.IGNORECASE),
    re.compile(r'(\d+)')
]

# Pattern for extracting resolution
resolution_pattern = re.compile(r'(\d{3,4}p|4k)', re.IGNORECASE)

def extract_episode_number(filename):
    for pattern in patterns:
        match = pattern.search(filename)
        if match:
            return int(match.groups()[-1])
    return float('inf')

def extract_resolution(filename):
    match = resolution_pattern.search(filename)
    if match:
        return match.group(1).lower()  # Returns '360p', '480p', '720p', '1080p', '4k', etc.
    return 'unknown'

# Default resolution order
default_resolution_order = {
    '360p': 1,
    '480p': 2,
    '720p': 3,
    '1080p': 4,
    '4k': 5
}

@app.on_message(filters.command("start"))
async def start_command(client, message):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Help", callback_data='help'),
            InlineKeyboardButton("Close", callback_data='close')
        ],
        [
            InlineKeyboardButton("Set Resolution Order", callback_data='set_resolution'),
            InlineKeyboardButton("Set Sequence Mode", callback_data='set_mode')
        ],
        [
            InlineKeyboardButton("Show Settings", callback_data='show_settings'),
            InlineKeyboardButton("OWNER", url='https://t.me/Its_Sahil_Ansari')
        ]
    ])

    await client.send_photo(
        chat_id=message.chat.id,
        photo=START_PIC,
        caption=START_MSG,
        reply_markup=buttons,
    )

@app.on_message(filters.command("startsequence"))
async def start_sequence(client, message):
    user_id = message.from_user.id
    if user_id not in user_sequences:
        user_sequences[user_id] = {
            'files': [],
            'resolution_order': default_resolution_order.copy(),
            'sequence_mode': 'episode'  # Default to episode-first mode
        }
        logger.info(f"User {user_id} started sequence mode")
    await message.reply_text("✅ Sequence mode started! Send your files now. Use /setresolutionorder, /setsequencemode, or /showsettings to customize.")

@app.on_message(filters.command("setresolutionorder"))
async def set_resolution_order(client, message):
    user_id = message.from_user.id
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("360p First", callback_data='res_360p'),
            InlineKeyboardButton("480p First", callback_data='res_480p')
        ],
        [
            InlineKeyboardButton("720p First", callback_data='res_720p'),
            InlineKeyboardButton("1080p First", callback_data='res_1080p')
        ],
        [
            InlineKeyboardButton("4k First", callback_data='res_4k'),
            InlineKeyboardButton("Reset to Default", callback_data='res_default')
        ]
    ])
    await message.reply_text(
        "📏 Choose the resolution to prioritize:",
        reply_markup=buttons
    )
    logger.info(f"User {user_id} requested resolution order selection")

@app.on_message(filters.command("setsequencemode"))
async def set_sequence_mode(client, message):
    user_id = message.from_user.id
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Episode First", callback_data='mode_episode'),
            InlineKeyboardButton("Resolution First", callback_data='mode_resolution')
        ]
    ])
    await message.reply_text(
        "📋 Choose sequencing mode:\n"
        "- Episode First: Sends all resolutions for each episode.\n"
        "- Resolution First: Sends all episodes for each resolution.",
        reply_markup=buttons
    )
    logger.info(f"User {user_id} requested sequence mode selection")

@app.on_message(filters.command("showsettings"))
async def show_settings(client, message):
    user_id = message.from_user.id
    if user_id not in user_sequences:
        user_sequences[user_id] = {
            'files': [],
            'resolution_order': default_resolution_order.copy(),
            'sequence_mode': 'episode'
        }
    
    resolution_order = user_sequences[user_id]['resolution_order']
    sorted_resolutions = sorted(resolution_order.items(), key=lambda x: x[1])
    resolution_text = ", ".join(res[0] for res in sorted_resolutions)
    sequence_mode = user_sequences[user_id]['sequence_mode'].capitalize()
    
    await message.reply_text(
        f"⚙️ **Current Settings**\n"
        f"**Sequence Mode**: {sequence_mode} First\n"
        f"**Resolution Order**: {resolution_text}"
    )
    logger.info(f"User {user_id} viewed settings: mode={sequence_mode}, resolution_order={resolution_text}")

@app.on_message(filters.command("endsequence"))
async def end_sequence(client, message):
    user_id = message.from_user.id
    if user_id not in user_sequences or not user_sequences[user_id]['files']:
        await message.reply_text("❌ No files in sequence!")
        return

    sequence_mode = user_sequences[user_id].get('sequence_mode', 'episode')
    logger.info(f"User {user_id} ending sequence with mode: {sequence_mode}")

    if sequence_mode == 'resolution':
        sorted_files = sorted(
            user_sequences[user_id]['files'],
            key=lambda x: (
                user_sequences[user_id]['resolution_order'].get(extract_resolution(x["filename"]), float('inf')),
                extract_episode_number(x["filename"])
            )
        )
    else:  # episode-first
        sorted_files = sorted(
            user_sequences[user_id]['files'],
            key=lambda x: (
                extract_episode_number(x["filename"]),
                user_sequences[user_id]['resolution_order'].get(extract_resolution(x["filename"]), float('inf'))
            )
        )

    for file in sorted_files:
        await client.copy_message(message.chat.id, from_chat_id=file["chat_id"], message_id=file["msg_id"])
        await asyncio.sleep(0.1)

    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"files_sequenced": len(user_sequences[user_id]['files'])}, "$set": {"username": message.from_user.first_name}},
        upsert=True
    )

    del user_sequences[user_id]
    await message.reply_text("✅ All files have been sequenced!")
    logger.info(f"User {user_id} completed sequencing {len(sorted_files)} files")

@app.on_message(filters.document | filters.video | filters.audio)
async def store_file(client, message):
    user_id = message.from_user.id
    if user_id in user_sequences:
        file_name = (
            message.document.file_name if message.document else
            message.video.file_name if message.video else
            message.audio.file_name if message.audio else
            "Unknown"
        )
        user_sequences[user_id]['files'].append({"filename": file_name, "msg_id": message.id, "chat_id": message.chat.id})
        await message.reply_text("📂 Your file has been added to the sequence!")
        logger.info(f"User {user_id} added file: {file_name}")
    else:
        await message.reply_text("❌ You need to start sequence mode first using /startsequence.")

@app.on_message(filters.command("leaderboard"))
async def leaderboard(client, message):
    top_users = users_collection.find().sort("files_sequenced", -1).limit(5)
    leaderboard_text = "**🏆 Top Users 🏆**\n\n"

    for index, user in enumerate(top_users, start=1):
        leaderboard_text += f"**{index}. {user['username']}** - {user['files_sequenced']} files\n"

    if not leaderboard_text.strip():
        leaderboard_text = "No data available!"

    await message.reply_text(leaderboard_text)
    logger.info(f"User {message.from_user.id} viewed leaderboard")

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(client, message):
    if len(message.command) < 2:
        await message.reply_text("**Usage:** `/broadcast Your message here`")
        return

    broadcast_text = message.text.split(" ", 1)[1]
    users = users_collection.find({}, {"user_id": 1})

    count = 0
    for user in users:
        try:
            await client.send_message(user["user_id"], broadcast_text)
            count += 1
        except Exception as e:
            logger.error(f"Failed to broadcast to user {user['user_id']}: {e}")

    await message.reply_text(f"✅ Broadcast sent to {count} users.")
    logger.info(f"Broadcast sent to {count} users by {message.from_user.id}")

@app.on_message(filters.command("users") & filters.user(OWNER_ID))
async def get_users(client, message):
    user_count = users_collection.count_documents({})
    await message.reply_text(f"📊 **Total Users:** {user_count}")
    logger.info(f"User {message.from_user.id} checked user count: {user_count}")

@app.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    logger.info(f"Received callback query: {data} from user {user_id}")

    # Initialize user_sequences if not present
    if user_id not in user_sequences:
        user_sequences[user_id] = {
            'files': [],
            'resolution_order': default_resolution_order.copy(),
            'sequence_mode': 'episode'
        }
        logger.info(f"Initialized user_sequences for user {user_id}")

    try:
        if data == "help":
            await query.message.edit_text(
                text=HELP_TXT.format(first=query.from_user.first_name),
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton('Back', callback_data='start'),
                            InlineKeyboardButton("Close", callback_data='close')
                        ]
                    ]
                )
            )
        elif data == "start":
            await query.message.edit_text(
                text=START_MSG.format(first=query.from_user.first_name),
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("Help", callback_data='help'),
                        InlineKeyboardButton("Close", callback_data='close')
                    ],
                    [
                        InlineKeyboardButton("Set Resolution Order", callback_data='set_resolution'),
                        InlineKeyboardButton("Set Sequence Mode", callback_data='set_mode')
                    ],
                    [
                        InlineKeyboardButton("Show Settings", callback_data='show_settings'),
                        InlineKeyboardButton("OWNER", url='https://t.me/Its_Sahil_Ansari')
                    ]
                ])
            )
        elif data == "close":
            await query.message.delete()
            try:
                await query.message.reply_to_message.delete()
            except:
                pass
        elif data == "set_resolution":
            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("360p First", callback_data='res_360p'),
                    InlineKeyboardButton("480p First", callback_data='res_480p')
                ],
                [
                    InlineKeyboardButton("720p First", callback_data='res_720p'),
                    InlineKeyboardButton("1080p First", callback_data='res_1080p')
                ],
                [
                    InlineKeyboardButton("4k First", callback_data='res_4k'),
                    InlineKeyboardButton("Reset to Default", callback_data='res_default')
                ]
            ])
            await query.message.edit_text(
                "📏 Choose the resolution to prioritize:",
                reply_markup=buttons
            )
            logger.info(f"User {user_id} opened resolution order selection")
        elif data == "set_mode":
            buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Episode First", callback_data='mode_episode'),
                    InlineKeyboardButton("Resolution First", callback_data='mode_resolution')
                ]
            ])
            await query.message.edit_text(
                "📋 Choose sequencing mode:\n"
                "- Episode First: Sends all resolutions for each episode.\n"
                "- Resolution First: Sends all episodes for each resolution.",
                reply_markup=buttons
            )
            logger.info(f"User {user_id} opened sequence mode selection")
        elif data == "show_settings":
            resolution_order = user_sequences[user_id]['resolution_order']
            sorted_resolutions = sorted(resolution_order.items(), key=lambda x: x[1])
            resolution_text = ", ".join(res[0] for res in sorted_resolutions)
            sequence_mode = user_sequences[user_id]['sequence_mode'].capitalize()
            await query.message.edit_text(
                f"⚙️ **Current Settings**\n"
                f"**Sequence Mode**: {sequence_mode} First\n"
                f"**Resolution Order**: {resolution_text}"
            )
            logger.info(f"User {user_id} viewed settings via callback")
        elif data.startswith("res_"):
            resolution = data.split('_')[1]
            new_order = default_resolution_order.copy()
            if resolution == 'default':
                user_sequences[user_id]['resolution_order'] = default_resolution_order.copy()
                await query.message.edit_text("✅ Resolution order reset to default (360p, 480p, 720p, 1080p, 4k).")
            else:
                new_order[resolution] = 0
                other_resolutions = [r for r in default_resolution_order.keys() if r != resolution]
                for i, res in enumerate(other_resolutions, 1):
                    new_order[res] = i
                user_sequences[user_id]['resolution_order'] = new_order
                await query.message.edit_text(f"✅ Resolution order set with {resolution} first.")
            logger.info(f"User {user_id} set resolution order: {resolution}")
        elif data.startswith("mode_"):
            mode = data.split('_')[1]
            user_sequences[user_id]['sequence_mode'] = mode
            await query.message.edit_text(f"✅ Sequence mode set to {mode.capitalize()} First.")
            logger.info(f"User {user_id} set sequence mode to {mode}")
        else:
            await query.message.edit_text("❌ Unknown callback data.")
            logger.warning(f"Unknown callback data: {data} from user {user_id}")
    except Exception as e:
        logger.error(f"Error in callback handler for user {user_id}: {e}")
        await query.message.edit_text("❌ An error occurred. Please try again.")

app.run()