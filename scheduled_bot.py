#!/usr/bin/env python3
import logging
import re
import os
import signal
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get configuration from environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
AMAZON_AFFILIATE_TAG = os.environ.get('AMAZON_TAG')

def convert_amazon_link(url):
    """Convert any Amazon link to include affiliate tag"""
    try:
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        if asin_match:
            asin = asin_match.group(1)
            return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
        
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}tag={AMAZON_AFFILIATE_TAG}"
    except Exception as e:
        logger.error(f"Error converting link: {e}")
        return url

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = """🤖 **Affiliate Bot Active - 15 Min Session!**
    
✅ Running on GitHub Actions
🕐 **Schedule:** 10AM, 1PM, 6PM, 9PM IST
⏱️ **Duration:** 15 minutes per session
💡 Send Amazon links for instant conversion!

**Daily Schedule:**
• 10:00-10:15 AM IST
• 1:00-1:15 PM IST  
• 6:00-6:15 PM IST
• 9:00-9:15 PM IST"""
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    text = update.message.text
    
    if not text:
        return
    
    if 'amazon.' in text.lower():
        logger.info(f"Processing Amazon link: {text}")
        
        converted_link = convert_amazon_link(text)
        
        # Create attractive message for channel
        channel_message = f"""🔥 **Deal Alert!** 🔥

{converted_link}

💰 Grab this amazing deal now!
⏰ Limited time offer!

#AmazonDeals #Affiliate"""
        
        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_message,
                parse_mode='Markdown'
            )
            
            await update.message.reply_text(
                f"✅ **Link converted and posted!**\n\n🔗 Converted: `{converted_link}`",
                parse_mode='Markdown'
            )
            
            logger.info("Successfully posted to channel")
            
        except Exception as e:
            error_msg = f"❌ Error posting to channel: {str(e)}"
            await update.message.reply_text(error_msg)
            logger.error(f"Error: {e}")
    else:
        await update.message.reply_text(
            "📎 Please send me an Amazon product link to convert!\n\n"
            "Example: https://www.amazon.in/dp/B08N5WRWNW"
        )

def timeout_handler(signum, frame):
    """Handle timeout after 15 minutes"""
    logger.info("⏰ 15-minute session completed - stopping bot gracefully")
    exit(0)

def main():
    """Main function to run the bot"""
    logger.info("🚀 Starting 15-minute Telegram Affiliate Bot session...")
    
    # Verify required environment variables
    if not all([BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG]):
        logger.error("Missing required environment variables")
        exit(1)
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Set up 15-minute timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(900)  # 900 seconds = 15 minutes
    
    logger.info("🎯 Bot will run for exactly 15 minutes...")
    logger.info(f"📢 Will post to channel: {CHANNEL_ID}")
    
    # Start the bot
    try:
        application.run_polling(drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        logger.info("🛑 15-minute session ended")

if __name__ == '__main__':
    main()
