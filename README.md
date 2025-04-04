# Telegram Media Download Bot

Commands:  

• /pick - Interactive menu to fetch posts  
• /fetch [x|instagram] <username> - Fetch posts by platform and username  
• /nogi_news - Fetch Nogizaka46 news from official web  
• /saku_news - Fetch Sakurazaka46 news from official web  
• /hinata_news - Fetch Hinatazaka46 news from official web  
• /fetch_nagi - Fetch all posts for Inoue Nagi  
• /fetch_nagi_x - Fetch only X/Twitter posts from Inoue Nagi  
• /fetch_nagi_ig - Fetch only Instagram posts from Inoue Nagi  
• /bili <url> - Download and send Bilibili video  
• /youtube <url> - Download and send YouTube video  
• /history - Browse previously fetched posts' media  
• /echo <message> - Echo back your message  
• /help - Show this help message  

## Setup & Installation
1. Install Python 3.9+ and Git on your machine.  
2. Clone this repository or download the project’s ZIP.  
3. In a terminal, navigate to the project folder and create a virtual environment (optional but recommended):  
4. Install dependencies:  
   ```
   pip install -r requirements.txt
   ```
5. Copy “.env.example” to “.env” or create a “.env” file. Add environment variables (e.g. BOT_TOKEN, CHAT_ID, etc.).

## Deployment
1. Run the bot with:
   ```
   python bot.py
   ```
2. Keep the process running in the background.

## Usage
Use Telegram commands in a chat with the bot. Examples:
• /pick - Interactive menu  
• /fetch x <username> - Fetch from X/Twitter  
• /fetch instagram <username> - Fetch from Instagram  
• /help - List available commands  

### Notes
- You can set the auto fetcher for specific accounts
- Now the bot depends on the `sent_posts.json` to view the history of the posts sent to the user, there might be some bugs for retrieving the history.


