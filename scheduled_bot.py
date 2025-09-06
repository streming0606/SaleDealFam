#!/usr/bin/env python3
import logging
import re
import os
import json
import asyncio
from datetime import datetime
import pytz
import requests
import base64
import sys
from telegram import Bot
from telegram.error import TelegramError

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(_name_)

# Configuration with debugging
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
AMAZON_AFFILIATE_TAG = os.environ.get('AMAZON_TAG')
SESSION_TYPE = os.environ.get('SESSION_TYPE', 'morning')
WEBSITE_REPO = "streming0606/DealFamSheduler"
PERSONAL_ACCESS_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')
SERPAPI_KEY = os.environ.get('SERPAPI_KEY')

SESSION_CONFIG = {
    'morning': {'links': 3, 'time': '10:12-10:20 AM'},
    'afternoon': {'links': 3, 'time': '1:12-1:20 PM'},
    'evening': {'links': 2, 'time': '6:12-6:20 PM'},
    'night': {'links': 2, 'time': '9:12-9:20 PM'}
}

def validate_environment():
    """Validate all required environment variables"""
    logger.info("🔧 Validating environment variables...")
    
    required_vars = {
        'BOT_TOKEN': BOT_TOKEN,
        'CHANNEL_ID': CHANNEL_ID,
        'AMAZON_AFFILIATE_TAG': AMAZON_AFFILIATE_TAG,
        'PERSONAL_ACCESS_TOKEN': PERSONAL_ACCESS_TOKEN
    }
    
    missing_vars = []
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing_vars.append(var_name)
        else:
            logger.info(f"✅ {var_name}: {'*' * 8}{var_value[-4:]}")
    
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    # Optional variables
    if SERPAPI_KEY:
        logger.info(f"✅ SERPAPI_KEY: {'*' * 8}{SERPAPI_KEY[-4:]}")
    else:
        logger.warning("⚠ SERPAPI_KEY not found - will use fallback data")
    
    return True

class DebuggedAffiliateBot:
    def _init_(self):
        logger.info("🤖 Initializing bot...")
        
        try:
            self.bot = Bot(token=BOT_TOKEN)
            logger.info("✅ Telegram bot initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Telegram bot: {e}")
            raise
        
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        
        logger.info(f"📊 Loaded {len(self.links)} Amazon links")
        logger.info(f"📍 Current index: {self.current_index}")
    
    def load_amazon_links(self):
        """Load Amazon links with error handling"""
        try:
            os.makedirs('data', exist_ok=True)
            
            if os.path.exists('data/amazon_links.json'):
                with open('data/amazon_links.json', 'r') as f:
                    data = json.load(f)
                    links = data.get('links', [])
                    logger.info(f"✅ Loaded {len(links)} links from file")
                    return links
            else:
                logger.warning("⚠ amazon_links.json not found - creating sample data")
                # Create sample data for testing
                sample_links = [
                    "https://www.amazon.in/dp/B08CFSZLQ4",
                    "https://www.amazon.in/dp/B07HGJKJL2",
                    "https://www.amazon.in/dp/B08BHBQKP7"
                ]
                self.save_amazon_links(sample_links)
                return sample_links
                
        except Exception as e:
            logger.error(f"❌ Error loading Amazon links: {e}")
            return []
    
    def save_amazon_links(self, links):
        """Save Amazon links to file"""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/amazon_links.json', 'w') as f:
                json.dump({'links': links}, f, indent=2)
            logger.info(f"✅ Saved {len(links)} links to file")
        except Exception as e:
            logger.error(f"❌ Error saving links: {e}")
    
    def load_progress(self):
        """Load progress with error handling"""
        try:
            if os.path.exists('data/progress.json'):
                with open('data/progress.json', 'r') as f:
                    data = json.load(f)
                    return data.get('current_index', 0)
            else:
                logger.info("📍 No progress file found - starting from index 0")
                return 0
        except Exception as e:
            logger.error(f"❌ Error loading progress: {e}")
            return 0
    
    def save_progress(self):
        """Save progress with error handling"""
        try:
            os.makedirs('data', exist_ok=True)
            progress_data = {
                'current_index': self.current_index,
                'total_links': len(self.links),
                'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
            }
            with open('data/progress.json', 'w') as f:
                json.dump(progress_data, f, indent=2)
            logger.info(f"✅ Saved progress: index {self.current_index}")
        except Exception as e:
            logger.error(f"❌ Error saving progress: {e}")
    
    def convert_amazon_link(self, url):
        """Convert Amazon link to affiliate link"""
        try:
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
            if asin_match:
                asin = asin_match.group(1)
                return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
            
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}tag={AMAZON_AFFILIATE_TAG}"
        except Exception as e:
            logger.error(f"❌ Error converting link: {e}")
            return url
    
    def extract_asin(self, url):
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return asin_match.group(1) if asin_match else None
    
    def get_product_data(self, amazon_url):
        """Get product data with SerpApi or fallback"""
        asin = self.extract_asin(amazon_url)
        
        # Try SerpApi if available
        if SERPAPI_KEY:
            try:
                logger.info(f"🔍 Fetching SerpApi data for ASIN: {asin}")
                
                params = {
                    'engine': 'amazon_product',
                    'asin': asin,
                    'api_key': SERPAPI_KEY,
                    'country': 'in'
                }
                
                response = requests.get('https://serpapi.com/search', params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if 'product_result' in data:
                        product = data['product_result']
                        
                        product_data = {
                            'title': product.get('title', f'Amazon Product {asin}')[:100],
                            'price': self.format_price(product.get('buybox', {}).get('price', {})),
                            'image': self.get_image_from_serpapi(product.get('images', [])),
                            'rating': self.format_rating(product.get('rating', {})),
                            'category': self.categorize_product(amazon_url),
                            'asin': asin
                        }
                        
                        logger.info(f"✅ SerpApi success: {product_data['title'][:50]}...")
                        return product_data
                    else:
                        logger.warning("⚠ No product_result in SerpApi response")
                else:
                    logger.warning(f"⚠ SerpApi error: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"❌ SerpApi request failed: {e}")
        
        # Fallback data
        logger.info(f"🔄 Using fallback data for ASIN: {asin}")
        return {
            'title': f'Premium Amazon Deal - {asin}' if asin else 'Amazon Special Offer',
            'price': '₹Special Price',
            'image': f"https://images-na.ssl-images-amazon.com/images/I/{asin}.AC_SL1500.jpg" if asin else "",
            'rating': '⭐⭐⭐⭐⭐',
            'category': 'electronics',
            'asin': asin
        }
    
    def format_price(self, price_data):
        """Format price from SerpApi data"""
        if isinstance(price_data, dict):
            value = price_data.get('value')
            if value:
                return f"₹{value:,.0f}" if isinstance(value, (int, float)) else f"₹{value}"
        return "₹Special Price"
    
    def format_rating(self, rating_data):
        """Format rating from SerpApi data"""
        if isinstance(rating_data, dict):
            rating = rating_data.get('rating')
            if rating:
                try:
                    rating_num = float(rating)
                    stars = '⭐' * min(int(round(rating_num)), 5)
                    return f"{stars} ({rating_num})"
                except:
                    pass
        return '⭐⭐⭐⭐⭐'
    
    def get_image_from_serpapi(self, images_data):
        """Extract image URL from SerpApi images array"""
        if isinstance(images_data, list) and images_data:
            for image in images_data:
                if isinstance(image, dict):
                    image_url = image.get('link') or image.get('url')
                    if image_url:
                        return image_url
        return ""
    
    def categorize_product(self, url):
        """Simple product categorization"""
        url_lower = url.lower()
        
        if any(word in url_lower for word in ['phone', 'mobile', 'laptop', 'electronics']):
            return 'electronics'
        elif any(word in url_lower for word in ['fashion', 'clothing', 'shoes']):
            return 'fashion'
        elif any(word in url_lower for word in ['home', 'kitchen', 'furniture']):
            return 'home'
        else:
            return 'electronics'
    
    def get_next_links(self, count):
        """Get next batch of links with error handling"""
        if not self.links:
            logger.error("❌ No Amazon links available!")
            return []
        
        selected = []
        for i in range(count):
            if self.current_index >= len(self.links):
                self.current_index = 0
                logger.info("🔄 Cycling back to beginning of links")
            
            selected.append(self.links[self.current_index])
            self.current_index += 1
        
        self.save_progress()
        return selected
    
    async def send_to_telegram(self, message):
        """Send message to Telegram with error handling"""
        try:
            await self.bot.send_message(
                chat_id=CHANNEL_ID,
                text=message,
                parse_mode='Markdown'
            )
            logger.info("✅ Telegram message sent successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Telegram send failed: {e}")
            return False
    
    async def update_website(self, products):
        """Update website with new products"""
        try:
            logger.info(f"🌐 Updating website with {len(products)} products...")
            
            # Get existing products
            existing_products = await self.get_existing_products()
            
            # Add new products at beginning
            for product in reversed(products):
                existing_products.insert(0, product)
            
            # Keep latest 100
            existing_products = existing_products[:100]
            
            # Update data structure
            updated_data = {
                "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                "total_products": len(existing_products),
                "products": existing_products
            }
            
            # Commit to GitHub
            success = await self.commit_to_github('data/products.json', json.dumps(updated_data, indent=2))
            
            if success:
                logger.info(f"✅ Website updated successfully")
            else:
                logger.error("❌ Website update failed")
                
            return success
            
        except Exception as e:
            logger.error(f"❌ Website update error: {e}")
            return False
    
    async def get_existing_products(self):
        """Get existing products from website repository"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/products.json"
            headers = {
                'Authorization': f'token {PERSONAL_ACCESS_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                file_content = response.json()
                content = base64.b64decode(file_content['content']).decode('utf-8')
                data = json.loads(content)
                return data.get('products', [])
            else:
                logger.info("📄 No existing products file found")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error getting existing products: {e}")
            return []
    
    async def commit_to_github(self, file_path, content):
        """Commit file to GitHub repository"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/{file_path}"
            headers = {
                'Authorization': f'token {PERSONAL_ACCESS_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get existing file SHA if exists
            response = requests.get(url, headers=headers, timeout=30)
            sha = None
            if response.status_code == 200:
                sha = response.json()['sha']
            
            # Prepare commit data
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            commit_data = {
                'message': f'🤖 Auto-update: {SESSION_TYPE} session with debugged bot',
                'content': encoded_content,
                'branch': 'main'
            }
            
            if sha:
                commit_data['sha'] = sha
            
            # Make commit
            response = requests.put(url, headers=headers, json=commit_data, timeout=30)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ GitHub commit successful")
                return True
            else:
                logger.error(f"❌ GitHub commit failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ GitHub commit error: {e}")
            return False
    
    async def process_session(self, session_type):
        """Process a session with comprehensive error handling"""
        try:
            config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
            link_count = config['links']
            
            logger.info(f"🚀 Starting {session_type} session")
            logger.info(f"📊 Will process {link_count} links")
            
            # Get links to process
            links = self.get_next_links(link_count)
            if not links:
                logger.error("❌ No links available for processing")
                return 0
            
            processed_count = 0
            website_products = []
            
            for i, url in enumerate(links, 1):
                try:
                    logger.info(f"📦 Processing product {i}/{link_count}")
                    
                    # Convert to affiliate link
                    affiliate_link = self.convert_amazon_link(url)
                    logger.info(f"🔗 Affiliate link: {affiliate_link}")
                    
                    # Get product data
                    product_data = self.get_product_data(url)
                    
                    # Create Telegram message
                    telegram_message = f"""🔥 DEAL FAM ALERT! 🔥

📱 *{product_data['title']}*

💰 *Price:* {product_data['price']}
⭐ *Rating:* {product_data['rating']}
🏷 *Category:* {product_data['category'].title()}

🛒 *Get Deal:* {affiliate_link}

⏰ *Limited Time Offer - Grab Now!*

#DealFam #AmazonDeals #Shopping #{product_data['category'].title()}Deals"""
                    
                    # Send to Telegram
                    telegram_success = await self.send_to_telegram(telegram_message)
                    
                    if telegram_success:
                        # Prepare for website
                        website_product = {
                            'id': f"debug_{session_type}{i}{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                            'title': product_data['title'],
                            'image': product_data['image'],
                            'affiliate_link': affiliate_link,
                            'price': product_data['price'],
                            'rating': product_data['rating'],
                            'category': product_data['category'],
                            'posted_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                            'session_type': session_type,
                            'asin': product_data['asin'],
                            'source': 'debugged-bot'
                        }
                        
                        website_products.append(website_product)
                        processed_count += 1
                        
                        logger.info(f"✅ Successfully processed product {i}/{link_count}")
                    else:
                        logger.error(f"❌ Failed to send product {i} to Telegram")
                    
                    # Wait between requests
                    if i < len(links):
                        await asyncio.sleep(3)
                        
                except Exception as e:
                    logger.error(f"❌ Error processing product {i}: {e}")
                    continue
            
            # Update website if we have products
            if website_products:
                website_success = await self.update_website(website_products)
                if website_success:
                    logger.info(f"🌐 Website updated with {len(website_products)} products")
            
            # Final summary
            logger.info(f"🎉 {session_type.upper()} SESSION COMPLETE:")
            logger.info(f"   ✅ Processed: {processed_count}/{link_count} products")
            logger.info(f"   📱 Telegram posts: {processed_count}")
            logger.info(f"   🌐 Website products: {len(website_products)}")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ Session processing error: {e}")
            raise

async def main():
    """Main function with comprehensive error handling"""
    try:
        logger.info("🚀 Starting Debugged Affiliate Bot...")
        logger.info(f"📅 Session Type: {SESSION_TYPE}")
        logger.info(f"🕒 Current IST Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Validate environment
        if not validate_environment():
            logger.error("❌ Environment validation failed")
            sys.exit(1)
        
        # Create and run bot
        bot = DebuggedAffiliateBot()
        result = await bot.process_session(SESSION_TYPE)
        
        logger.info(f"🎉 Bot completed successfully! Processed {result} products")
        
    except Exception as e:
        logger.error(f"❌ Main function error: {e}")
        logger.error(f"❌ Error type: {type(e)._name_}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        sys.exit(1)

if _name_ == '_main_':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ Asyncio run error: {e}")
        sys.exit(1)
