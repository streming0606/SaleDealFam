#!/usr/bin/env python3
import logging
import re
import os
import json
import asyncio
import time  # Add time import for synchronous delays
from datetime import datetime, timedelta
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
WEBSITE_REPO = "streming0606/DealFamSheduler"
GITHUB_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')
SERP_API_KEY = os.environ.get('SERP_API_KEY')

# Session configuration
SESSION_CONFIG = {
    'morning': {
        'telegram_links': 3, 
        'website_links': 2, 
        'time': '10:12-10:20 AM'
    },
    'afternoon': {
        'telegram_links': 3, 
        'website_links': 2, 
        'time': '1:12-1:20 PM'
    },
    'evening': {
        'telegram_links': 2, 
        'website_links': 1, 
        'time': '6:12-6:20 PM'
    },
    'night': {
        'telegram_links': 2, 
        'website_links': 1, 
        'time': '9:12-9:20 PM'
    }
}

class EnhancedAffiliateBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        self.serp_request_count = 0
        self.serp_start_time = datetime.now()
        
        logger.info(f"🚀 Enhanced Affiliate Bot Initialized")
        logger.info(f"📊 Loaded {len(self.links)} total links")
        logger.info(f"📍 Starting from index: {self.current_index}")
        logger.info(f"🔑 SerpApi available: {'Yes' if SERP_API_KEY else 'No'}")
        
    def load_amazon_links(self):
        """Load Amazon links from file"""
        try:
            os.makedirs('data', exist_ok=True)
            
            if os.path.exists('data/amazon_links.json'):
                with open('data/amazon_links.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    links = data.get('links', [])
                    logger.info(f"✅ Loaded {len(links)} links from amazon_links.json")
                    return links
                    
        except Exception as e:
            logger.error(f"❌ Error loading links: {e}")
        
        logger.warning("⚠️ No links loaded - returning empty list")
        return []
    
    def load_progress(self):
        """Load current progress"""
        try:
            # Try GitHub first
            github_progress = self.get_progress_from_github()
            if github_progress is not None:
                logger.info(f"📈 Loaded progress from GitHub: index {github_progress}")
                return github_progress
            
            # Try local file
            if os.path.exists('data/progress.json'):
                with open('data/progress.json', 'r') as f:
                    data = json.load(f)
                    index = data.get('current_index', 0)
                    logger.info(f"📈 Loaded progress from local file: index {index}")
                    return index
                    
        except Exception as e:
            logger.error(f"❌ Error loading progress: {e}")
        
        logger.info("📈 No progress found - starting from index 0")
        return 0
    
    def get_progress_from_github(self):
        """Get current progress from GitHub repository (FIXED - synchronous)"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if not GITHUB_TOKEN:
                    return None
                    
                url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/progress.json"
                headers = {
                    'Authorization': f'token {GITHUB_TOKEN}',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                response = requests.get(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    file_content = response.json()
                    import base64
                    content = base64.b64decode(file_content['content']).decode('utf-8')
                    data = json.loads(content)
                    return data.get('current_index', 0)
                elif response.status_code == 404:
                    logger.info("No progress file found in GitHub repository")
                    return None
                else:
                    logger.warning(f"GitHub API returned {response.status_code}: {response.text}")
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Error getting progress from GitHub: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # FIXED: Use time.sleep instead of await asyncio.sleep
        
        return None
    
    def save_progress(self):
        """Save current progress"""
        try:
            os.makedirs('data', exist_ok=True)
            
            if not self.links:
                cycle_number, position_in_cycle = 1, 1
            else:
                total_links = len(self.links)
                cycle_number = (self.current_index // total_links) + 1
                position_in_cycle = (self.current_index % total_links) + 1
                
                if self.current_index > 0 and self.current_index % total_links == 0:
                    cycle_number = (self.current_index // total_links)
                    position_in_cycle = total_links
            
            ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
            
            progress_data = {
                'current_index': self.current_index,
                'cycle_number': cycle_number,
                'position_in_cycle': position_in_cycle,
                'total_links': len(self.links),
                'last_updated': ist_now.isoformat(),
                'session_type': SESSION_TYPE
            }
            
            # Save locally
            with open('data/progress.json', 'w') as f:
                json.dump(progress_data, f, indent=2)
            
            # Save to GitHub asynchronously
            asyncio.create_task(self.update_progress_on_github(progress_data))
            
            logger.info(f"💾 Progress saved: Index {self.current_index}, Cycle {cycle_number}, Position {position_in_cycle}/{len(self.links)}")
                
        except Exception as e:
            logger.error(f"❌ Error saving progress: {e}")
    
    async def update_progress_on_github(self, progress_data):
        """Update progress file on GitHub"""
        try:
            if not GITHUB_TOKEN:
                return False
            
            success = await self.commit_to_github(
                'data/progress.json', 
                json.dumps(progress_data, indent=2)
            )
            
            if success:
                logger.info("✅ Progress updated on GitHub repository")
            else:
                logger.error("❌ Failed to update progress on GitHub")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error updating progress on GitHub: {e}")
            return False
    
    def convert_amazon_link(self, url):
        """Convert Amazon link to include affiliate tag"""
        try:
            # Remove existing affiliate tags
            url = re.sub(r'[?&]tag=[^&]*', '', url)
            
            # Extract ASIN and create clean link
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
            if asin_match:
                asin = asin_match.group(1)
                return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
            
            # Fallback: append tag
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}tag={AMAZON_AFFILIATE_TAG}"
            
        except Exception as e:
            logger.error(f"❌ Error converting link: {e}")
            return url
    
    def extract_asin_from_url(self, amazon_url):
        """Extract ASIN from Amazon URL"""
        try:
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', amazon_url)
            if asin_match:
                return asin_match.group(1)
            return None
        except Exception as e:
            logger.error(f"❌ Error extracting ASIN: {e}")
            return None
    
    async def get_real_product_info_serpapi(self, asin):
        """Get real product information using SerpApi"""
        if not SERP_API_KEY:
            logger.warning("No SerpApi key - using fallback product info")
            return self.get_fallback_product_info(asin)
        
        try:
            logger.info(f"🔍 Fetching real product data for ASIN: {asin}")
            
            params = {
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'asin': asin,
                'api_key': SERP_API_KEY
            }
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'error' in data:
                    logger.error(f"SerpApi error: {data['error']}")
                    return self.get_fallback_product_info(asin)
                
                product_result = data.get('product_result', {})
                
                if not product_result:
                    logger.warning(f"No product result for ASIN: {asin}")
                    return self.get_fallback_product_info(asin)
                
                # Extract product information
                title = product_result.get('title', f'Amazon Product {asin}')
                price = self.format_price(product_result.get('price'))
                rating = self.format_rating(product_result.get('rating'))
                image = product_result.get('main_image', {}).get('link', '')
                
                if not image:
                    images = product_result.get('images', [])
                    if images:
                        image = images[0].get('link', '')
                
                product_info = {
                    'asin': asin,
                    'title': title[:100] + '...' if len(title) > 100 else title,
                    'image': image,
                    'price': price,
                    'rating': rating,
                    'category': self.categorize_by_title(title),
                    'source': 'serpapi'
                }
                
                logger.info(f"✅ Real product data fetched: {title[:50]}...")
                return product_info
                
        except Exception as e:
            logger.error(f"Error fetching product info via SerpApi: {e}")
        
        return self.get_fallback_product_info(asin)
    
    def format_price(self, price_data):
        """Format price from SerpApi response"""
        if not price_data:
            return "₹Special Price"
        
        if isinstance(price_data, str):
            return price_data if '₹' in price_data else f"₹{price_data}"
        elif isinstance(price_data, dict):
            current_price = price_data.get('current_price')
            if current_price:
                return current_price if '₹' in str(current_price) else f"₹{current_price}"
        
        return "₹Special Price"
    
    def format_rating(self, rating_data):
        """Format rating from SerpApi response"""
        if not rating_data:
            return "⭐⭐⭐⭐⭐"
        
        try:
            if isinstance(rating_data, (int, float)):
                stars = int(rating_data)
            elif isinstance(rating_data, str):
                rating_num = float(rating_data.split()[0])
                stars = int(rating_num)
            else:
                return "⭐⭐⭐⭐⭐"
                
            return "⭐" * min(stars, 5) + "☆" * max(0, 5-stars)
        except:
            return "⭐⭐⭐⭐⭐"
    
    def get_fallback_product_info(self, asin):
        """Fallback product info when SerpApi is not available"""
        return {
            'asin': asin,
            'title': f"Amazon Product {asin}" if asin else "Amazon Deal",
            'image': f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else "",
            'price': "₹Special Price",
            'rating': "⭐⭐⭐⭐⭐",
            'category': "electronics",
            'source': 'fallback'
        }
    
    def categorize_by_title(self, title):
        """Categorize product based on title"""
        title_lower = title.lower()
        
        if any(keyword in title_lower for keyword in ['phone', 'smartphone', 'mobile', 'laptop', 'computer']):
            return 'electronics'
        elif any(keyword in title_lower for keyword in ['shirt', 'tshirt', 'jeans', 'dress', 'shoes']):
            return 'fashion'
        elif any(keyword in title_lower for keyword in ['kitchen', 'furniture', 'home']):
            return 'home'
        elif any(keyword in title_lower for keyword in ['skincare', 'beauty', 'cosmetic']):
            return 'health'
        else:
            return 'electronics'
    
    async def update_website_products(self, new_products):
        """Update website products.json file via GitHub API"""
        try:
            if not GITHUB_TOKEN:
                logger.warning("No GitHub token provided - skipping website update")
                return False
            
            website_products = await self.get_website_products()
            
            # Add new products to the beginning
            for product in reversed(new_products):
                website_products.insert(0, product)
            
            # Keep only latest 50 products
            website_products = website_products[:50]
            
            updated_data = {
                "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                "total_products": len(website_products),
                "daily_target": 6,
                "products": website_products
            }
            
            success = await self.commit_to_github('data/products.json', json.dumps(updated_data, indent=2))
            
            if success:
                logger.info(f"✅ Website updated with {len(new_products)} new products")
                return True
            else:
                logger.error("❌ Failed to update website")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error updating website: {e}")
            return False
    
    async def get_website_products(self):
        """Get existing products from website repository"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/products.json"
            headers = {
                'Authorization': f'token {GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
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
            logger.error(f"❌ Error getting website products: {e}")
            return []
    
    async def commit_to_github(self, file_path, content):
        """Commit file to GitHub repository"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/{file_path}"
            headers = {
                'Authorization': f'token {GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get current file SHA if exists
            response = requests.get(url, headers=headers, timeout=10)
            sha = None
            if response.status_code == 200:
                sha = response.json()['sha']
            
            import base64
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            commit_data = {
                'message': f'Auto-update: {SESSION_TYPE} session - Index {self.current_index}',
                'content': encoded_content,
                'branch': 'main'
            }
            
            if sha:
                commit_data['sha'] = sha
            
            response = requests.put(url, headers=headers, json=commit_data, timeout=30)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Successfully committed {file_path}")
                return True
            else:
                logger.error(f"❌ GitHub commit failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error committing to GitHub: {e}")
            return False
    
    def get_next_links(self, count, purpose="general"):
        """Get next batch of links for scheduling"""
        if not self.links:
            logger.warning("⚠️ No links available for scheduling")
            return []
        
        selected_links = []
        
        logger.info(f"📋 Getting {count} links for {purpose} starting from index {self.current_index}")
        
        for i in range(count):
            if self.current_index >= len(self.links):
                self.current_index = 0
                logger.info(f"🔄 Cycle completed! Wrapping around to index 0")
            
            selected_link = self.links[self.current_index]
            selected_links.append(selected_link)
            
            logger.info(f"   📎 Link {i+1}/{count}: Index {self.current_index} - {selected_link[:50]}...")
            self.current_index += 1
        
        # Save progress after website selection
        if purpose == "website":
            self.save_progress()
        
        logger.info(f"✅ Selected {len(selected_links)} links for {purpose}. Next index: {self.current_index}")
        return selected_links
    
    async def send_scheduled_links(self, session_type):
        """Send links to Telegram and update Website"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        telegram_count = config['telegram_links']
        website_count = config['website_links']
        time_slot = config['time']
        
        logger.info(f"🚀 Starting {session_type} session: {time_slot} IST")
        logger.info(f"📱 Telegram posts: {telegram_count}")
        logger.info(f"🌐 Website posts: {website_count}")
        logger.info(f"📍 Starting from index: {self.current_index}")
        
        # Get links for Telegram
        telegram_links = self.get_next_links(telegram_count, "telegram")
        # Get separate links for website
        website_links = self.get_next_links(website_count, "website")
        
        if not telegram_links and not website_links:
            logger.error("❌ No links available to send")
            return 0
        
        sent_count = 0
        website_products = []
        
        # Send to Telegram
        logger.info("📱 Sending to Telegram...")
        for i, original_link in enumerate(telegram_links, 1):
            try:
                converted_link = self.convert_amazon_link(original_link)
                
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
                
                ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                logger.info(f"✅ Telegram {i}/{telegram_count} sent at {ist_time} IST")
                
                sent_count += 1
                await asyncio.sleep(4)
                    
            except Exception as e:
                logger.error(f"❌ Error sending to Telegram {i}: {e}")
        
        # Process Website Products
        logger.info("🌐 Processing website products...")
        for i, original_link in enumerate(website_links, 1):
            try:
                converted_link = self.convert_amazon_link(original_link)
                asin = self.extract_asin_from_url(original_link)
                
                # Get product information
                product_info = await self.get_real_product_info_serpapi(asin)
                
                website_product = {
                    'id': f"product_{session_type}_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'title': product_info['title'],
                    'image': product_info['image'],
                    'affiliate_link': converted_link,
                    'price': product_info['price'],
                    'rating': product_info['rating'],
                    'category': product_info['category'],
                    'asin': product_info['asin'],
                    'data_source': product_info.get('source', 'unknown'),
                    'posted_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                    'session_type': session_type,
                    'link_index': self.current_index - website_count + i - 1
                }
                
                website_products.append(website_product)
                
                logger.info(f"✅ Website product {i}/{website_count} processed")
                
                if i < len(website_links):
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"❌ Error processing website product {i}: {e}")
        
        # Update website
        if website_products:
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"✅ Website updated with {len(website_products)} products")
            else:
                logger.error("❌ Website update failed")
        
        # Final summary
        total_links = len(self.links) if self.links else 0
        cycle_number = (self.current_index // total_links) if total_links > 0 else 1
        remaining_in_cycle = total_links - (self.current_index % total_links) if total_links > 0 else 0
        
        logger.info(f"📊 {session_type.upper()} SESSION COMPLETE:")
        logger.info(f"   📱 Telegram: {sent_count}/{telegram_count} links posted")
        logger.info(f"   🌐 Website: {len(website_products)} products updated")
        logger.info(f"   📍 Progress: {self.current_index}/{total_links}")
        logger.info(f"   🔄 Cycle: {cycle_number}, Remaining: {remaining_in_cycle}")
        
        return sent_count

# Main execution function
async def main():
    """Main function for scheduled execution"""
    logger.info("🚀 Starting Enhanced Telegram + Website Bot with SerpApi...")
    logger.info(f"📅 Session Type: {SESSION_TYPE.upper()}")
    
    required_vars = [BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG]
    if not all(required_vars):
        logger.error("❌ Missing required environment variables")
        exit(1)
    
    if not SERP_API_KEY:
        logger.warning("⚠️ No SerpApi key found - will use fallback product data")
    
    bot_instance = EnhancedAffiliateBot()
    
    logger.info(f"📊 Total links loaded: {len(bot_instance.links)}")
    logger.info(f"📍 Starting from index: {bot_instance.current_index}")
    logger.info(f"🎯 Target channel: {CHANNEL_ID}")
    logger.info(f"🌐 Target website: {WEBSITE_REPO}")
    
    try:
        sent_count = await bot_instance.send_scheduled_links(SESSION_TYPE)
        logger.info(f"🎉 Session completed! Telegram: {sent_count} links, Website: Updated")
        
    except Exception as e:
        logger.error(f"❌ Error in session: {e}")
        exit(1)

if __name__ == '__main__':
    asyncio.run(main())
