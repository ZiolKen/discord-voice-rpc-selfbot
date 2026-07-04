# Discord Voice & RPC Selfbot

A selfbot designed to keep your Discord account active in a voice channel 24/7 while displaying a highly customizable Rich Presence (RPC). The bot automatically rejoins if kicked or moved and can be controlled via commands sent from your account.

> **Warning**: Self-bots are against Discord's Terms of Service. Use this software at your own risk. Your account may be subject to termination.

## Features

- **24/7 Voice Camping**: Stays connected to a specified voice channel indefinitely.
- **Auto Rejoin**: Automatically rejoins the voice channel if disconnected, kicked, or moved.
- **Custom Rich Presence (RPC)**:
    - Set custom status, details, and state.
    - Use large and small images with hover text (from developer assets or external URLs).
    - Display elapsed time or a countdown to a specific timestamp.
    - Add up to two clickable buttons.
- **Runtime Commands**: Control the bot's behavior directly from any chat with your user account.
- **Health Check Server**: Includes a simple HTTP server, making it easy to deploy on services like Render that require a web service to be running.

## Configuration

All configuration is handled through a `.env` file.

1.  Rename `.env.example` to `.env`.
2.  Fill in the required values and customize the RPC to your liking.

```env
# ═══════════════════════════════════════════════════
#  Discord Voice Camper + Custom RPC — .env config
# ═══════════════════════════════════════════════════

# ── Required ────────────────────────────────────────
# Your Discord user token.
TOKEN=your_discord_token_here

# The ID of the voice channel you want to stay in.
VOICE_CHANNEL_ID=123456789012345678

# The ID of the server (guild) where the voice channel is.
GUILD_ID=123456789012345678

# ── Status ──────────────────────────────────────────
# Your online status: online | idle | dnd | invisible
STATUS=idle

# ── RPC — Simple ────────────────────────────────────
# RPC_TYPE: 0=Playing, 2=Listening to, 3=Watching, 5=Competing in
RPC_TYPE=3
RPC_NAME=something cool
RPC_DETAILS=optional details line
RPC_STATE=optional state line

# ── RPC — Images ──────────────────────────────────────
# APPLICATION_ID: Required if using asset keys for images. Get it from your app at https://discord.com/developers/applications
APPLICATION_ID=

# RPC_LARGE_IMAGE / RPC_SMALL_IMAGE:
# Can be an asset key from your Discord app (requires APPLICATION_ID) or a direct URL starting with https://
RPC_LARGE_IMAGE=https://i.imgur.com/example.png
RPC_LARGE_TEXT=hover text for large image
RPC_SMALL_IMAGE=https://i.imgur.com/example2.png
RPC_SMALL_TEXT=hover text for small image

# ── RPC — Timestamps ──────────────────────────────────
# RPC_SHOW_ELAPSED=YES: Shows "xx:xx elapsed" from script start time.
RPC_SHOW_ELAPSED=YES
# RPC_END_TIMESTAMP: A Unix timestamp for a countdown. Leave blank if not used.
RPC_END_TIMESTAMP=

# ── RPC — Buttons (max: 2) ────────────────────────
# URL must start with https://
RPC_BUTTON1_LABEL=Visit Website
RPC_BUTTON1_URL=https://example.com
RPC_BUTTON2_LABEL=
RPC_BUTTON2_URL=

# ── Bot ─────────────────────────────────────────────
# The prefix for commands.
PREFIX=.

# ── Render (optional) ────────────────────────────────
# Port for the health check server.
PORT=10000
```

## Installation & Usage

You need Python 3 installed.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ziolken/discord-voice-rpc-selfbot.git
    cd discord-voice-rpc-selfbot
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure:**
    Create a `.env` file by copying `.env.example` and fill in your details as described in the [Configuration](#configuration) section.

4.  **Run the bot:**
    ```bash
    python main.py
    ```

## Commands

You can control the bot by sending messages from your own account in any channel or DM. Replace `.` with your custom prefix if you've changed it.

| Command                               | Description                                                                                              |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `.ping`                               | Checks the bot's uptime, voice connection status, and running state.                                     |
| `.voice [channel_id]`                 | Joins the specified voice channel. If no `channel_id` is provided, it joins the default one from `.env`. |
| `.rpc`                                | Refreshes and pushes your RPC status to Discord.                                                         |
| `.status <online\|idle\|dnd\|invisible>` | Changes your online status.                                                                              |
| `.stop`                               | Pauses the bot. Disables auto-rejoin for voice and presence keepalive.                                   |
| `.continue`                           | Resumes a stopped bot, rejoining voice and refreshing presence.                                          |
| `.restart`                            | Restarts the entire script.                                                                              |
| `.exit`                               | Gracefully stops the bot and exits the script.                                                           |

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Credits

Created and maintained by **[ZiolKen](https://github.com/ZiolKen)**.

## Support

If this project helps you:

[![BuyMeACoffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/_zkn) [![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/zkn0461) [![Patreon](https://img.shields.io/badge/Patreon-F96854?style=for-the-badge&logo=patreon&logoColor=white)](https://patreon.com/ZiolKen) 

<div>
  <img style="100%" src="https://capsule-render.vercel.app/api?type=waving&height=100&section=footer&reversal=false&fontSize=70&fontColor=FFFFFF&fontAlign=50&fontAlignY=50&stroke=-&descSize=20&descAlign=50&descAlignY=50&theme=cobalt"  />
</div>
