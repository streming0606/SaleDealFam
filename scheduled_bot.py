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
import random
from telegram import Bot
from telegram.error import TelegramError

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(_name_)

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
AMAZON_AFFILIATE_TAG = os.environ.get('AMAZON_TAG')
SESSION_TYPE = os.environ.get('SESSION_TYPE', 'morning')
WEBSITE_REPO = "streming0606/DealFamSheduler"
PERSONAL_ACCESS_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')

# SerpApi Configuration - Add these secrets to GitHub
SERPAPI_KEY_1 = os.environ.get('SERPAPI_KEY_1')  # First account API key
SERPAPI_KEY_2 = os.environ.get('SERPAPI_KEY_2')  # Second account API key

SESSION_CONFIG = {
    'morning': {'links': 3, 'time': '10:12-10:20 AM'},
    'afternoon': {'links': 3, 'time': '1:12-1:20 PM'},
    'evening': {'links': 2, 'time': '6:12-6:20 PM'},
    'night': {'links': 2, 'time': '9:12-9:20 PM'}
}

class SerpApiAmazonBot:
    def _init_(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        
        # SerpApi keys rotation
        self.serpapi_keys = [key for key in [SERPAPI_KEY_1, SERPAPI_KEY_2] if key]
        self.current_api_key_index = 0
        
        if not self.serpapi_keys:
            logger.error("❌ No SerpApi keys provided!")
            
        logger.info(f"✅ Loaded {len(self.serpapi_keys)} SerpApi keys")
    
    def get_current_serpapi_key(self):
        """Get current SerpApi key and rotate"""
        if not self.serpapi_keys:
            return None
            
        key = self.serpapi_keys[self.current_api_key_index]
        self.current_api_key_index = (self.current_api_key_index + 1) % len(self.serpapi_keys)
        return key
    
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
            progress_data = {
                'current_index': self.current_index,
                'total_links': len(self.links),
                'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
            }
            with open('data/progress.json', 'w') as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving progress: {e}")
    
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
            logger.error(f"Error converting link: {e}")
            return url
    
    def extract_asin_from_url(self, url):
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return asin_match.group(1) if asin_match else None
    
    def get_product_data_via_serpapi(self, amazon_url):
        """Get comprehensive product data using SerpApi"""
        try:
            # Extract ASIN for better search
            asin = self.extract_asin_from_url(amazon_url)
            
            if not asin:
                logger.warning(f"No ASIN found in URL: {amazon_url}")
                return self.get_fallback_product_data(amazon_url)
            
            # Get current API key
            api_key = self.get_current_serpapi_key()
            if not api_key:
                logger.error("No SerpApi key available")
                return self.get_fallback_product_data(amazon_url)
            
            logger.info(f"🔍 Fetching product data for ASIN: {asin}")
            
            # SerpApi Amazon Product API call
            params = {
                "engine": "amazon_product",
                "asin": asin,
                "api_key": api_key,
                "country": "in"  # India
            }
            
            response = requests.get("https://serpapi.com/search", params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return self.parse_serpapi_response(data, amazon_url)
            else:
                logger.warning(f"SerpApi request failed: {response.status_code}")
                return self.get_fallback_product_data(amazon_url)
                
        except Exception as e:
            logger.error(f"Error with SerpApi: {e}")
            return self.get_fallback_product_data(amazon_url)
    
    def parse_serpapi_response(self, data, original_url):
        """Parse SerpApi response to extract product data"""
        try:
            # Extract product information from SerpApi response
            product_info = data.get('product_result', {})
            
            # Title
            title = (product_info.get('title') or 
                    data.get('search_metadata', {}).get('amazon_product_title') or
                    "Amazon Product")
            
            # Price
            price_info = product_info.get('buybox', {})
            price = (price_info.get('price', {}).get('value') or
                    product_info.get('price') or
                    "Special Price")
            
            if isinstance(price, (int, float)):
                price = f"₹{price:,.0f}"
            elif not price.startswith('₹'):
                price = f"₹{price}"
            
            # Rating
            rating_info = product_info.get('rating')
            if rating_info:
                rating_value = rating_info.get('rating', 0)
                stars = '⭐' * min(int(float(rating_value)), 5)
                rating = f"{stars} ({rating_value})"
            else:
                rating = '⭐⭐⭐⭐⭐'
            
            # Images - Get the highest quality image
            images = product_info.get('images', [])
            image_url = ""
            
            if images:
                # Try to get the first/main image
                if isinstance(images, list) and len(images) > 0:
                    image_url = images.get('link', '')
                elif isinstance(images, dict):
                    image_url = images.get('link', '')
            
            # Category
            breadcrumbs = data.get('breadcrumbs', [])
            category = 'electronics'  # default
            
            if breadcrumbs:
                for crumb in breadcrumbs:
                    name = crumb.get('name', '').lower()
                    category = self.categorize_from_text(name)
                    if category != 'electronics':  # Found a specific category
                        break
            
            # ASIN
            asin = self.extract_asin_from_url(original_url)
            
            product_data = {
                'title': title[:120] + "..." if len(title) > 120 else title,
                'price': price,
                'rating': rating,
                'image': image_url,
                'category': category,
                'asin': asin
            }
            
            logger.info(f"✅ SerpApi extracted: {product_data['title'][:50]}...")
            logger.info(f"📸 Image URL: {'Available' if image_url else 'Not found'}")
            
            return product_data
            
        except Exception as e:
            logger.error(f"Error parsing SerpApi response: {e}")
            return self.get_fallback_product_data(original_url)
    
    def categorize_from_text(self, text):
        """Categorize product from text"""
        text_lower = text.lower()
        
        categories = {
            'electronics': ['electronic', 'phone', 'mobile', 'laptop', 'computer', 'gadget', 'camera'],
            'fashion': ['clothing', 'fashion', 'shoes', 'watch', 'jewelry', 'apparel'],
            'home': ['home', 'kitchen', 'furniture', 'decor', 'appliance'],
            'health': ['health', 'beauty', 'care', 'cosmetic', 'wellness'],
            'sports': ['sports', 'fitness', 'gym', 'outdoor', 'exercise'],
            'vehicle': ['automotive', 'car', 'bike', 'vehicle'],
            'books': ['books', 'kindle', 'reading']
        }
        
        for category, keywords in categories.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
                
        return 'electronics'
    
    def get_fallback_product_data(self, url):
        """Fallback product data when SerpApi fails"""
        asin = self.extract_asin_from_url(url)
        
        return {
            'title': f"Premium Amazon Product {asin}" if asin else "Special Amazon Deal",
            'price': "₹Special Price",
            'rating': '⭐⭐⭐⭐⭐',
            'image': f"https://images-na.ssl-images-amazon.com/images/I/{asin}.AC_SL1500.jpg" if asin else "",
            'category': 'electronics',
            'asin': asin
        }
    
    async def update_website_products(self, new_products):
        """Update website with SerpApi-enhanced products"""
        try:
            if not PERSONAL_ACCESS_TOKEN:
                logger.warning("No GitHub token - skipping website update")
                return False
            
            # Get existing products
            website_products = await self.get_website_products()
            
            # Add new products to beginning
            for product in reversed(new_products):
                website_products.insert(0, product)
            
            # Keep latest 100
            website_products = website_products[:100]
            
            # Update JSON
            updated_data = {
                "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                "total_products": len(website_products),
                "api_source": "SerpApi Enhanced",
                "products": website_products
            }
            
            # Commit to GitHub
            success = await self.commit_to_github('data/products.json', json.dumps(updated_data, indent=2))
            
            if success:
                logger.info(f"✅ Website updated with {len(new_products)} SerpApi products")
                return True
            else:
                logger.error("❌ Website update failed")
                return False
                
        except Exception as e:
            logger.error(f"Error updating website: {e}")
            return False
    
    async def get_website_products(self):
        """Get existing website products"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/products.json"
            headers = {
                'Authorization': f'token {PERSONAL_ACCESS_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                file_content = response.json()
                content = base64.b64decode(file_content['content']).decode('utf-8')
                data = json.loads(content)
                return data.get('products', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting website products: {e}")
            return []
    
    async def commit_to_github(self, file_path, content):
        """Commit to GitHub repository"""
        try:
            url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/{file_path}"
            headers = {
                'Authorization': f'token {PERSONAL_ACCESS_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get existing file SHA
            response = requests.get(url, headers=headers)
            sha = None
            if response.status_code == 200:
                sha = response.json()['sha']
            
            # Prepare commit
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            commit_data = {
                'message': f'🚀 SerpApi update: {SESSION_TYPE} session with reliable product data',
                'content': encoded_content,
                'branch': 'main'
            }
            
            if sha:
                commit_data['sha'] = sha
            
            # Commit
            response = requests.put(url, headers=headers, json=commit_data)
            
            return response.status_code in [200, 201]
                
        except Exception as e:
            logger.error(f"Error committing to GitHub: {e}")
            return False
    
    def get_next_links(self, count):
        """Get next batch of links"""
        if not self.links:
            return []
        
        selected_links = []
        for i in range(count):
            if self.current_index >= len(self.links):
                self.current_index = 0
            
            selected_links.append(self.links[self.current_index])
            self.current_index += 1
        
        self.save_progress()
        return selected_links
    
    async def send_serpapi_enhanced_products(self, session_type):
        """Send products enhanced with SerpApi data"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        link_count = config['links']
        time_slot = config['time']
        
        logger.info(f"🚀 Starting SerpApi-enhanced {session_type} session: {time_slot} IST")
        logger.info(f"📊 Processing {link_count} links with SerpApi")
        
        links_to_process = self.get_next_links(link_count)
        if not links_to_process:
            logger.error("❌ No links available")
            return 0
        
        sent_count = 0
        website_products = []
        
        for i, original_link in enumerate(links_to_process, 1):
            try:
                logger.info(f"🔍 Processing product {i}/{link_count} with SerpApi")
                
                # Convert to affiliate link
                affiliate_link = self.convert_amazon_link(original_link)
                
                # Get comprehensive product data via SerpApi
                product_data = self.get_product_data_via_serpapi(original_link)
                
                # Create enhanced Telegram message
                telegram_message = f"""🔥 DEAL FAM ALERT! 🔥

📱 *{product_data['title']}*

💰 *Price:* {product_data['price']}
⭐ *Rating:* {product_data['rating']}
🏷 *Category:* {product_data['category'].title()}

🛒 *Get Deal:* {affiliate_link}

⏰ *Limited Time Offer - Grab Now!*

#DealFam #AmazonDeals #Shopping #{product_data['category'].title()}Deals #SerpApiPowered"""
                
                # Send to Telegram
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=telegram_message,
                    parse_mode='Markdown'
                )
                
                # Prepare for website with SerpApi data
                website_product = {
                    'id': f"serpapi_{session_type}{i}{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'title': product_data['title'],
                    'image': product_data['image'],
                    'affiliate_link': affiliate_link,
                    'price': product_data['price'],
                    'rating': product_data['rating'],
                    'category': product_data['category'],
                    'posted_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                    'session_type': session_type,
                    'asin': product_data['asin'],
                    'data_source': 'SerpApi'
                }
                
                website_products.append(website_product)
                
                # Log success
                ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                logger.info(f"✅ {session_type.upper()}: SerpApi product {i}/{link_count} at {ist_time}")
                logger.info(f"📝 Title: {product_data['title'][:60]}...")
                logger.info(f"💰 Price: {product_data['price']}")
                logger.info(f"📸 Image: {'✅' if product_data['image'] else '❌'}")
                
                sent_count += 1
                
                # Wait between API calls to respect rate limits
                if i < len(links_to_process):
                    await asyncio.sleep(random.uniform(2, 4))
                    
            except Exception as e:
                logger.error(f"❌ Error processing product {i}: {e}")
                continue
        
        # Update website with SerpApi-enhanced products
        if website_products:
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"🌐 Website updated with {len(website_products)} SerpApi products")
            else:
                logger.error("❌ Website update failed")
        
        # Final summary
        logger.info(f"🎉 {session_type.upper()} SERPAPI SESSION COMPLETE:")
        logger.info(f"   ✅ Telegram: {sent_count}/{link_count} enhanced posts")
        logger.info(f"   🌐 Website: {len(website_products)} products with reliable data")
        logger.info(f"   🔧 API Usage: {sent_count} SerpApi calls")
        
        return sent_count

# Main execution
async def main():
    logger.info("🚀 Starting SerpApi-Enhanced Amazon Bot...")
    
    required_vars = [BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG, SERPAPI_KEY_1]
    if not all(required_vars):
        logger.error("❌ Missing required environment variables")
        exit(1)
    
    bot = SerpApiAmazonBot()
    
    logger.info(f"📊 Total links: {len(bot.links)}")
    logger.info(f"📍 Current index: {bot.current_index}")
    logger.info(f"🔧 SerpApi keys loaded: {len(bot.serpapi_keys)}")
    logger.info(f"🎯 Target: SerpApi-enhanced Telegram + Website")
    
    try:
        sent_count = await bot.send_serpapi_enhanced_products(SESSION_TYPE)
        logger.info(f"🎉 SerpApi session completed! {sent_count} products with reliable data")
        
    except Exception as e:
        logger.error(f"❌ Error in SerpApi session: {e}")
        exit(1)

if _name_ == '_main_':
    asyncio.run(main())
