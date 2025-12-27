# OfTheDayBot 🤖

A Discord bot that posts daily content from your custom categories and creates fun match-up polls!

## Features

### 📅 Daily Posts
- Automatically post a random item from a category at a scheduled time
- Supports images, links, and rich descriptions
- Configurable per-server with custom timing

### 🥊 Daily Match-ups
- Automatically post daily polls between two random items from a category
- Uses Discord's native poll feature with 24-hour voting
- Rich embeds with descriptions and images
- Configurable per-server with custom timing

## Installation

1. **Clone/Download this project**

2. **Install dependencies with uv:**
   ```bash
   uv sync
   ```

3. **Configure your bot token:**
   ```bash
   cp .env.example .env
   # Edit .env and add your Discord bot token
   # Get your token from: https://discord.com/developers/applications
   ```

4. **Add your data** (see Data Format section below)

5. **Run the bot:**
   ```bash
   uv run python bot.py
   ```

## Discord Setup

1. **Create a Discord Application:**
   - Go to https://discord.com/developers/applications
   - Create a new application
   - Go to "Bot" section and create a bot
   - Copy the bot token for your `.env` file

2. **Invite the bot to your server:**
   - Go to "OAuth2" > "URL Generator"
   - Select "bot" and "applications.commands" scopes
   - Select these permissions:
     - View Channels
     - Send Messages
     - Embed Links
     - Attach Files
     - Create Public Threads (for polls)
     - Use Slash Commands
   - Use the generated URL to invite the bot

## Slash Commands

All commands require Administrator permissions.

### `/daily categories`
Lists all available categories from your data directory.

### `/daily status`
Show current daily posting configuration for this server, including configured categories, channels, times, and active polls.

### `/daily setup`
Set up automatic daily posting or match-up polls for a category.
- **post_type**: Choose between "Daily Post" or "Match-up Poll"
- **category**: The category to post from
- **channel**: The channel to post to
- **time_hour**: Hour (0-23) to post at
- **time_minute**: Minute (0-59) to post at (default: 0)

**Example (Daily Post):** `/daily setup post_type:Daily Post category:Touhou channel:#daily-touhou time_hour:9 time_minute:30`

**Example (Match-up):** `/daily setup post_type:Match-up Poll category:Touhou channel:#touhou-battles time_hour:15 time_minute:0`

### `/daily remove`
Remove daily posting configuration for a category.
- **post_type**: Choose between "Daily Post" or "Match-up Poll"
- **category**: The category to remove configuration for

**Example:** `/daily remove post_type:Daily Post category:Touhou`

### `/daily endpoll`
Manually close the active poll for a category before its 24-hour duration ends.
- **category**: Category of the poll to close

**Example:** `/daily endpoll category:Touhou`

### `/daily reroll`
Manually trigger a daily post or matchup for testing purposes. Uses the pre-configured channels from setup commands.
- **post_type**: Choose between "Daily Post" or "Match-up Poll"
- **category**: The category to select items from

**Example:** `/daily reroll post_type:Daily Post category:Touhou`

## Data Format

### Directory Structure
```
data/
├── <category_name>/
│   ├── <item_name>/
│   │   ├── info.json
│   │   └── image.png (optional)
│   └── <another_item>/
│       ├── info.json
│       └── image.jpg (optional)
└── <another_category>/
    └── ...
```

### Item Format (info.json)
```json
{
    "name": "Display name of item",
    "link": "https://optional-link-for-more-info.com",
    "description": "Description of the item that will be displayed in embeds"
}
```

### Example Structure
```
data/
├── Touhou/
│   ├── Reimu_Hakurei/
│   │   ├── info.json
│   │   └── image.png
│   ├── Marisa_Kirisame/
│   │   ├── info.json
│   │   └── image.png
│   └── Cirno/
│       ├── info.json
│       └── image.jpg
├── Pokemon/
│   ├── Pikachu/
│   │   ├── info.json
│   │   └── image.png
│   └── Charizard/
│       ├── info.json
│       └── image.gif
└── Movies/
    ├── The_Matrix/
    │   ├── info.json
    │   └── image.jpg
    └── Inception/
        ├── info.json
        └── image.png
```

### Image Support
- **Supported formats**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`
- **File naming**: Images should be named `image.ext` (e.g., `image.png`)
- **Display**: Images are automatically included in embeds
- **Recommended size**: 400x400 or smaller for best Discord display

## Bot Behavior

### Daily Posts
- The bot checks every minute if it's time to post
- Only posts once per day at the configured time
- Posts include embed with title, description, link (if available), and image (if available)
- Format: "{Category} of the Day: {Item Name}"

### Daily Match-ups
- The bot checks every minute if it's time to post a match-up
- Only posts once per day at the configured time
- Selects 2 random items from the specified category
- Creates an embed showing both contestants with descriptions
- Posts a Discord poll with 24-hour voting duration
- Uses red 🔴 and blue 🔵 emojis for poll options
- Shows image from the first contestant as thumbnail

## Configuration Storage

Bot configurations are saved in `configs.json` and persist between restarts.

## Troubleshooting

### Bot not responding to slash commands
- Make sure the bot has been invited with the correct permissions
- Check that slash commands are synced (should happen automatically on startup)
- Verify your bot token is correct in the `.env` file

### Daily posts/matchups not working
- Check your time zone - the bot uses the server's local time
- Verify the category exists and has items
- Make sure the bot has permission to post in the configured channel
- For matchups, ensure the bot has permission to create polls

### Images not appearing
- Check that the image file exists and is named correctly (`image.ext`)
- Verify the image format is supported
- Ensure the bot has "Attach Files" permission

### No categories found
- Check that your data directory structure is correct
- Ensure info.json files are valid JSON
- Make sure category folders contain item folders (not just files)

### Polls not working
- Ensure your Discord server supports polls (available in most servers)
- Verify the bot has appropriate permissions
- Check that the category has at least 2 items for match-ups

## Requirements

- Python 3.8+
- discord.py 2.3.2+
- python-dotenv
- See `requirements.txt` for full list

## License

MIT License - Feel free to modify and use as needed!
