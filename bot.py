#!/usr/bin/env python3
import os
import logging
import re
import time
import threading
import urllib.parse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration - YOU NEED TO UPDATE THESE
BOT_TOKEN = '8275623624:AAFuqP6t4EVT04J6rG1vPb66BfZgzfPLV1Q8'
CHANNEL_ID = '-1001599112424'
ADMIN_ID = '5470961827'
AMAZON_AFFILIATE_TAG = 'gadgetville99f-21'
EARNKARO_ID = 'your_earnkaro_id'

def convert_amazon_link(url):
    """Convert Amazon link to affiliate link"""
    try:
        asin_patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/gp/product/([A-Z0-9]{10})',
            r'/product/([A-Z0-9]{10})'
        ]
        
        for pattern in asin_patterns:
            match = re.search(pattern, url)
            if match:
                asin = match.group(1)
                return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
        
        separator = '&' if '?' in url else '?'
        return f"{url}{separator}tag={AMAZON_AFFILIATE_TAG}"
    except Exception as e:
        logger.error(f"Amazon conversion error: {e}")
        return url

def convert_flipkart_to_earnkaro(url):
    """Convert Flipkart link to EarnKaro affiliate link"""
    try:
        clean_url = url.split('?')
        encoded_url = urllib.parse.quote(clean_url, safe=':/?#[]@!$&\'()*+,;=')
        return f"https://earnkaro.com/ref/{EARNKARO_ID}/?url={encoded_url}"
    except Exception as e:
        logger.error(f"Flipkart conversion error: {e}")
        return url

def detect_and_convert_links(text):
    """Detect and convert affiliate links"""
    amazon_pattern = r'https?://(?:www\.)?amazon\.(?:in|com)/[^\s]+'
    flipkart_pattern = r'https?://(?:www\.)?flipkart\.com/[^\s]+'
    
    converted_text = text
    conversions = []
    
    # Convert Amazon links
    amazon_urls = re.findall(amazon_pattern, text)
    for url in amazon_urls:
        converted_url = convert_amazon_link(url)
        converted_text = converted_text.replace(url, converted_url)
        conversions.append("🛒 Amazon → Your Affiliate")
    
    # Convert Flipkart links
    flipkart_urls = re.findall(flipkart_pattern, text)
    for url in flipkart_urls:
        converted_url = convert_flipkart_to_earnkaro(url)
        converted_text = converted_text.replace(url, converted_url)
        conversions.append("🛍️ Flipkart → EarnKaro")
    
    return converted_text, conversions

def keep_codespace_active():
    """Keep Codespace active within free limits"""
    logger.info("🔄 Codespace keep-alive started")
    
    while True:
        try:
            # Light CPU activity to prevent sleep
            current_time = time.time()
            while time.time() - current_time < 1:  # 1 second of work
                _ = sum(range(10000))
            
            logger.info(f"✅ Keep-alive ping: {time.strftime('%H:%M:%S')}")
            
            # Run every 10 minutes (conservative for free tier)
            time.sleep(600)
            
        except Exception as e:
            logger.error(f"Keep-alive error: {e}")
            time.sleep(300)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
🤖 **FREE 24/7 Affiliate Bot** 
*Powered by GitHub Codespaces*

✅ **Features:**
• Amazon → Your Affiliate Links
• Flipkart → EarnKaro Links  
• Auto-post to your channel
• Running in the cloud!

**Commands:**
/start - Show this message
/status - Check bot status

**Usage:** Just send me any Amazon or Flipkart links!
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Status command - admin only"""
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("❌ Admin access required!")
        return
    
    status_text = f"""
🤖 **Bot Status**

✅ **Online:** GitHub Codespaces
🌐 **Channel:** {CHANNEL_ID}
⚡ **Environment:** Cloud (Ubuntu)
🔄 **Keep-alive:** Active
📊 **Free tier:** 120 hours/month

**Ready to convert affiliate links!**
    """
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages with affiliate links"""
    message_text = update.message.text
    
    if 'amazon.' in message_text or 'flipkart.' in message_text:
        converted_text, conversions = detect_and_convert_links(message_text)
        
        if conversions:
            try:
                # Post to channel
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=f"🔥 **Deal Alert!**\n\n{converted_text}\n\n💰 *Grab this deal now!*",
                    parse_mode='Markdown'
                )
                
                # Confirm to user
                await update.message.reply_text(
                    f"✅ **SUCCESS!**\n\n{chr(10).join(conversions)}\n\n📺 Posted to {CHANNEL_ID}",
                    parse_mode='Markdown'
                )
                
                logger.info(f"Links converted and posted: {conversions}")
                
            except Exception as e:
                error_msg = f"❌ **Error posting to channel:**\n{str(e)}"
                await update.message.reply_text(error_msg, parse_mode='Markdown')
                logger.error(f"Channel posting error: {e}")
        else:
            await update.message.reply_text("❌ No valid affiliate links found in your message!")
    else:
        await update.message.reply_text(
            "💡 **Send me product links to convert!**\n\n"
            "Supported: Amazon.in, Amazon.com, Flipkart.com"
        )

def main():
    """Main function"""
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("❌ Please update BOT_TOKEN in the code!")
        return
    
    # Start keep-alive thread
    keep_alive_thread = threading.Thread(target=keep_codespace_active, daemon=True)
    keep_alive_thread.start()
    
    # Create bot application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    logger.info("🚀 Telegram Affiliate Bot started on GitHub Codespaces!")
    logger.info(f"📺 Target Channel: {CHANNEL_ID}")
    logger.info(f"👨‍💼 Admin ID: {ADMIN_ID}")
    
    # Run the bot
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=2.0,
        timeout=10
    )

if __name__ == '__main__':
    main()
