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
WEBSITE_REPO = "streming0606/DealFamSheduler"
GITHUB_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')
SERP_API_KEY = os.environ.get('SERP_API_KEY')  # 🆕 Add SerpApi key

# 🔄 Updated session configuration - 6 products total for website
SESSION_CONFIG = {
    'morning': {'telegram_links': 3, 'website_links': 2, 'time': '10:12-10:20 AM'},
    'afternoon': {'telegram_links': 3, 'website_links': 2, 'time': '1:12-1:20 PM'},
    'evening': {'telegram_links': 2, 'website_links': 1, 'time': '6:12-6:20 PM'},
    'night': {'telegram_links': 2, 'website_links': 1, 'time': '9:12-9:20 PM'}
}

class EnhancedAffiliateBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        
        logger.info(f"📊 Loaded {len(self.links)} total links")
        logger.info(f"📍 Starting from index: {self.current_index}")
        logger.info(f"🔑 SerpApi available: {'Yes' if SERP_API_KEY else 'No'}")
        
    def load_amazon_links(self):
        """Load Amazon links from file"""
        try:
            os.makedirs('data', exist_ok=True)
            if os.path.exists('data/amazon_links.json'):
                with open('data/amazon_links.json', 'r') as f:
                    data = json.load(f)
                    links = data.get('links', [])
                    logger.info(f"✅ Loaded {len(links)} links from amazon_links.json")
                    return links
        except Exception as e:
            logger.error(f"Error loading links: {e}")
        
        logger.warning("⚠️ No links loaded - returning empty list")
        return []
    
    def load_progress(self):
        """Load current progress from GitHub repository"""
        try:
            progress = self.get_progress_from_github()
            if progress is not None:
                logger.info(f"📈 Loaded progress from GitHub: index {progress}")
                return progress
            else:
                if os.path.exists('data/progress.json'):
                    with open('data/progress.json', 'r') as f:
                        data = json.load(f)
                        index = data.get('current_index', 0)
                        logger.info(f"📈 Loaded progress from local file: index {index}")
                        return index
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
        
        logger.info("📈 No progress found - starting from index 0")
        return 0
    
    def get_progress_from_github(self):
        """Get current progress from GitHub repository"""
        try:
            if not GITHUB_TOKEN:
                return None
                
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/progress.json"
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
                return data.get('current_index', 0)
            else:
                logger.info("No progress file found in GitHub repository")
                return None
                
        except Exception as e:
            logger.error(f"Error getting progress from GitHub: {e}")
            return None
    
    def save_progress(self):
        """Save current progress to both local and GitHub"""
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
            
            progress_data = {
                'current_index': self.current_index,
                'cycle_number': cycle_number,
                'position_in_cycle': position_in_cycle,
                'total_links': len(self.links),
                'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                'session_type': SESSION_TYPE
            }
            
            with open('data/progress.json', 'w') as f:
                json.dump(progress_data, f, indent=2)
            
            asyncio.create_task(self.update_progress_on_github(progress_data))
            
            logger.info(f"💾 Progress saved: Index {self.current_index}, Cycle {cycle_number}, Position {position_in_cycle}/{len(self.links)}")
                
        except Exception as e:
            logger.error(f"Error saving progress: {e}")
    
    async def update_progress_on_github(self, progress_data):
        """Update progress file on GitHub repository"""
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
            logger.error(f"Error updating progress on GitHub: {e}")
            return False
    
    def convert_amazon_link(self, url):
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
    
    def extract_asin_from_url(self, amazon_url):
        """Extract ASIN from Amazon URL"""
        try:
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', amazon_url)
            if asin_match:
                return asin_match.group(1)
            return None
        except Exception as e:
            logger.error(f"Error extracting ASIN: {e}")
            return None
    
    def get_real_product_info_serpapi(self, asin):
        """🆕 Get real product information using SerpApi"""
        if not SERP_API_KEY:
            logger.warning("No SerpApi key - using fallback product info")
            return self.get_fallback_product_info(asin)
        
        try:
            logger.info(f"🔍 Fetching real product data for ASIN: {asin}")
            
            # SerpApi Amazon search parameters
            params = {
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'asin': asin,
                'api_key': SERP_API_KEY
            }
            
            # Make API request
            response = requests.get('https://serpapi.com/search', params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract product information
                product_result = data.get('product_result', {})
                
                # Get real product data
                title = product_result.get('title', f'Amazon Product {asin}')
                price = self.format_price(product_result.get('price'))
                rating = self.format_rating(product_result.get('rating'))
                image = product_result.get('main_image', {}).get('link', '')
                
                # Alternative image sources
                if not image:
                    images = product_result.get('images', [])
                    if images:
                        image = images[0].get('link', '')
                
                product_info = {
                    'asin': asin,
                    'title': title[:100] + '...' if len(title) > 100 else title,  # Limit title length
                    'image': image,
                    'price': price,
                    'rating': rating,
                    'category': self.categorize_by_title(title),
                    'source': 'serpapi'
                }
                
                logger.info(f"✅ Real product data fetched: {title[:50]}...")
                logger.info(f"   💰 Price: {price}")
                logger.info(f"   ⭐ Rating: {rating}")
                logger.info(f"   🖼️ Image: {'Available' if image else 'Not available'}")
                
                return product_info
                
            else:
                logger.warning(f"SerpApi request failed: {response.status_code}")
                return self.get_fallback_product_info(asin)
                
        except Exception as e:
            logger.error(f"Error fetching product info via SerpApi: {e}")
            return self.get_fallback_product_info(asin)
    
    def format_price(self, price_data):
        """Format price from SerpApi response"""
        if not price_data:
            return "₹Price on request"
        
        if isinstance(price_data, str):
            return price_data if '₹' in price_data else f"₹{price_data}"
        elif isinstance(price_data, dict):
            # Handle different price formats
            current_price = price_data.get('current_price')
            if current_price:
                return current_price if '₹' in str(current_price) else f"₹{current_price}"
        
        return "₹Special Price"
    
    def format_rating(self, rating_data):
        """Format rating from SerpApi response"""
        if not rating_data:
            return "⭐⭐⭐⭐⭐"
        
        if isinstance(rating_data, (int, float)):
            stars = int(rating_data)
            return "⭐" * min(stars, 5) + "☆" * max(0, 5-stars)
        elif isinstance(rating_data, str):
            try:
                rating_num = float(rating_data.split()[0])
                stars = int(rating_num)
                return "⭐" * min(stars, 5) + "☆" * max(0, 5-stars)
            except:
                return "⭐⭐⭐⭐⭐"
        
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
        """Enhanced categorization based on product title"""
        title_lower = title.lower()
        
        if any(keyword in title_lower for keyword in ['phone', 'smartphone', 'mobile', 'iphone', 'samsung', 'oneplus']):
            return 'electronics'
        elif any(keyword in title_lower for keyword in ['laptop', 'computer', 'macbook', 'dell', 'hp', 'lenovo']):
            return 'electronics'
        elif any(keyword in title_lower for keyword in ['shirt', 'tshirt', 't-shirt', 'jeans', 'dress', 'shoes', 'sneakers']):
            return 'fashion'
        elif any(keyword in title_lower for keyword in ['kitchen', 'cookware', 'furniture', 'home decor', 'bedsheet']):
            return 'home'
        elif any(keyword in title_lower for keyword in ['skincare', 'shampoo', 'cream', 'beauty', 'cosmetic']):
            return 'health'
        elif any(keyword in title_lower for keyword in ['fitness', 'gym', 'yoga', 'sports', 'exercise']):
            return 'sports'
        elif any(keyword in title_lower for keyword in ['car', 'bike', 'automotive', 'vehicle']):
            return 'vehicle'
        elif any(keyword in title_lower for keyword in ['book', 'novel', 'kindle', 'ebook']):
            return 'books'
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
            
            # Keep only latest 50 products for better performance
            website_products = website_products[:50]
            
            updated_data = {
                "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                "total_products": len(website_products),
                "daily_target": 6,  # 🆕 Track daily target
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
            logger.error(f"Error committing to GitHub: {e}")
            return False
    
    def get_next_links(self, count, purpose="general"):
        """Get next batch of links for scheduling with proper progression"""
        if not self.links:
            logger.warning("⚠️ No links available for scheduling")
            return []
        
        selected_links = []
        starting_index = self.current_index
        
        logger.info(f"📋 Getting {count} links for {purpose} starting from index {self.current_index}")
        
        for i in range(count):
            if self.current_index >= len(self.links):
                self.current_index = 0
                logger.info(f"🔄 Cycle completed! Wrapping around to index 0")
            
            selected_link = self.links[self.current_index]
            selected_links.append(selected_link)
            
            logger.info(f"   📎 Link {i+1}/{count}: Index {self.current_index} - {selected_link[:50]}...")
            
            self.current_index += 1
        
        # Only save progress once per session
        if purpose == "website":  # Save after website selection
            self.save_progress()
        
        logger.info(f"✅ Selected {len(selected_links)} links for {purpose}. Next index: {self.current_index}")
        return selected_links
    
    async def send_scheduled_links(self, session_type):
        """🔄 Updated: Send links to Telegram and fewer products to Website"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        telegram_count = config['telegram_links']
        website_count = config['website_links']
        time_slot = config['time']
        
        logger.info(f"🕐 Starting {session_type} session: {time_slot} IST")
        logger.info(f"📱 Telegram posts: {telegram_count}")
        logger.info(f"🌐 Website posts: {website_count}")
        logger.info(f"📍 Starting from index: {self.current_index}")
        
        # Get links for Telegram
        telegram_links = self.get_next_links(telegram_count, "telegram")
        # Get separate links for website (with real product data)
        website_links = self.get_next_links(website_count, "website")
        
        if not telegram_links and not website_links:
            logger.error("❌ No links available to send")
            return 0
        
        sent_count = 0
        website_products = []
        
        # 📱 Send to Telegram
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
        
        # 🌐 Process Website Products with Real Data
        logger.info("🌐 Processing website products with real data...")
        for i, original_link in enumerate(website_links, 1):
            try:
                converted_link = self.convert_amazon_link(original_link)
                asin = self.extract_asin_from_url(original_link)
                
                # 🆕 Get real product information using SerpApi
                product_info = self.get_real_product_info_serpapi(asin)
                
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
                logger.info(f"   📋 Title: {product_info['title'][:50]}...")
                logger.info(f"   💰 Price: {product_info['price']}")
                logger.info(f"   🖼️ Image: {'Available' if product_info['image'] else 'No image'}")
                
                # Rate limiting for SerpApi
                if i < len(website_links):
                    await asyncio.sleep(2)
                    
            except Exception as e:
                logger.error(f"❌ Error processing website product {i}: {e}")
        
        # Update website with enhanced product data
        if website_products:
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"✅ Website updated with {len(website_products)} enhanced products")
            else:
                logger.error("❌ Website update failed")
        
        # Final summary
        total_links = len(self.links) if self.links else 0
        cycle_number = (self.current_index // total_links) if total_links > 0 else 1
        remaining_in_cycle = total_links - (self.current_index % total_links) if total_links > 0 else 0
        
        logger.info(f"📊 {session_type.upper()} SESSION COMPLETE:")
        logger.info(f"   📱 Telegram: {sent_count}/{telegram_count} links posted")
        logger.info(f"   🌐 Website: {len(website_products)} products with real data")
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
        logger.info(f"🎉 Enhanced session completed! Telegram: {sent_count} links, Website: Updated with real data")
        
    except Exception as e:
        logger.error(f"❌ Error in enhanced session: {e}")
        exit(1)

if __name__ == '__main__':
    asyncio.run(main())
