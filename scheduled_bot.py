#!/usr/bin/env python3
import logging
import re
import os
import json
import asyncio
import time
from datetime import datetime, timedelta
import pytz
import requests
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
import traceback

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
        logger.info(f"🔑 SerpApi key: {'Yes (***' + SERP_API_KEY[-4:] + ')' if SERP_API_KEY else 'No'}")
        
        # Test SerpApi connection on initialization
        if SERP_API_KEY:
            asyncio.create_task(self.test_serpapi_connection())
    
    async def test_serpapi_connection(self):
        """Test SerpApi connection and response"""
        try:
            logger.info("🧪 Testing SerpApi connection...")
            
            # Test with a known ASIN
            test_asin = "B08N5WRWNW"  # Popular electronics item
            
            params = {
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'asin': test_asin,
                'api_key': SERP_API_KEY
            }
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=20)
            
            logger.info(f"🧪 Test response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"🧪 Test response keys: {list(data.keys())}")
                
                if 'error' in data:
                    logger.error(f"🧪 SerpApi error: {data['error']}")
                    logger.error(f"🧪 Full error response: {json.dumps(data, indent=2)}")
                    return False
                else:
                    logger.info("✅ SerpApi connection test successful!")
                    
                    # Log sample data structure
                    if 'product_result' in data:
                        product = data['product_result']
                        logger.info(f"🧪 Sample product title: {product.get('title', 'No title')[:50]}...")
                        logger.info(f"🧪 Sample price: {product.get('price', 'No price')}")
                    
                    return True
            else:
                logger.error(f"🧪 Test failed with status: {response.status_code}")
                logger.error(f"🧪 Response text: {response.text[:500]}...")
                return False
                
        except Exception as e:
            logger.error(f"🧪 Test exception: {e}")
            logger.error(f"🧪 Full traceback: {traceback.format_exc()}")
            return False
        
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
        """Get current progress from GitHub repository"""
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
                    time.sleep(2 ** attempt)
        
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
    
    def extract_price_from_result(self, result):
        """Extract price with multiple fallback methods"""
        try:
            # Method 1: Direct price field
            if 'price' in result:
                price_data = result['price']
                if isinstance(price_data, str) and price_data.strip():
                    return price_data if '₹' in price_data else f"₹{price_data}"
                elif isinstance(price_data, dict):
                    current_price = price_data.get('current_price') or price_data.get('value')
                    if current_price:
                        return current_price if '₹' in str(current_price) else f"₹{current_price}"
            
            # Method 2: Check extracted field
            if 'extracted' in result:
                extracted = result['extracted']
                if 'price' in extracted:
                    return extracted['price']
            
            # Method 3: Look for price in snippet or title
            snippet = result.get('snippet', '')
            title = result.get('title', '')
            price_pattern = r'₹[\d,]+'
            
            for text in [snippet, title]:
                price_match = re.search(price_pattern, text)
                if price_match:
                    return price_match.group()
                    
        except Exception as e:
            logger.error(f"Error extracting price: {e}")
        
        return "₹Special Price"
    
    def extract_rating_from_result(self, result):
        """Extract rating with multiple fallback methods"""
        try:
            # Method 1: Direct rating field
            if 'rating' in result:
                rating_data = result['rating']
                if isinstance(rating_data, (int, float)):
                    stars = min(int(rating_data), 5)
                    return "⭐" * stars + "☆" * (5-stars)
                elif isinstance(rating_data, str):
                    rating_num = float(rating_data.split()[0])
                    stars = min(int(rating_num), 5)
                    return "⭐" * stars + "☆" * (5-stars)
            
            # Method 2: Look for rating in snippet
            snippet = result.get('snippet', '')
            rating_pattern = r'(\d+(?:\.\d+)?)\s*(?:out of|/)\s*5'
            rating_match = re.search(rating_pattern, snippet)
            
            if rating_match:
                rating_num = float(rating_match.group(1))
                stars = min(int(rating_num), 5)
                return "⭐" * stars + "☆" * (5-stars)
                
        except Exception as e:
            logger.error(f"Error extracting rating: {e}")
        
        return "⭐⭐⭐⭐☆"
    
    def extract_image_from_result(self, result, asin):
        """Extract image with multiple fallback methods"""
        try:
            # Method 1: Direct image fields
            for field in ['image', 'thumbnail', 'main_image']:
                if field in result:
                    image_data = result[field]
                    if isinstance(image_data, str) and image_data.startswith('http'):
                        return image_data
                    elif isinstance(image_data, dict) and 'link' in image_data:
                        return image_data['link']
            
            # Method 2: Images array
            if 'images' in result and result['images']:
                first_image = result['images'][0]
                if isinstance(first_image, str):
                    return first_image
                elif isinstance(first_image, dict) and 'link' in first_image:
                    return first_image['link']
                    
        except Exception as e:
            logger.error(f"Error extracting image: {e}")
        
        # Fallback: Amazon image URL pattern
        return f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else ""

    async def get_real_product_info_serpapi(self, asin):
        """Get real product information using SerpApi - ENHANCED VERSION"""
        if not SERP_API_KEY:
            logger.warning("No SerpApi key - using fallback product info")
            return self.get_fallback_product_info(asin)
        
        try:
            logger.info(f"🔍 Fetching real product data for ASIN: {asin}")
            
            # Rate limiting check
            current_time = datetime.now()
            if (current_time - self.serp_start_time).seconds < 3600:  # 1 hour window
                if self.serp_request_count >= 240:  # Leave buffer from 250 limit
                    logger.warning("SerpApi rate limit approaching - using fallback")
                    return self.get_fallback_product_info(asin)
            else:
                # Reset counter every hour
                self.serp_request_count = 0
                self.serp_start_time = current_time
            
            # Enhanced SerpApi parameters
            params = {
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'asin': asin,
                'api_key': SERP_API_KEY,
                'location': 'India',
                'hl': 'en',  # Language
                'gl': 'in'   # Country
            }
            
            logger.info(f"📡 Making SerpApi request for ASIN: {asin}")
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=25)
            
            logger.info(f"📨 SerpApi response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Log response structure for debugging
                logger.info(f"📊 SerpApi response keys: {list(data.keys())}")
                
                # Check for errors first
                if 'error' in data:
                    logger.error(f"SerpApi error: {data['error']}")
                    logger.error(f"Full error response: {json.dumps(data, indent=2)[:500]}...")
                    return self.get_fallback_product_info(asin)
                
                # Try multiple data extraction methods
                product_result = None
                
                # Method 1: Direct product_result
                if 'product_result' in data and data['product_result']:
                    product_result = data['product_result']
                    logger.info("✅ Found product_result")
                
                # Method 2: Check organic_results
                elif 'organic_results' in data and data['organic_results']:
                    for result in data['organic_results']:
                        if 'asin' in result or '/dp/' in result.get('link', ''):
                            product_result = result
                            logger.info("✅ Found product in organic_results")
                            break
                
                # Method 3: Check if there's any product data at root level
                elif any(key in data for key in ['title', 'price', 'images']):
                    product_result = data
                    logger.info("✅ Found product data at root level")
                
                if not product_result:
                    logger.warning(f"❌ No product result found for ASIN: {asin}")
                    logger.info(f"📋 Raw response (first 800 chars): {json.dumps(data, indent=2)[:800]}...")
                    return self.get_fallback_product_info(asin)
                
                # Extract product information with enhanced error handling
                title = (product_result.get('title') or 
                        product_result.get('name') or 
                        f'Amazon Product {asin}')
                
                # Enhanced data extraction
                price = self.extract_price_from_result(product_result)
                rating = self.extract_rating_from_result(product_result)
                image = self.extract_image_from_result(product_result, asin)
                
                product_info = {
                    'asin': asin,
                    'title': title[:100] + '...' if len(title) > 100 else title,
                    'image': image,
                    'price': price,
                    'rating': rating,
                    'category': self.categorize_by_title(title),
                    'source': 'serpapi'
                }
                
                # Increment request counter
                self.serp_request_count += 1
                
                logger.info(f"✅ Real product data fetched successfully!")
                logger.info(f"   📝 Title: {title[:50]}...")
                logger.info(f"   💰 Price: {price}")
                logger.info(f"   ⭐ Rating: {rating}")
                logger.info(f"   🖼️ Image: {'Yes' if image else 'No'}")
                logger.info(f"   📊 Requests used: {self.serp_request_count}/250")
                
                return product_info
                    
            else:
                logger.error(f"SerpApi HTTP error: {response.status_code}")
                logger.error(f"Response text: {response.text[:500]}...")
                
        except Exception as e:
            logger.error(f"❌ Exception in SerpApi call: {str(e)}")
            logger.error(f"📋 Full traceback: {traceback.format_exc()}")
        
        logger.warning(f"🔄 Falling back to default product info for ASIN: {asin}")
        return self.get_fallback_product_info(asin)
    
    def get_fallback_product_info(self, asin):
        """Enhanced fallback product info"""
        fallback_titles = [
            f"Premium Electronics Deal - {asin}",
            f"Top Rated Product - {asin}",
            f"Trending Amazon Deal - {asin}",
            f"Best Seller Product - {asin}",
            f"Featured Deal - {asin}"
        ]
        
        import random
        title = random.choice(fallback_titles) if asin else "Special Amazon Deal"
        
        return {
            'asin': asin or "UNKNOWN",
            'title': title,
            'image': f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else "",
            'price': "₹Special Price",
            'rating': "⭐⭐⭐⭐☆",
            'category': "electronics",
            'source': 'fallback'
        }
    
    def categorize_by_title(self, title):
        """Categorize product based on title"""
        title_lower = title.lower()
        
        categories = {
            'electronics': ['phone', 'smartphone', 'mobile', 'laptop', 'computer', 'tablet', 'earphone', 'headphone'],
            'fashion': ['shirt', 'tshirt', 'jeans', 'dress', 'shoes', 'watch', 'bag', 'clothing'],
            'home': ['kitchen', 'furniture', 'home', 'decor', 'appliance', 'bedsheet', 'pillow'],
            'health': ['skincare', 'beauty', 'cosmetic', 'health', 'supplement', 'medicine']
        }
        
        for category, keywords in categories.items():
            if any(keyword in title_lower for keyword in keywords):
                return category
                
        return 'electronics'  # Default category
    
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
        
        # Save progress after getting links
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

👍 Deal Fam Rating: ⭐⭐⭐⭐⭐
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
                
                logger.info(f"🔍 Processing website product {i}/{website_count} - ASIN: {asin}")
                
                # Get product information using enhanced SerpApi
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
                
                logger.info(f"✅ Website product {i}/{website_count} processed successfully")
                logger.info(f"   📝 Title: {product_info['title'][:50]}...")
                logger.info(f"   💰 Price: {product_info['price']}")
                logger.info(f"   📊 Source: {product_info.get('source', 'unknown')}")
                
                # Small delay between product processing
                if i < len(website_links):
                    await asyncio.sleep(3)
                    
            except Exception as e:
                logger.error(f"❌ Error processing website product {i}: {e}")
                logger.error(f"📋 Full error: {traceback.format_exc()}")
        
        # Update website
        if website_products:
            logger.info(f"🌐 Updating website with {len(website_products)} products...")
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"✅ Website successfully updated!")
            else:
                logger.error("❌ Website update failed")
        else:
            logger.warning("⚠️ No products to update on website")
        
        # Final summary
        total_links = len(self.links) if self.links else 0
        cycle_number = (self.current_index // total_links) if total_links > 0 else 1
        remaining_in_cycle = total_links - (self.current_index % total_links) if total_links > 0 else 0
        
        logger.info(f"")
        logger.info(f"🎉 {session_type.upper()} SESSION COMPLETE! 🎉")
        logger.info(f"   📱 Telegram: {sent_count}/{telegram_count} links posted")
        logger.info(f"   🌐 Website: {len(website_products)}/{website_count} products updated")
        logger.info(f"   📍 Progress: {self.current_index}/{total_links}")
        logger.info(f"   🔄 Cycle: {cycle_number}, Remaining: {remaining_in_cycle}")
        logger.info(f"   🔑 SerpApi requests used: {self.serp_request_count}/250")
        logger.info(f"")
        
        return sent_count

# Main execution function
async def main():
    """Main function for scheduled execution"""
    logger.info("🚀 Starting Enhanced Telegram + Website Bot with SerpApi...")
    logger.info(f"📅 Session Type: {SESSION_TYPE.upper()}")
    logger.info(f"🕐 IST Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %I:%M:%S %p')}")
    
    # Validate required environment variables
    required_vars = {
        'BOT_TOKEN': BOT_TOKEN,
        'CHANNEL_ID': CHANNEL_ID,
        'AMAZON_TAG': AMAZON_AFFILIATE_TAG,
        'GITHUB_TOKEN': GITHUB_TOKEN
    }
    
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)
    
    if not SERP_API_KEY:
        logger.warning("⚠️ No SerpApi key found - will use enhanced fallback product data")
    else:
        logger.info(f"✅ SerpApi key configured: ***{SERP_API_KEY[-4:]}")
    
    # Initialize bot
    bot_instance = EnhancedAffiliateBot()
    
    logger.info(f"📊 Configuration Summary:")
    logger.info(f"   📱 Total links loaded: {len(bot_instance.links)}")
    logger.info(f"   📍 Starting from index: {bot_instance.current_index}")
    logger.info(f"   🎯 Target channel: {CHANNEL_ID}")
    logger.info(f"   🌐 Target website: {WEBSITE_REPO}")
    logger.info(f"   🏷️ Affiliate tag: {AMAZON_AFFILIATE_TAG}")
    
    try:
        # Execute the session
        sent_count = await bot_instance.send_scheduled_links(SESSION_TYPE)
        
        logger.info(f"")
        logger.info(f"🏆 MISSION ACCOMPLISHED! 🏆")
        logger.info(f"Session '{SESSION_TYPE}' completed successfully!")
        logger.info(f"Telegram posts: {sent_count}, Website: Updated")
        logger.info(f"")
        
    except Exception as e:
        logger.error(f"❌ Critical error in session: {e}")
        logger.error(f"📋 Full traceback: {traceback.format_exc()}")
        exit(1)

if __name__ == '__main__':
    asyncio.run(main())
