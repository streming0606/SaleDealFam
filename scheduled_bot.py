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

    async def get_real_product_info_serpapi(self, asin):
        """Get real product information using SerpApi - CORRECT METHOD"""
        if not SERP_API_KEY:
            logger.warning("No SerpApi key - using enhanced fallback")
            return self.get_enhanced_fallback_product_info(asin)
        
        try:
            logger.info(f"🔍 Fetching product data via SerpApi search for ASIN: {asin}")
            
            # Rate limiting check
            current_time = datetime.now()
            if (current_time - self.serp_start_time).seconds < 3600:
                if self.serp_request_count >= 240:
                    logger.warning("SerpApi rate limit approaching - using enhanced fallback")
                    return self.get_enhanced_fallback_product_info(asin)
            else:
                self.serp_request_count = 0
                self.serp_start_time = current_time
            
            # CORRECT METHOD: Search for the ASIN as a query term
            params = {
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'q': asin,  # Search for ASIN as query
                'api_key': SERP_API_KEY
            }
            
            logger.info(f"📡 Making SerpApi search request for ASIN: {asin}")
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=25)
            logger.info(f"📨 SerpApi response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"📊 SerpApi response keys: {list(data.keys())}")
                
                if 'error' in data:
                    logger.error(f"SerpApi error: {data['error']}")
                    return self.get_enhanced_fallback_product_info(asin)
                
                # Look for the product in organic_results
                organic_results = data.get('organic_results', [])
                logger.info(f"📋 Found {len(organic_results)} organic results")
                
                # Find the exact ASIN match
                target_product = None
                for result in organic_results:
                    result_asin = result.get('asin')
                    if result_asin == asin:
                        target_product = result
                        logger.info(f"✅ Found exact ASIN match: {asin}")
                        break
                
                # If no exact match, try to find ASIN in link
                if not target_product:
                    for result in organic_results:
                        link = result.get('link', '')
                        if f'/dp/{asin}' in link:
                            target_product = result
                            logger.info(f"✅ Found ASIN in product link")
                            break
                
                # If still no match, use first result if available
                if not target_product and organic_results:
                    target_product = organic_results[0]
                    logger.info(f"⚠️ Using first search result as fallback")
                
                if target_product:
                    # Extract product information
                    title = target_product.get('title', f'Amazon Product {asin}')
                    price = self.extract_price_from_result(target_product)
                    rating = self.extract_rating_from_result(target_product)
                    image = target_product.get('thumbnail', '')
                    
                    product_info = {
                        'asin': asin,
                        'title': title[:100] + '...' if len(title) > 100 else title,
                        'image': image,
                        'price': price,
                        'rating': rating,
                        'category': self.categorize_by_title(title),
                        'source': 'serpapi'
                    }
                    
                    self.serp_request_count += 1
                    
                    logger.info(f"✅ SerpApi product data extracted successfully!")
                    logger.info(f"   📝 Title: {title[:50]}...")
                    logger.info(f"   💰 Price: {price}")
                    logger.info(f"   ⭐ Rating: {rating}")
                    logger.info(f"   📊 API calls used: {self.serp_request_count}/250")
                    
                    return product_info
                else:
                    logger.warning(f"❌ No product found in search results for ASIN: {asin}")
                    
            else:
                logger.error(f"SerpApi HTTP error: {response.status_code}")
                logger.error(f"Response text: {response.text[:500]}...")
                
        except Exception as e:
            logger.error(f"❌ Exception in SerpApi call: {str(e)}")
            logger.error(f"📋 Full traceback: {traceback.format_exc()}")
        
        logger.warning(f"🔄 Using enhanced fallback for ASIN: {asin}")
        return self.get_enhanced_fallback_product_info(asin)
    
    def extract_price_from_result(self, result):
        """Extract price with multiple fallback methods"""
        try:
            # Method 1: Direct price field
            if 'price' in result and result['price']:
                price = result['price']
                if isinstance(price, str) and price.strip():
                    return price if '₹' in price else f"₹{price}"
            
            # Method 2: Look in title or snippet for price
            for text in [result.get('title', ''), result.get('snippet', '')]:
                price_patterns = [
                    r'₹[\d,]+',
                    r'Rs\.?\s*[\d,]+',
                    r'INR\s*[\d,]+'
                ]
                
                for pattern in price_patterns:
                    price_match = re.search(pattern, text, re.IGNORECASE)
                    if price_match:
                        price = price_match.group()
                        return price if '₹' in price else f"₹{price.replace('Rs', '').replace('INR', '').strip()}"
        
        except Exception as e:
            logger.error(f"Error extracting price: {e}")
        
        return "₹Special Price"
    
    def extract_rating_from_result(self, result):
        """Extract rating with multiple fallback methods"""
        try:
            # Method 1: Direct rating field
            if 'rating' in result and result['rating']:
                rating = result['rating']
                if isinstance(rating, (int, float)):
                    stars = min(int(rating), 5)
                    return "⭐" * stars + "☆" * (5-stars) if stars < 5 else "⭐" * 5
            
            # Method 2: Look for rating in title or snippet
            for text in [result.get('title', ''), result.get('snippet', '')]:
                rating_patterns = [
                    r'(\d+(?:\.\d+)?)\s*out of\s*5',
                    r'(\d+(?:\.\d+)?)\s*/\s*5',
                    r'(\d+(?:\.\d+)?)\s*stars?'
                ]
                
                for pattern in rating_patterns:
                    rating_match = re.search(pattern, text, re.IGNORECASE)
                    if rating_match:
                        rating_num = float(rating_match.group(1))
                        stars = min(int(rating_num), 5)
                        return "⭐" * stars + "☆" * (5-stars) if stars < 5 else "⭐" * 5
                        
        except Exception as e:
            logger.error(f"Error extracting rating: {e}")
        
        return "⭐⭐⭐⭐☆"
    
    def get_enhanced_fallback_product_info(self, asin):
        """Enhanced fallback with realistic product data"""
        
        # Realistic product categories and titles
        product_templates = {
            'electronics': [
                'Premium Electronics Deal - {asin}',
                'Latest Tech Gadget - {asin}',
                'Smart Device Special - {asin}',
                'Top Rated Electronics - {asin}'
            ],
            'fashion': [
                'Trendy Fashion Item - {asin}',
                'Premium Clothing Deal - {asin}',
                'Stylish Accessories - {asin}',
                'Fashion Forward Pick - {asin}'
            ],
            'home': [
                'Home Essential Deal - {asin}',
                'Kitchen Must-Have - {asin}',
                'Home Decor Special - {asin}',
                'Premium Home Product - {asin}'
            ]
        }
        
        # Realistic price ranges
        realistic_prices = [
            "₹299", "₹499", "₹699", "₹899", "₹1,199", 
            "₹1,499", "₹1,999", "₹2,499", "₹2,999", "₹3,499"
        ]
        
        # Realistic ratings
        realistic_ratings = [
            "⭐⭐⭐⭐⭐", "⭐⭐⭐⭐☆", "⭐⭐⭐⭐⭐", 
            "⭐⭐⭐⭐☆", "⭐⭐⭐⭐⭐"
        ]
        
        import random
        
        # Choose category based on ASIN pattern (if available)
        category = 'electronics'  # Default
        if asin and len(asin) >= 3:
            category_map = {'B0': 'electronics', 'B1': 'fashion', 'B2': 'home'}
            category = category_map.get(asin[:2], 'electronics')
        
        templates = product_templates.get(category, product_templates['electronics'])
        title = random.choice(templates).format(asin=asin or "SPECIAL")
        
        return {
            'asin': asin or "UNKNOWN",
            'title': title,
            'image': f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else "",
            'price': random.choice(realistic_prices),
            'rating': random.choice(realistic_ratings),
            'category': category,
            'source': 'enhanced_fallback'
        }
    
    def categorize_by_title(self, title):
        """Categorize product based on title"""
        title_lower = title.lower()
        
        categories = {
            'electronics': ['phone', 'smartphone', 'mobile', 'laptop', 'computer', 'tablet', 'earphone', 'headphone', 'charger', 'cable'],
            'fashion': ['shirt', 'tshirt', 'jeans', 'dress', 'shoes', 'watch', 'bag', 'clothing', 'cap', 'hat'],
            'home': ['kitchen', 'furniture', 'home', 'decor', 'appliance', 'bedsheet', 'pillow', 'curtain'],
            'health': ['skincare', 'beauty', 'cosmetic', 'health', 'supplement', 'medicine']
        }
        
        for category, keywords in categories.items():
            if any(keyword in title_lower for keyword in keywords):
                return category
                
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
                    chat_id=CHANNEL
