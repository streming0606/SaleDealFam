#!/usr/bin/env python3
import logging
import re
import os
import json
import asyncio
from datetime import datetime
import pytz
import requests
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
WEBSITE_REPO = "streming0606/DealFamSheduler"  # Your website repository
GITHUB_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')  # Add this secret

# Session configuration for link counts
SESSION_CONFIG = {
    'morning': {'links': 3, 'time': '10:12-10:20 AM'},
    'afternoon': {'links': 3, 'time': '1:12-1:20 PM'},
    'evening': {'links': 2, 'time': '6:12-6:20 PM'},
    'night': {'links': 2, 'time': '9:12-9:20 PM'}
}

class EnhancedAffiliateBot:
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
    
    def extract_product_info(self, amazon_url):
        """Extract basic product information from Amazon URL"""
        try:
            # Extract ASIN
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', amazon_url)
            asin = asin_match.group(1) if asin_match else None
            
            # Basic product info (you can enhance this with actual scraping)
            product_info = {
                'asin': asin,
                'title': f"Amazon Product {asin}" if asin else "Amazon Deal",
                'image': f"https://images-na.ssl-images-amazon.com/images/I/{asin}.jpg" if asin else "",
                'price': "₹Special Price",
                'rating': "⭐⭐⭐⭐⭐",
                'category': self.categorize_product(amazon_url)
            }
            
            return product_info
            
        except Exception as e:
            logger.error(f"Error extracting product info: {e}")
            return {
                'asin': None,
                'title': "Amazon Deal",
                'image': "",
                'price': "₹Special Price", 
                'rating': "⭐⭐⭐⭐⭐",
                'category': "electronics"
            }
    
    def categorize_product(self, url):
        """Simple categorization based on URL keywords"""
        url_lower = url.lower()
        
        if any(keyword in url_lower for keyword in ['phone', 'laptop', 'electronics', 'mobile', 'tablet']):
            return 'electronics'
        elif any(keyword in url_lower for keyword in ['fashion', 'clothing', 'shoes', 'watch']):
            return 'fashion'
        elif any(keyword in url_lower for keyword in ['home', 'kitchen', 'furniture']):
            return 'home'
        elif any(keyword in url_lower for keyword in ['health', 'beauty', 'care']):
            return 'health'
        elif any(keyword in url_lower for keyword in ['sports', 'fitness', 'gym']):
            return 'sports'
        elif any(keyword in url_lower for keyword in ['car', 'bike', 'vehicle']):
            return 'vehicle'
        elif any(keyword in url_lower for keyword in ['book', 'kindle']):
            return 'books'
        else:
            return 'electronics'  # Default category
    
    async def update_website_products(self, new_products):
        """Update website products.json file via GitHub API"""
        try:
            if not GITHUB_TOKEN:
                logger.warning("No GitHub token provided - skipping website update")
                return False
            
            # Load existing website products
            website_products = await self.get_website_products()
            
            # Add new products to the beginning of the list
            for product in reversed(new_products):
                website_products.insert(0, product)
            
            # Keep only latest 100 products to avoid file size issues
            website_products = website_products[:100]
            
            # Update the JSON structure
            updated_data = {
                "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                "total_products": len(website_products),
                "products": website_products
            }
            
            # Update file on GitHub
            success = await self.commit_to_github('data/products.json', json.dumps(updated_data, indent=2))
            
            if success:
                logger.info(f"✅ Website updated with {len(new_products)} new products")
                return True
            else:
                logger.error("❌ Failed to update website")
                return False
                
        except Exception as e:
            logger.error(f"Error updating website: {e}")
            return False
    
    async def get_website_products(self):
        """Get existing products from website repository"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/products.json"
            headers = {
                'Authorization': f'token {GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                file_content = response.json()
                import base64
                content = base64.b64decode(file_content['content']).decode('utf-8')
                data = json.loads(content)
                return data.get('products', [])
            else:
                logger.info("No existing products file found - creating new one")
                return []
                
        except Exception as e:
            logger.error(f"Error getting website products: {e}")
            return []
    
    async def commit_to_github(self, file_path, content):
        """Commit file to GitHub repository"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/{file_path}"
            headers = {
                'Authorization': f'token {GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get existing file SHA (if exists)
            response = requests.get(url, headers=headers)
            sha = None
            if response.status_code == 200:
                sha = response.json()['sha']
            
            # Prepare commit data
            import base64
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            commit_data = {
                'message': f'Auto-update: {SESSION_TYPE} session products',
                'content': encoded_content,
                'branch': 'main'
            }
            
            if sha:
                commit_data['sha'] = sha
            
            # Commit file
            response = requests.put(url, headers=headers, json=commit_data)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Successfully committed {file_path}")
                return True
            else:
                logger.error(f"❌ GitHub commit failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error committing to GitHub: {e}")
            return False
    
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
        """Send scheduled links to both Telegram and Website"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        link_count = config['links']
        time_slot = config['time']
        
        logger.info(f"🕐 Starting {session_type} session: {time_slot} IST")
        logger.info(f"📊 Will send {link_count} links to Telegram + Website")
        
        # Get links for this session
        links_to_send = self.get_next_links(link_count)
        
        if not links_to_send:
            logger.error("❌ No links available to send")
            return
        
        sent_count = 0
        website_products = []
        
        for i, original_link in enumerate(links_to_send, 1):
            try:
                # Convert link to affiliate link
                converted_link = self.convert_amazon_link(original_link)
                
                # Extract product information
                product_info = self.extract_product_info(original_link)
                
                # Create Telegram message
                channel_message = f"""🔥 DEAL FAM ALERT! 🔥

🛒 Amazon Link: {converted_link}
👍Deal Fam Rating: {product_info['rating']}
💰 Grab this amazing deal now!
⏰ Limited Time: 6 hours left!

#DealFam #AmazonDeals #FlipkartOffers #ShoppingDeals #IndianDeals #SaveMoney #DailyDeals"""
                
                # Send to Telegram channel
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=channel_message,
                    parse_mode='Markdown'
                )









                
                # Prepare product data for website
               website_product = {
                    'id': f"product_{session_type}_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'title': product_info['title'],
                    'image': product_info['image'],
                    'affiliate_link': converted_link,
                    'price': product_info['price'],
                    'rating': product_info['rating'],
                    'category': product_info['category'],
                    'posted_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                    'session_type': session_type
                }
                website_products.append(website_product)

                # Log success
                ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                logger.info(f"✅ {session_type.upper()}: Sent link {i}/{link_count} at {ist_time} IST")
                logger.info(f"🔗 Original: {original_link}")
                logger.info(f"🔗 Converted: {converted_link}")
                logger.info(f"📂 Category: {product_info['category']}")
                
                sent_count += 1
                
                # Wait between messages
                if i < len(links_to_send):
                    await asyncio.sleep(4)
                    
            except Exception as e:
                logger.error(f"❌ Error processing link {i}: {e}")
        
        # Update website with all products from this session
        if website_products:
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"✅ Website updated with {len(website_products)} products")
            else:
                logger.error("❌ Website update failed")
        
        # Final summary
        total_links = len(self.links) if self.links else 0
        cycle_info = f"Cycle {(self.current_index // total_links) + 1}" if total_links > 0 else "No cycle"
        
        logger.info(f"📊 {session_type.upper()} SESSION COMPLETE:")
        logger.info(f"   ✅ Telegram: {sent_count}/{link_count} links posted")
        logger.info(f"   🌐 Website: {len(website_products)} products added")
        logger.info(f"   📍 Progress: Link {self.current_index}/{total_links}")
        logger.info(f"   🔄 {cycle_info}")
        
        return sent_count

# Main execution function
async def main():
    """Main function for scheduled execution"""
    logger.info("🚀 Starting Enhanced Telegram + Website Bot...")
    logger.info(f"📅 Session Type: {SESSION_TYPE.upper()}")
    
    # Verify required environment variables
    required_vars = [BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG]
    if not all(required_vars):
        logger.error("❌ Missing required environment variables")
        exit(1)
    
    # Create bot instance
    bot_instance = EnhancedAffiliateBot()
    
    # Log current status
    logger.info(f"📊 Total links loaded: {len(bot_instance.links)}")
    logger.info(f"📍 Current index: {bot_instance.current_index}")
    logger.info(f"🎯 Target channel: {CHANNEL_ID}")
    logger.info(f"🌐 Target website: {WEBSITE_REPO}")
    
    # Send scheduled links to both platforms
    try:
        sent_count = await bot_instance.send_scheduled_links(SESSION_TYPE)
        logger.info(f"🎉 Enhanced session completed! Telegram: {sent_count} links, Website: Updated")
        
    except Exception as e:
        logger.error(f"❌ Error in enhanced session: {e}")
        exit(1)

if __name__ == '__main__':
    # Run the enhanced bot
    asyncio.run(main())
