from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
import re
from collections import defaultdict
from pymongo import MongoClient
from config import API_HASH, API_ID, BOT_TOKEN, MONGO_URI, START_PIC, START_MSG, HELP_TXT, OWNER_ID

mongo_client = MongoClient(MONGO_URI)
db = mongo_client["sequence_bot"]
users_collection = db["users_sequence"]

app = Client("sequence_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_sequences = {} 

# Patterns for extracting episode numbers
patterns = [
    re.compile(r'S(\d+)(?:E|EP)(\d+)', re.IGNORECASE),
    re.compile(r'S(\d+)\s*(?:E|EP|-\s*EP)(\d+)', re.IGNORECASE),
    re.compile(r'(?:[([<{]?\s*(?:E|EP)\s*(\d+)\s*[)\]>}]?)', re.IGNORECASE),
    re.compile(r'(?:\s*-\s*(\d+)\s*)'),
    re.compile(r'S(\d+)[^\d]*(\d+)', re.IGNORECASE),
    re.compile(r'(\d+)')
]

def extract_episode_number(filename):
    for pattern in patterns:
        match = pattern.search(filename)
        if match:
            return int(match.groups()[-1])
    return float('inf')  

@app.on_message(filters.command("start"))
def start_command(client, message):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Help", callback_data='help'),
            InlineKeyboardButton("Close", callback_data='close')
        ],
        [
            InlineKeyboardButton("OWNER", url='https://t.me/Its_Sahil_Ansari')
        ]
    ])
    
    client.send_photo(
        chat_id=message.chat.id,
        photo=START_PIC,
        caption=START_MSG,
        reply_markup=buttons,
    )

@app.on_message(filters.command("startsequence"))
def start_sequence(client, message):
    user_id = message.from_user.id
    if user_id not in user_sequences: 
        user_sequences[user_id] = []
        message.reply_text("✅ Sequence mode started! Send your files now.")

@app.on_message(filters.command("endsequence"))
def end_sequence(client, message):
    user_id = message.from_user.id
    if user_id not in user_sequences or not user_sequences[user_id]: 
        message.reply_text("❌ No files in sequence!")
        return
    
    sorted_files = sorted(user_sequences[user_id], key=lambda x: extract_episode_number(x["filename"]))
    
    for file in sorted_files:
        client.copy_message(message.chat.id, from_chat_id=file["chat_id"], message_id=file["msg_id"]) 

    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"files_sequenced": len(user_sequences[user_id])}, "$set": {"username": message.from_user.first_name}},
        upsert=True
    )

    del user_sequences[user_id] 
    message.reply_text("✅ All files have been sequenced!")

@app.on_message(filters.document | filters.video | filters.audio)
def store_file(client, message):
    user_id = message.from_user.id
    if user_id in user_sequences: 
        file_name = (
            message.document.file_name if message.document else
            message.video.file_name if message.video else
            message.audio.file_name if message.audio else
            "Unknown"
        )
        user_sequences[user_id].append({"filename": file_name, "msg_id": message.id, "chat_id": message.chat.id})
        message.reply_text("📂 Your file has been added to the sequence!")
    else:
        message.reply_text("❌ You need to start sequence mode first using /startsequence.")

@app.on_message(filters.command("leaderboard"))
def leaderboard(client, message):
    top_users = users_collection.find().sort("files_sequenced", -1).limit(10)
    leaderboard_text = "**🏆 Leaderboard 🏆**\n\n"

    for index, user in enumerate(top_users, start=1):
        leaderboard_text += f"**{index}. {user['username']}** - {user['files_sequenced']} files\n"

    message.reply_text(leaderboard_text if leaderboard_text else "No data available!")

# /broadcast Command
@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
def broadcast(client, message):
    if len(message.command) < 2:
        message.reply_text("**Usage:** `/broadcast Your message here`")
        return

    broadcast_text = message.text.split(" ", 1)[1]
    users = users_collection.find({}, {"user_id": 1})
    
    count = 0
    for user in users:
        try:
            client.send_message(user["user_id"], broadcast_text)
            count += 1
        except:
            pass  

    message.reply_text(f"✅ Broadcast sent to {count} users.")

# /users Command 
@app.on_message(filters.command("users") & filters.user(OWNER_ID))
def get_users(client, message):
    user_count = users_collection.count_documents({})
    message.reply_text(f"📊 **Total Users:** {user_count}")

@app.on_callback_query()
async def cb_handler(client: app, query: CallbackQuery):
    data = query.data
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

app.run()
