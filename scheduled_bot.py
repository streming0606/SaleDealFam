#!/usr/bin/env python3
import logging
import re
import os
import json
import asyncio
from datetime import datetime
import pytz
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

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
SESSION_TYPE = os.environ.get('SESSION_TYPE', 'morning')

# Session configuration for link counts
SESSION_CONFIG = {
    'morning': {'links': 3, 'time': '10:12-10:20 AM'},
    'afternoon': {'links': 3, 'time': '1:12-1:20 PM'},
    'evening': {'links': 2, 'time': '6:12-6:20 PM'},
    'night': {'links': 2, 'time': '9:12-9:20 PM'}
}

class ScheduledAffiliateBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        
    def load_amazon_links(self):
        """Load Amazon links from file"""
        try:
            os.makedirs('data', exist_ok=True)
            if os.path.exists('data/amazon_links.json'):
                with open('data/amazon_links.json', 'r') as f:
                    data = json.load(f)
                    return data.get('links', [])
        except Exception as e:
            logger.error(f"Error loading links: {e}")
        return []
    
    def save_amazon_links(self, links):
        """Save Amazon links to file"""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/amazon_links.json', 'w') as f:
                json.dump({'links': links}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving links: {e}")
    
    def load_progress(self):
        """Load current progress"""
        try:
            if os.path.exists('data/progress.json'):
                with open('data/progress.json', 'r') as f:
                    data = json.load(f)
                    return data.get('current_index', 0)
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
        return 0
    
    def save_progress(self):
        """Save current progress"""
        try:
            os.makedirs('data', exist_ok=True)
            cycle_number = (self.current_index // len(self.links)) + 1 if self.links else 1
            position_in_cycle = (self.current_index % len(self.links)) + 1 if self.links else 1
            
            progress_data = {
                'current_index': self.current_index,
                'cycle_number': cycle_number,
                'position_in_cycle': position_in_cycle,
                'total_links': len(self.links),
                'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
            }
            
            with open('data/progress.json', 'w') as f:
                json.dump(progress_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving progress: {e}")
    
    def convert_amazon_link(self, url):
        """Convert any Amazon link to include affiliate tag"""
        try:
            # Extract ASIN from various Amazon URL formats
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
            if asin_match:
                asin = asin_match.group(1)
                return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
            
            # Add affiliate tag to existing URL
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}tag={AMAZON_AFFILIATE_TAG}"
        except Exception as e:
            logger.error(f"Error converting link: {e}")
            return url
    
    def get_next_links(self, count):
        """Get next batch of links for scheduling"""
        if not self.links:
            logger.warning("No links available for scheduling")
            return []
        
        selected_links = []
        for i in range(count):
            if self.current_index >= len(self.links):
                self.current_index = 0  # Reset to beginning
            
            selected_links.append(self.links[self.current_index])
            self.current_index += 1
        
        self.save_progress()
        return selected_links
    
    async def send_scheduled_links(self, session_type):
        """Send scheduled links based on session type"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        link_count = config['links']
        time_slot = config['time']
        
        logger.info(f"🕐 Starting {session_type} session: {time_slot} IST")
        logger.info(f"📊 Will send {link_count} links to channel")
        
        # Get links for this session
        links_to_send = self.get_next_links(link_count)
        
        if not links_to_send:
            logger.error("❌ No links available to send")
            return
        
        sent_count = 0
        failed_links = []
        
        for i, original_link in enumerate(links_to_send, 1):
            try:
                # Convert link to affiliate link
                converted_link = self.convert_amazon_link(original_link)
                
                # Create attractive message for channel
                channel_message = f"""🔥 DEAL FAM ALERT! 🔥

🛒 Amazon Link: {converted_link}
👍Deal Fam Rating: ⭐⭐⭐⭐⭐
💰 Grab this amazing deal now!
⏰ Limited Time: 6 hours left!

#DealFam #AmazonDeals #FlipkartOffers #ShoppingDeals #IndianDeals #SaveMoney #DailyDeals #iPhoneDeals #AmazonSale"""
                
                # Send to channel
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=channel_message,
                    parse_mode='Markdown'
                )
                
                # Log success
                ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                logger.info(f"✅ {session_type.upper()}: Sent link {i}/{link_count} at {ist_time} IST")
                logger.info(f"🔗 Original: {original_link}")
                logger.info(f"🔗 Converted: {converted_link}")
                
                sent_count += 1
                
                # Wait between messages (3-5 seconds)
                if i < len(links_to_send):
                    await asyncio.sleep(4)
                    
            except TelegramError as e:
                logger.error(f"❌ Telegram error for link {i}: {e}")
                failed_links.append(original_link)
            except Exception as e:
                logger.error(f"❌ Unexpected error for link {i}: {e}")
                failed_links.append(original_link)
        
        # Retry failed links once
        if failed_links:
            logger.info(f"🔄 Retrying {len(failed_links)} failed links...")
            await asyncio.sleep(10)
            
            for failed_link in failed_links:
                try:
                    converted_link = self.convert_amazon_link(failed_link)
                    
                    channel_message = f"""🔥 DEAL FAM ALERT! 🔥

🛒 Amazon Link: {converted_link}
👍Deal Fam Rating: ⭐⭐⭐⭐⭐
💰 Grab this amazing deal now!
⏰ Limited Time: 6 hours left!

#DealFam #AmazonDeals #FlipkartOffers #ShoppingDeals #IndianDeals #SaveMoney #DailyDeals"""
                    
                    await self.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=channel_message,
                        parse_mode='Markdown'
                    )
                    
                    logger.info(f"✅ {session_type.upper()}: Retry successful")
                    sent_count += 1
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    logger.error(f"❌ {session_type.upper()}: Retry failed: {e}")
        
        # Final summary
        total_links = len(self.links) if self.links else 0
        cycle_info = f"Cycle {(self.current_index // total_links) + 1}" if total_links > 0 else "No cycle"
        
        logger.info(f"📊 {session_type.upper()} SESSION COMPLETE:")
        logger.info(f"   ✅ Sent: {sent_count}/{link_count} links")
        logger.info(f"   📍 Progress: Link {self.current_index}/{total_links}")
        logger.info(f"   🔄 {cycle_info}")
        
        return sent_count

# Manual message handling (for interactive use)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = f"""🤖 **Scheduled Affiliate Bot Active!**

✅ Running on GitHub Actions
🕐 **Auto Schedule:** 
• 10:12 AM IST - 3 links
• 1:12 PM IST - 3 links  
• 6:12 PM IST - 2 links
• 9:12 PM IST - 2 links

⏱️ **Current Session:** {SESSION_TYPE.upper()}
💡 Send Amazon links for instant conversion!

**Daily Total:** 10 links automatically posted"""
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    text = update.message.text
    
    if not text:
        return
    
    if 'amazon.' in text.lower():
        logger.info(f"Processing manual Amazon link: {text}")
        
        bot_instance = ScheduledAffiliateBot()
        converted_link = bot_instance.convert_amazon_link(text)
        
        # Create message for channel
        channel_message = f"""🔥 DEAL FAM ALERT! 🔥

🛒 Amazon Link: {converted_link}
👍Deal Fam Rating: ⭐⭐⭐⭐⭐
💰 Grab this amazing deal now!
⏰ Limited Time: 6 hours left!

#DealFam #ManualPost #AmazonDeals #ShoppingDeals"""
        
        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=channel_message,
                parse_mode='Markdown'
            )
            
            await update.message.reply_text(
                f"✅ **Manual link posted!**\n\n🔗 Converted: `{converted_link}`",
                parse_mode='Markdown'
            )
            
            logger.info("Successfully posted manual link to channel")
            
        except Exception as e:
            error_msg = f"❌ Error posting to channel: {str(e)}"
            await update.message.reply_text(error_msg)
            logger.error(f"Error: {e}")
    else:
        await update.message.reply_text(
            f"📎 **Current session: {SESSION_TYPE.upper()}**\n\n"
            "Send me an Amazon product link to convert!\n\n"
            "Example: https://www.amazon.in/dp/B08N5WRWNW"
        )

async def main():
    """Main function for scheduled execution"""
    logger.info("🚀 Starting Scheduled Telegram Affiliate Bot...")
    logger.info(f"📅 Session Type: {SESSION_TYPE.upper()}")
    
    # Verify required environment variables
    if not all([BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG]):
        logger.error("❌ Missing required environment variables")
        exit(1)
    
    # Create bot instance
    bot_instance = ScheduledAffiliateBot()
    
    # Log current status
    logger.info(f"📊 Total links loaded: {len(bot_instance.links)}")
    logger.info(f"📍 Current index: {bot_instance.current_index}")
    logger.info(f"🎯 Target channel: {CHANNEL_ID}")
    
    # Send scheduled links
    try:
        sent_count = await bot_instance.send_scheduled_links(SESSION_TYPE)
        logger.info(f"🎉 Scheduled session completed successfully! Sent {sent_count} links")
        
    except Exception as e:
        logger.error(f"❌ Error in scheduled session: {e}")
        exit(1)

if __name__ == '__main__':
    # Check if this is a scheduled run or interactive run
    if SESSION_TYPE and SESSION_TYPE in SESSION_CONFIG:
        # Scheduled execution
        asyncio.run(main())
    else:
        # Interactive mode (fallback)
        logger.info("🤖 Starting interactive mode...")
        
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        try:
            application.run_polling(drop_pending_updates=True)
        except Exception as e:
            logger.error(f"Bot error: {e}")
