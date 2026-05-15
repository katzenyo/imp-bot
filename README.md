# Imp Bot 10000

A feature-rich Discord bot built with [discord.py v2](https://discordpy.readthedocs.io/en/stable/), organized as a modular cog architecture. Includes Twitch stream notifications via EventSub WebSocket, Letterboxd RSS integration, a starboard, birthday tracking, a voice audio player, and more.

## Features

### Twitch Stream Notifications
Monitors Twitch channels via a persistent EventSub WebSocket connection (no polling). Sends rich embed notifications with stream title, game, thumbnail, and a direct watch link when a streamer goes live.

**Commands** (`/stream` — requires Manage Server):
| Command | Description |
|---|---|
| `/stream channel #channel` | Set the channel for stream notifications |
| `/stream add <twitch_login>` | Add a Twitch channel to watch |
| `/stream remove <twitch_login>` | Stop watching a Twitch channel |
| `/stream list` | List all watched channels |

### Letterboxd Feed
Polls linked Letterboxd profiles every 30 minutes and posts new film ratings and reviews as embeds. Only posts entries with a star rating or a written review.

**Commands** (`/letterboxd`):
| Command | Description |
|---|---|
| `/letterboxd follow <username>` | Link your Letterboxd profile |
| `/letterboxd unfollow` | Unlink your profile |
| `/letterboxd list` | Show all linked profiles in the server |
| `/letterboxd channel #channel` | Set the posting channel (admin) |

### Birthday Tracker
Stores member birthdays and sends a daily announcement at midnight UTC when it's someone's birthday.

**Commands** (`/birthday`):
| Command | Description |
|---|---|
| `/birthday set <month> <day>` | Set your birthday |
| `/birthday remove` | Remove your birthday |
| `/birthday check [member]` | Look up a birthday |
| `/birthday list` | Show all upcoming birthdays in the server |
| `/birthday channel #channel` | Set the announcement channel (admin) |

### Starboard
Pins stand-out messages to a dedicated channel when they accumulate enough ⭐ reactions. The star count updates live as reactions change.

**Commands** (`/starboard` — requires Manage Server):
| Command | Description |
|---|---|
| `/starboard channel #channel` | Set the starboard channel |
| `/starboard threshold <n>` | Set the minimum star count (default: 3) |
| `/starboard disable` | Disable the starboard |
| `/starboard status` | Show current configuration |

### Voice Audio Player (LPC)
Plays local audio files from a configured album library into a voice channel, with queue support and inline playback controls.

**Commands** (`/play`):
| Command | Description |
|---|---|
| `/play <album>` | Play an album (with autocomplete) |
| Stop / Skip buttons | Inline controls on the now-playing message |

Supports `.mp3`, `.wav`, `.ogg`, `.flac`, and `.m4a`.

### Slash Commands (`/`)
| Command | Description |
|---|---|
| `/roll` | Roll a d20 |
| `/clown` | Identifies a clown (you) |
| `/game <member>` | Show what game a member is playing |
| `/wiki random` | Fetch a random Wikipedia article with embed |
| `/bobstream` | Check if a specific streamer is live (server-specific) |

### Member Events
Sends a welcome message when a member joins and a farewell message when they leave, posted to the server's system channel.

### Movie Genre Poll
A ranked-choice poll cog for voting on movie genres. Members rank their top three choices; the bot tallies votes with a weighted point system and resolves ties by vote ranking.

---

## Setup

### Prerequisites
- Python 3.11+
- FFmpeg (for the voice audio player)
- A Twitch application ([dev.twitch.tv](https://dev.twitch.tv))

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd python-discord-bot

# Create and activate a virtual environment
python -m venv chat-bot-env
./chat-bot-env/Scripts/Activate.ps1   # PowerShell
# source chat-bot-env/bin/activate    # bash/zsh

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# Required
DISCORD_TOKEN=your_discord_bot_token
TWITCH_ACCESS_TOKEN=your_twitch_access_token
TWITCH_CLIENT_ID=your_twitch_client_id
TWITCH_CLIENT_SECRET=your_twitch_client_secret

# Optional — needed for the LPC voice player
ALBUMS_PATH=/path/to/your/music/library
FFMPEG_PATH=/path/to/ffmpeg   # defaults to 'ffmpeg' on PATH

# Optional — for future Wikipedia search features
WIKI_CLIENT_ID=your_wikimedia_client_id
WIKI_CLIENT_SECRET=your_wikimedia_client_secret
WIKI_ACCESS_TOKEN=your_wikimedia_access_token
```

### Running

```bash
python main.py
```

On first run (or after adding new slash commands), sync them to Discord using the owner-only prefix command in your server:

```
!sync
```

---

## Architecture

`main.py` constructs `ImpBot(commands.Bot)`, enables the `message_content`, `members`, and `presences` intents, and loads all cogs during `setup_hook()`. It also validates the Twitch token on startup and warns if it expires within a week.

Each feature lives in its own cog file:

| File | Cog | Purpose |
|---|---|---|
| `twitch.py` | `TwitchCog` | EventSub WebSocket, stream notifications |
| `letterboxd.py` | `LetterboxdCog` | RSS feed polling, film rating embeds |
| `birthdays.py` | `BirthdayCog` | Birthday storage, daily announcement task |
| `starboard.py` | `StarboardCog` | Star reaction threshold → pinned embed |
| `lpc.py` | `LPCPlayer` | Local audio queue, FFmpeg voice playback |
| `slash.py` | `SlashCommands` | Misc slash commands |
| `events.py` | `EventsCog` | Member join/leave messages |
| `poll.py` | `PollCog` | Ranked-choice genre voting |

**Database:** SQLite via `aiosqlite`. Each cog manages its own connection to `impbot.db` and initializes its schema with `CREATE TABLE IF NOT EXISTS`. All tables include `guild_id` as a primary/foreign key for multi-server support.

**Owner commands** (legacy prefix `!`):
- `!sync` — sync slash commands globally
- `!refresh_twitch` — refresh the Twitch API token
- `!whois <member>` — show basic member info

---

## Dependencies

| Package | Purpose |
|---|---|
| `discord.py` | Discord API wrapper |
| `aiohttp` | Async HTTP and WebSocket client |
| `aiosqlite` | Async SQLite (via `asyncio`) |
| `python-dotenv` | `.env` file loading |
| `PyNaCl` | Voice support |
