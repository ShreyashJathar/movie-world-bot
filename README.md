# 🎬 Telegram Movie Sender Bot

A high-performance, asynchronous Telegram Movie Sender and Auto-Filter Bot built with Python, `python-telegram-bot`, and SQLite.

## ✨ Features

- 🔍 **Smart In-Chat Search**: Users can type movie titles directly in chat or groups. Supports fuzzy/keyword tokenization (e.g. `Spider Man 1080p` matches `Spider-Man.No.Way.Home.1080p.mkv`).
- 🔗 **Deep Link File Sharing**: Generates unique shareable links (`t.me/yourbot?start=file_<code>`) for any movie.
- 📦 **Zero-Bandwidth Channel Delivery**: Copies messages directly from your private storage channel without consuming your server's bandwidth or RAM.
- ⏳ **Auto-Delete Timer**: Automatically deletes delivered movie files from user chats after a configurable timer (default: 10 minutes) with a warning notice to prevent copyright strikes.
- 🔒 **Force-Subscription (FSUB)**: Requires users to join your Telegram update channel before accessing movies, with instant 1-tap verification.
- 🎨 **IMDb / OMDb Posters & Synopses**: Automatically shows IMDb ratings, release year, plot summary, and official movie posters when users search.
- 👑 **Admin Automation**:
  - **Direct Upload**: Send or forward video/document files directly to the bot in private chat to index them and receive shareable links.
  - **Channel Auto-Indexing**: Add the bot as an Admin in your Storage Channel; any movie forwarded or posted there is automatically indexed!
  - **Broadcast**: Send announcements to all registered bot users with `/broadcast`.
  - **Stats & Metrics**: Track total indexed movies and registered users with `/stats`.
  - **File Management**: Manage and delete files with `/delete <id>`.

---

## 🚀 Quick Setup Guide

### 1. Prerequisites
- Python 3.10+ (Python 3.14+ is supported and tested)
- Telegram account

### 2. Get Your Credentials
1. **Bot Token**:
   - Open Telegram and message [@BotFather](https://t.me/BotFather).
   - Send `/newbot`, choose a name and username.
   - Copy the API Token provided.
2. **Admin Telegram ID**:
   - Message [@userinfobot](https://t.me/userinfobot) or [@MissRose_bot](https://t.me/MissRose_bot) (send `/id`).
   - Copy your numeric ID (e.g. `123456789`).

---

### 3. Configure the Bot

Open the [.env](file:///d:/telegram%20bot/.env) file and configure your settings:

```ini
# Your Telegram Bot Token from @BotFather (Required)
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# Telegram User ID(s) of Bot Admins (comma-separated)
ADMIN_IDS=123456789

# Storage Channel ID (Optional but recommended, e.g. -1001234567890)
STORAGE_CHANNEL_ID=

# Force-Subscribe Channel (Optional, e.g. @MyChannel or -1001234567890)
FSUB_CHANNEL_ID=

# Invite link for the FSUB channel (Optional, e.g. https://t.me/MyChannel)
FSUB_INVITE_LINK=

# Auto-Delete Movie Timer in Seconds (600 = 10 minutes, 0 to disable)
AUTO_DELETE_SECONDS=600

# Free OMDb API Key for IMDb posters (Optional: http://www.omdbapi.com/apikey.aspx)
OMDB_API_KEY=

# SQLite Database File
DATABASE_PATH=movies.db
```

---

### 4. Run the Bot

The virtual environment is already prepared in this directory. To start the bot:

```powershell
.\venv\Scripts\python.exe main.py
```

---

## 📁 How to Add Movies

### Method A: Direct Upload (Fastest for single files)
1. Message your bot in private chat.
2. Send or forward any video or document file.
3. The bot indexes the file, stores it in SQLite, and gives you:
   - File Name & Size
   - Database ID
   - Unique Deep Link (`https://t.me/bot?start=file_xxxxxx`)

### Method B: Storage Channel Auto-Indexing (Best for bulk libraries)
1. Create a private Telegram channel (e.g., `My Movie Storage`).
2. Add your bot as an **Administrator** with *Post Messages* permission.
3. Get the channel ID (usually starts with `-100...`) and paste it into `STORAGE_CHANNEL_ID` in `.env`.
4. Now, simply forward 10s or 100s of movie files into that channel — the bot will automatically index every single file!

---

## 🛠️ Admin Commands

| Command | Description |
| :--- | :--- |
| `/admin` | Show admin command help and instructions |
| `/stats` | View total registered users, indexed files & VIP subscribers |
| `/plans` | View configured VIP subscription plans and pricing |
| `/pending` | View pending VIP payment submissions from users |
| `/approve <id>` | Manually approve a payment request by Request ID |
| `/reject <id>` | Manually reject a payment request by Request ID |
| `/addpremium <user_id> [days]` | Grant or extend VIP access manually (default: 30 days) |
| `/removepremium <user_id>` | Revoke VIP subscription for a user |
| `/resetlimit [user_id]` | Reset daily download limit counter for a user or self |
| `/delete <id>` | Remove a movie from the database by its ID |
| `/link <id>` | Retrieve the deep link for an indexed movie ID |
| `/broadcast <message>` | Send an announcement to all bot users |

---

## 💎 VIP Subscription Plans

The bot features an automated in-chat subscription workflow with instant admin approval:

| Plan | Duration | Price | Perks |
| :--- | :--- | :--- | :--- |
| 🌟 **Weekly Pass** | 7 Days | ₹39 | Unlimited movie downloads with zero daily limits |
| 🌟 **1 Month VIP** | 30 Days | ₹89 | Unlimited movie downloads with zero daily limits |
| 🔥 **3 Months VIP** | 90 Days | ₹219 | Unlimited movie downloads with zero daily limits |
| 👑 **6 Months VIP** | 180 Days | ₹349 | Unlimited movie downloads with zero daily limits |
| ⚡ **One Year VIP** | 365 Days | ₹649 | Unlimited movie downloads with zero daily limits |

### How It Works:
1. Users open `/plan` (or click **💎 VIP Plans**).
2. Users select a plan and view the payment details (UPI ID, 1-tap UPI link, QR code).
3. Users submit their payment screenshot or 12-digit UTR in chat.
4. The bot forwards the proof to your **Private Admin Group** with **[✅ Approve]** and **[❌ Reject]** buttons.
5. Any admin in the group taps **Approve** to instantly activate the user's VIP access!

### Linking Your Private Admin Group (`https://t.me/+lgLJDd4mfZw5M2U1`):
1. Open your private group: [Private Group](https://t.me/+lgLJDd4mfZw5M2U1).
2. Add your bot into the group as an **Administrator**.
3. Send `/setadmingroup` inside the group.
4. The bot will automatically detect the group's Chat ID, link it permanently, and forward all payment proofs there!
*(Alternatively, you can paste the numeric group ID into `ADMIN_GROUP_ID=` in your `.env` file).*

---

## 👥 User Features

- **Search by Movie Name**: Users simply send `Avatar` or `Interstellar 1080p` to view search results with buttons.
- **Pagination**: Navigate search results with `◀️ Prev` and `Next ▶️` buttons.
- **VIP Subscription Plans**: Access unlimited downloads anytime via `/plan` or `/premium`.
- **Force Subscription**: If enabled, users are guided to join your channel first with a 1-tap `Verify` button.
- **Auto-Delete Timer**: Sent files are automatically removed after the configured duration (default: 10 mins).

