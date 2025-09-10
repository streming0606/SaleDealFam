#!/usr/bin/env python3
import logging
import re
import os
import json
import asyncio
from datetime import datetime, timedelta
import pytz
import requests
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

# Set up logging with more detailed format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log') if os.path.exists('.') else logging.StreamHandler()
    ]
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

# 🔄 Enhanced session configuration with detailed timing
SESSION_CONFIG = {
    'morning': {
        'telegram_links': 3, 
        'website_links': 2, 
        'time': '10:12-10:20 AM',
        'delay_between_posts': 60,  # 1 minute between posts
        'priority': 'high'
    },
    'afternoon': {
        'telegram_links': 3, 
        'website_links': 2, 
        'time': '1:12-1:20 PM',
        'delay_between_posts': 60,
        'priority': 'high'
    },
    'evening': {
        'telegram_links': 2, 
        'website_links': 1, 
        'time': '6:12-6:20 PM',
        'delay_between_posts': 90,  # Slightly longer delay
        'priority': 'medium'
    },
    'night': {
        'telegram_links': 2, 
        'website_links': 1, 
        'time': '9:12-9:20 PM',
        'delay_between_posts': 120,  # Longer delay for night
        'priority': 'medium'
    }
}

class EnhancedAffiliateBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        self.serp_request_count = 0
        self.serp_start_time = datetime.now()
        self.session_stats = {
            'telegram_sent': 0,
            'website_updated': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }
        
        logger.info(f"🚀 Enhanced Affiliate Bot Initialized")
        logger.info(f"📊 Loaded {len(self.links)} total links")
        logger.info(f"📍 Starting from index: {self.current_index}")
        logger.info(f"🔑 SerpApi available: {'Yes' if SERP_API_KEY else 'No'}")
        logger.info(f"🌐 Target repository: {WEBSITE_REPO}")
        
    def load_amazon_links(self):
        """Load Amazon links from file with enhanced validation"""
        try:
            os.makedirs('data', exist_ok=True)
            
            if os.path.exists('data/amazon_links.json'):
                with open('data/amazon_links.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    links = data.get('links', [])
                    
                    # Validate links
                    valid_links = []
                    for link in links:
                        if self.is_valid_amazon_link(link):
                            valid_links.append(link)
                        else:
                            logger.warning(f"⚠️ Invalid link skipped: {link[:50]}...")
                    
                    logger.info(f"✅ Loaded {len(valid_links)} valid links from {len(links)} total")
                    return valid_links
                    
        except Exception as e:
            logger.error(f"❌ Error loading links: {e}")
        
        logger.warning("⚠️ No links loaded - returning empty list")
        return []
    
    def is_valid_amazon_link(self, link):
        """Validate if link is a proper Amazon link"""
        if not link or not isinstance(link, str):
            return False
        
        amazon_patterns = [
            r'amazon\.in',
            r'amazon\.com',
            r'amzn\.to',
            r'/dp/',
            r'/gp/product/'
        ]
        
        return any(re.search(pattern, link, re.IGNORECASE) for pattern in amazon_patterns)
    
    def load_progress(self):
        """Load current progress with enhanced fallback logic"""
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
        """Get current progress from GitHub repository with retry logic"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if not GITHUB_TOKEN:
                    return None
                    
                url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/progress.json"
                headers = {
                    'Authorization': f'token {GITHUB_TOKEN}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'Enhanced-Affiliate-Bot/1.0'
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
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return None
    
    def save_progress(self):
        """Enhanced progress saving with detailed metadata"""
        try:
            os.makedirs('data', exist_ok=True)
            
            if not self.links:
                cycle_number, position_in_cycle = 1, 1
                completion_percentage = 0
            else:
                total_links = len(self.links)
                cycle_number = (self.current_index // total_links) + 1
                position_in_cycle = (self.current_index % total_links) + 1
                completion_percentage = round((position_in_cycle / total_links) * 100, 2)
                
                if self.current_index > 0 and self.current_index % total_links == 0:
                    cycle_number = (self.current_index // total_links)
                    position_in_cycle = total_links
                    completion_percentage = 100.0
            
            ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
            
            progress_data = {
                'current_index': self.current_index,
                'cycle_number': cycle_number,
                'position_in_cycle': position_in_cycle,
                'completion_percentage': completion_percentage,
                'total_links': len(self.links),
                'last_updated': ist_now.isoformat(),
                'session_type': SESSION_TYPE,
                'session_stats': self.session_stats,
                'next_reset_date': (ist_now + timedelta(days=1)).strftime('%Y-%m-%d'),
                'bot_version': '2.0.0'
            }
            
            # Save locally
            with open('data/progress.json', 'w') as f:
                json.dump(progress_data, f, indent=2)
            
            # Save to GitHub asynchronously
            asyncio.create_task(self.update_progress_on_github(progress_data))
            
            logger.info(f"💾 Progress saved: Index {self.current_index}, Cycle {cycle_number}, Position {position_in_cycle}/{len(self.links)} ({completion_percentage}%)")
                
        except Exception as e:
            logger.error(f"❌ Error saving progress: {e}")
    
    async def update_progress_on_github(self, progress_data):
        """Update progress file on GitHub with enhanced error handling"""
        try:
            if not GITHUB_TOKEN:
                logger.warning("No GitHub token - skipping GitHub progress update")
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
        """Enhanced Amazon link conversion with multiple patterns"""
        try:
            # Remove existing affiliate tags
            url = re.sub(r'[?&]tag=[^&]*', '', url)
            url = re.sub(r'[?&]ref=[^&]*', '', url)
            
            # Extract ASIN and create clean link
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
            if asin_match:
                asin = asin_match.group(1)
                return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
            
            # Handle gp/product URLs
            product_match = re.search(r'/gp/product/([A-Z0-9]{10})', url)
            if product_match:
                asin = product_match.group(1)
                return f"https://www.amazon.in/dp/{asin}?tag={AMAZON_AFFILIATE_TAG}"
            
            # Handle short links (amzn.to)
            if 'amzn.to' in url:
                try:
                    response = requests.head(url, allow_redirects=True, timeout=10)
                    resolved_url = response.url
                    return self.convert_amazon_link(resolved_url)
                except:
                    pass
            
            # Fallback: append tag
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}tag={AMAZON_AFFILIATE_TAG}"
            
        except Exception as e:
            logger.error(f"❌ Error converting link: {e}")
            return url
    
    def extract_asin_from_url(self, amazon_url):
        """Enhanced ASIN extraction with multiple patterns"""
        try:
            patterns = [
                r'/dp/([A-Z0-9]{10})',
                r'/gp/product/([A-Z0-9]{10})',
                r'asin=([A-Z0-9]{10})',
                r'/product/([A-Z0-9]{10})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, amazon_url)
                if match:
                    return match.group(1)
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error extracting ASIN: {e}")
            return None
    
    async def check_serp_api_limits(self):
        """Check SerpApi rate limits"""
        current_time = datetime.now()
        
        # Reset counter monthly
        if (current_time - self.serp_start_time).days >= 30:
            self.serp_request_count = 0
            self.serp_start_time = current_time
            logger.info("🔄 SerpApi counter reset for new month")
        
        # Check daily limits (assuming 100/month = ~3/day safe limit)
        daily_limit = 5
        requests_today = self.serp_request_count
        
        if requests_today >= daily_limit:
            logger.warning(f"⚠️ SerpApi daily limit reached ({requests_today}/{daily_limit})")
            return False
        
        return True
    
    async def get_real_product_info_serpapi(self, asin):
        """Enhanced SerpApi integration with comprehensive error handling"""
        if not SERP_API_KEY:
            logger.warning("No SerpApi key - using fallback product info")
            return self.get_fallback_product_info(asin)
        
        # Check rate limits
        if not await self.check_serp_api_limits():
            logger.warning("SerpApi rate limit reached - using fallback")
            return self.get_fallback_product_info(asin)
        
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔍 Fetching real product data for ASIN: {asin} (attempt {attempt + 1})")
                
                params = {
                    'engine': 'amazon',
                    'amazon_domain': 'amazon.in',
                    'asin': asin,
                    'api_key': SERP_API_KEY,
                    'include_html': False
                }
                
                response = requests.get(
                    'https://serpapi.com/search', 
                    params=params, 
                    timeout=20,
                    headers={'User-Agent': 'Enhanced-Affiliate-Bot/2.0'}
                )
                
                response.raise_for_status()
                self.serp_request_count += 1
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check for API errors
                    if 'error' in data:
                        logger.error(f"SerpApi error: {data['error']}")
                        return self.get_fallback_product_info(asin)
                    
                    product_result = data.get('product_result', {})
                    
                    if not product_result:
                        logger.warning(f"No product result for ASIN: {asin}")
                        return self.get_fallback_product_info(asin)
                    
                    # Extract enhanced product information
                    title = product_result.get('title', f'Amazon Product {asin}')
                    price = self.format_price(product_result.get('price'))
                    rating = self.format_rating(product_result.get('rating'))
                    
                    # Get the best available image
                    image = self.get_best_product_image(product_result)
                    
                    # Extract additional metadata
                    availability = product_result.get('availability', {})
                    stock_status = availability.get('in_stock', True)
                    
                    product_info = {
                        'asin': asin,
                        'title': self.clean_title(title),
                        'image': image,
                        'price': price,
                        'rating': rating,
                        'category': self.categorize_by_title(title),
                        'in_stock': stock_status,
                        'source': 'serpapi',
                        'fetched_at': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
                    }
                    
                    logger.info(f"✅ Real product data fetched: {title[:50]}...")
                    logger.info(f"   💰 Price: {price}")
                    logger.info(f"   ⭐ Rating: {rating}")
                    logger.info(f"   📦 In Stock: {stock_status}")
                    logger.info(f"   🖼️ Image: {'Available' if image else 'Not available'}")
                    
                    return product_info
                
            except requests.RequestException as e:
                logger.error(f"SerpApi request error (attempt {attempt + 1}): {e}")
            except json.JSONDecodeError as e:
                logger.error(f"SerpApi JSON decode error (attempt {attempt + 1}): {e}")
            except Exception as e:
                logger.error(f"Unexpected SerpApi error (attempt {attempt + 1}): {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(3 * (attempt + 1))  # Progressive delay
        
        logger.warning(f"All SerpApi attempts failed for ASIN: {asin} - using fallback")
        return self.get_fallback_product_info(asin)
    
    def get_best_product_image(self, product_result):
        """Get the best available product image"""
        # Try main image first
        main_image = product_result.get('main_image', {})
        if main_image and main_image.get('link'):
            return main_image['link']
        
        # Try images array
        images = product_result.get('images', [])
        if images and len(images) > 0:
            return images[0].get('link', '')
        
        # Try image from other fields
        if product_result.get('image'):
            return product_result['image']
        
        return ''
    
    def clean_title(self, title):
        """Clean and optimize product title"""
        if len(title) > 100:
            # Find a good breaking point
            if ' - ' in title:
                title = title.split(' - ')[0]
            elif ', ' in title and len(title.split(', ')[0]) > 50:
                title = title.split(', ')[0]
            else:
                title = title[:97] + '...'
        
        # Remove excessive punctuation and clean up
        title = re.sub(r'[^\w\s\-\(\),.]', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        
        return title
    
    def format_price(self, price_data):
        """Enhanced price formatting"""
        if not price_data:
            return "₹Special Price"
        
        try:
            if isinstance(price_data, str):
                # Extract number from string
                price_match = re.search(r'[\d,]+(?:\.\d{2})?', price_data.replace('₹', ''))
                if price_match:
                    return f"₹{price_match.group(0)}"
                return price_data if '₹' in price_data else f"₹{price_data}"
                
            elif isinstance(price_data, dict):
                current_price = price_data.get('current_price') or price_data.get('price')
                if current_price:
                    return current_price if '₹' in str(current_price) else f"₹{current_price}"
            
            elif isinstance(price_data, (int, float)):
                return f"₹{price_data:,.2f}"
            
        except Exception as e:
            logger.error(f"Error formatting price: {e}")
        
        return "₹Special Offer"
    
    def format_rating(self, rating_data):
        """Enhanced rating formatting with half stars"""
        if not rating_data:
            return "⭐⭐⭐⭐⭐"
        
        try:
            if isinstance(rating_data, (int, float)):
                rating_num = float(rating_data)
            elif isinstance(rating_data, str):
                rating_num = float(rating_data.split()[0])
            elif isinstance(rating_data, dict):
                rating_num = float(rating_data.get('rating', 4.0))
            else:
                return "⭐⭐⭐⭐⭐"
            
            # Convert to 5-star scale if needed
            if rating_num > 5:
                rating_num = rating_num / 2
            
            full_stars = int(rating_num)
            has_half = (rating_num - full_stars) >= 0.5
            
            stars = "⭐" * full_stars
            if has_half and full_stars < 5:
                stars += "⭐"  # Using full star for half (can use ✨ if preferred)
                full_stars += 1
            
            empty_stars = "☆" * max(0, 5 - full_stars)
            
            return stars + empty_stars
            
        except Exception as e:
            logger.error(f"Error formatting rating: {e}")
            return "⭐⭐⭐⭐⭐"
    
    def get_fallback_product_info(self, asin):
        """Enhanced fallback product info with better defaults"""
        fallback_titles = [
            "Premium Amazon Product",
            "Top Rated Item",
            "Customer Favorite",
            "Best Seller Product",
            "Amazon Choice Item"
        ]
        
        import hashlib
        title_index = int(hashlib.md5(str(asin).encode()).hexdigest(), 16) % len(fallback_titles)
        
        return {
            'asin': asin or 'UNKNOWN',
            'title': f"{fallback_titles[title_index]} {asin}" if asin else fallback_titles[title_index],
            'image': f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else "",
            'price': "₹Special Price",
            'rating': "⭐⭐⭐⭐⭐",
            'category': "electronics",
            'in_stock': True,
            'source': 'fallback',
            'fetched_at': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
        }
    
    def categorize_by_title(self, title):
        """Enhanced product categorization"""
        title_lower = title.lower()
        
        categories = {
            'electronics': ['phone', 'smartphone', 'mobile', 'iphone', 'samsung', 'oneplus', 'laptop', 
                          'computer', 'macbook', 'dell', 'hp', 'lenovo', 'tablet', 'earphones', 
                          'headphones', 'speaker', 'charger', 'cable', 'mouse', 'keyboard'],
            'fashion': ['shirt', 'tshirt', 't-shirt', 'jeans', 'dress', 'shoes', 'sneakers', 
                       'clothing', 'apparel', 'fashion', 'wear', 'jacket', 'sweater'],
            'home': ['kitchen', 'cookware', 'furniture', 'home decor', 'bedsheet', 'pillow', 
                    'curtain', 'lamp', 'table', 'chair', 'storage'],
            'health': ['skincare', 'shampoo', 'cream', 'beauty', 'cosmetic', 'supplement', 
                      'vitamin', 'healthcare', 'medical'],
            'sports': ['fitness', 'gym', 'yoga', 'sports', 'exercise', 'workout', 'running'],
            'automotive': ['car', 'bike', 'automotive', 'vehicle', 'motorcycle', 'scooter'],
            'books': ['book', 'novel', 'kindle', 'ebook', 'textbook', 'guide'],
            'toys': ['toy', 'game', 'kids', 'children', 'baby', 'doll', 'puzzle']
        }
        
        for category, keywords in categories.items():
            if any(keyword in title_lower for keyword in keywords):
                return category
        
        return 'electronics'  # Default category
    
    async def update_website_products(self, new_products):
        """Enhanced website update with better error handling"""
        try:
            if not GITHUB_TOKEN:
                logger.warning("No GitHub token provided - skipping website update")
                return False
            
            logger.info("🌐 Updating website with new products...")
            
            # Get existing products
            website_products = await self.get_website_products()
            
            # Add new products to the beginning
            for product in reversed(new_products):
                website_products.insert(0, product)
            
            # Keep only latest 100 products for better performance
            website_products = website_products[:100]
            
            ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
            
            updated_data = {
                "last_updated": ist_now.isoformat(),
                "total_products": len(website_products),
                "daily_target": 6,
                "session_type": SESSION_TYPE,
                "update_count": len(new_products),
                "bot_version": "2.0.0",
                "products": website_products
            }
            
            success = await self.commit_to_github(
                'data/products.json', 
                json.dumps(updated_data, indent=2)
            )
            
            if success:
                logger.info(f"✅ Website updated with {len(new_products)} new products")
                logger.info(f"📊 Total products on website: {len(website_products)}")
                self.session_stats['website_updated'] = len(new_products)
                return True
            else:
                logger.error("❌ Failed to update website")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error updating website: {e}")
            self.session_stats['errors'] += 1
            return False
    
    async def get_website_products(self):
        """Get existing products from website repository with retry logic"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/products.json"
                headers = {
                    'Authorization': f'token {GITHUB_TOKEN}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'Enhanced-Affiliate-Bot/2.0'
                }
                
                response = requests.get(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    file_content = response.json()
                    import base64
                    content = base64.b64decode(file_content['content']).decode('utf-8')
                    data = json.loads(content)
                    return data.get('products', [])
                elif response.status_code == 404:
                    logger.info("No existing products file found - creating new one")
                    return []
                else:
                    logger.warning(f"GitHub API returned {response.status_code}: {response.text}")
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Error getting website products: {e}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        logger.warning("All attempts to get website products failed - returning empty list")
        return []
    
    async def commit_to_github(self, file_path, content):
        """Enhanced GitHub commit with retry logic"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/{file_path}"
                headers = {
                    'Authorization': f'token {GITHUB_TOKEN}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'Enhanced-Affiliate-Bot/2.0'
                }
                
                # Get current file SHA if exists
                response = requests.get(url, headers=headers, timeout=15)
                sha = None
                if response.status_code == 200:
                    sha = response.json()['sha']
                
                # Encode content
                import base64
                encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                
                # Prepare commit data
                commit_message = f'Auto-update: {SESSION_TYPE} session - {datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")}'
                
                commit_data = {
                    'message': commit_message,
                    'content': encoded_content,
                    'branch': 'main'
                }
                
                if sha:
                    commit_data['sha'] = sha
                
                # Make commit
                response = requests.put(url, headers=headers, json=commit_data, timeout=30)
                
                if response.status_code in [200, 201]:
                    logger.info(f"✅ Successfully committed {file_path}")
                    return True
                else:
                    logger.error(f"GitHub commit failed: {response.status_code} - {response.text}")
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Error committing to GitHub: {e}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        logger.error(f"All GitHub commit attempts failed for {file_path}")
        return False
    
    def get_next_links(self, count, purpose="general"):
        """Enhanced link selection with validation"""
        if not self.links:
            logger.warning("⚠️ No links available for scheduling")
            return []
        
        selected_links = []
        starting_index = self.current_index
        
        logger.info(f"📋 Getting {count} links for {purpose} starting from index {self.current_index}")
        
        attempts = 0
        max_attempts = len(self.links) * 2  # Prevent infinite loop
        
        while len(selected_links) < count and attempts < max_attempts:
            if self.current_index >= len(self.links):
                self.current_index = 0
                logger.info(f"🔄 Cycle completed! Wrapping around to index 0")
            
            current_link = self.links[self.current_index]
            
            # Validate link before adding
            if self.is_valid_amazon_link(current_link):
                selected_links.append(current_link)
                logger.info(f"   📎 Link {len(selected_links)}/{count}: Index {self.current_index} - {current_link[:50]}...")
            else:
                logger.warning(f"   ⚠️ Skipping invalid link at index {self.current_index}")
            
            self.current_index += 1
            attempts += 1
        
        # Save progress after link selection
        if purpose == "website":  # Save after website selection
            self.save_progress()
        
        logger.info(f"✅ Selected {len(selected_links)} valid links for {purpose}. Next index: {self.current_index}")
        return selected_links
    
    async def send_to_telegram_with_retry(self, message, chat_id, max_retries=3):
        """Send message to Telegram with retry logic"""
        for attempt in range(max_retries):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                return True
                
            except TelegramError as e:
                logger.error(f"Telegram error (attempt {attempt + 1}): {e}")
                
                if "retry after" in str(e).lower():
                    # Rate limit - wait and retry
                    wait_time = 60 + (attempt * 30)
                    logger.info(f"Rate limited - waiting {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                elif attempt < max_retries - 1:
                    await asyncio.sleep(5 * (attempt + 1))
                else:
                    self.session_stats['errors'] += 1
                    return False
                    
            except Exception as e:
                logger.error(f"Unexpected error sending to Telegram (attempt {attempt + 1}): {e}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(3 * (attempt + 1))
                else:
                    self.session_stats['errors'] += 1
                    return False
        
        return False
    
    async def send_scheduled_links(self, session_type):
        """🚀 Enhanced main function with comprehensive logging and error handling"""
        self.session_stats['start_time'] = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        telegram_count = config['telegram_links']
        website_count = config['website_links']
        time_slot = config['time']
        delay_between_posts = config['delay_between_posts']
        
        logger.info(f"🚀 STARTING {session_type.upper()} SESSION")
        logger.info(f"🕐 Time Slot: {time_slot} IST")
        logger.info(f"📱 Telegram posts: {telegram_count}")
        logger.info(f"🌐 Website posts: {website_count}")
        logger.info(f"⏱️ Delay between posts: {delay_between_posts}s")
        logger.info(f"📍 Starting from index: {self.current_index}")
        logger.info(f"📊 Total available links: {len(self.links)}")
        
        if not self.links:
            logger.error("❌ No links available to process")
            return 0
        
        # Get links for both platforms
        telegram_links = self.get_next_links(telegram_count, "telegram")
        website_links = self.get_next_links(website_count, "website")
        
        if not telegram_links and not website_links:
            logger.error("❌ No valid links obtained")
            return 0
        
        sent_count = 0
        website_products = []
        
        # 📱 TELEGRAM POSTING
        logger.info("📱 TELEGRAM POSTING PHASE")
        logger.info("=" * 50)
        
        for i, original_link in enumerate(telegram_links, 1):
            try:
                converted_link = self.convert_amazon_link(original_link)
                
                # Enhanced Telegram message
                channel_message = f"""🔥 **DEAL FAM SPECIAL!** 🔥

🛒 **Amazon Hot Deal:** {converted_link}

⭐ **Deal Fam Rating:** ⭐⭐⭐⭐⭐
💰 **Grab this amazing offer now!**
⏰ **Limited Time:** Only 6 hours left!
🚀 **Fast Delivery Available**

#{session_type.title()}Deals #AmazonDeals #FlipkartOffers #ShoppingDeals #IndianDeals #SaveMoney #DailyDeals #DealFam"""
                
                success = await self.send_to_telegram_with_retry(channel_message, CHANNEL_ID)
                
                if success:
                    ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                    logger.info(f"✅ Telegram {i}/{telegram_count} sent successfully at {ist_time} IST")
                    sent_count += 1
                    self.session_stats['telegram_sent'] += 1
                else:
                    logger.error(f"❌ Failed to send Telegram message {i}/{telegram_count}")
                
                # Delay between posts (except last one)
                if i < len(telegram_links):
                    logger.info(f"⏱️ Waiting {delay_between_posts}s before next post...")
                    await asyncio.sleep(delay_between_posts)
                    
            except Exception as e:
                logger.error(f"❌ Error processing Telegram link {i}: {e}")
                self.session_stats['errors'] += 1
        
        # 🌐 WEBSITE PRODUCT PROCESSING
        logger.info("🌐 WEBSITE PRODUCT PROCESSING PHASE")
        logger.info("=" * 50)
        
        for i, original_link in enumerate(website_links, 1):
            try:
                converted_link = self.convert_amazon_link(original_link)
                asin = self.extract_asin_from_url(original_link)
                
                logger.info(f"🔍 Processing website product {i}/{website_count} (ASIN: {asin})")
                
                # Get real product information
                product_info = await self.get_real_product_info_serpapi(asin)
                
                # Create enhanced website product
                ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
                
                website_product = {
                    'id': f"product_{session_type}_{i}_{ist_now.strftime('%Y%m%d_%H%M%S')}",
                    'title': product_info['title'],
                    'image': product_info['image'],
                    'affiliate_link': converted_link,
                    'original_link': original_link,
                    'price': product_info['price'],
                    'rating': product_info['rating'],
                    'category': product_info['category'],
                    'asin': product_info['asin'],
                    'in_stock': product_info.get('in_stock', True),
                    'data_source': product_info.get('source', 'unknown'),
                    'posted_date': ist_now.isoformat(),
                    'session_type': session_type,
                    'link_index': self.current_index - website_count + i - 1,
                    'fetched_at': product_info.get('fetched_at', ist_now.isoformat())
                }
                
                website_products.append(website_product)
                
                logger.info(f"✅ Website product {i}/{website_count} processed successfully")
                logger.info(f"   📋 Title: {product_info['title'][:60]}...")
                logger.info(f"   💰 Price: {product_info['price']}")
                logger.info(f"   ⭐ Rating: {product_info['rating']}")
                logger.info(f"   📦 In Stock: {product_info.get('in_stock', True)}")
                logger.info(f"   🖼️ Image: {'Available' if product_info['image'] else 'No image'}")
                logger.info(f"   🔧 Source: {product_info.get('source', 'unknown')}")
                
                # Rate limiting between SerpApi calls
                if i < len(website_links):
                    await asyncio.sleep(3)
                    
            except Exception as e:
                logger.error(f"❌ Error processing website product {i}: {e}")
                self.session_stats['errors'] += 1
        
        # 🌐 WEBSITE UPDATE
        logger.info("🌐 WEBSITE UPDATE PHASE")
        logger.info("=" * 50)
        
        if website_products:
            website_success = await self.update_website_products(website_products)
            
            if website_success:
                logger.info(f"✅ Website successfully updated with {len(website_products)} enhanced products")
            else:
                logger.error("❌ Website update failed")
                self.session_stats['errors'] += 1
        else:
            logger.warning("⚠️ No website products to update")
        
        # 📊 FINAL SESSION SUMMARY
        self.session_stats['end_time'] = datetime.now(pytz.timezone('Asia/Kolkata'))
        session_duration = (self.session_stats['end_time'] - self.session_stats['start_time']).total_seconds()
        
        total_links = len(self.links) if self.links else 0
        cycle_number = (self.current_index // total_links) if total_links > 0 else 1
        remaining_in_cycle = total_links - (self.current_index % total_links) if total_links > 0 else 0
        completion_percentage = round((self.current_index % total_links) / total_links * 100, 1) if total_links > 0 else 0
        
        logger.info("=" * 70)
        logger.info(f"🎉 {session_type.upper()} SESSION COMPLETED!")
        logger.info("=" * 70)
        logger.info(f"📱 Telegram Results: {self.session_stats['telegram_sent']}/{telegram_count} links posted")
        logger.info(f"🌐 Website Results: {len(website_products)} products with enhanced data")
        logger.info(f"⚠️ Errors Encountered: {self.session_stats['errors']}")
        logger.info(f"⏱️ Session Duration: {session_duration:.1f} seconds")
        logger.info(f"📍 Progress: Index {self.current_index}/{total_links}")
        logger.info(f"🔄 Cycle: {cycle_number}, Remaining: {remaining_in_cycle}")
        logger.info(f"📊 Completion: {completion_percentage}% of current cycle")
        logger.info(f"🕐 Completed at: {self.session_stats['end_time'].strftime('%I:%M:%S %p IST')}")
        logger.info("=" * 70)
        
        return self.session_stats['telegram_sent']

# 🚀 MAIN EXECUTION FUNCTION
async def main():
    """Enhanced main function with comprehensive startup checks"""
    logger.info("🚀 STARTING ENHANCED TELEGRAM + WEBSITE BOT v2.0")
    logger.info("=" * 70)
    logger.info(f"📅 Session Type: {SESSION_TYPE.upper()}")
    logger.info(f"🕐 Current IST Time: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %I:%M:%S %p')}")
    
    # Environment validation
    required_vars = {
        'BOT_TOKEN': BOT_TOKEN,
        'CHANNEL_ID': CHANNEL_ID,
        'AMAZON_TAG': AMAZON_AFFILIATE_TAG,
        'GITHUB_TOKEN': GITHUB_TOKEN
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        exit(1)
    
    logger.info("✅ All required environment variables present")
    
    # Optional variables
    optional_vars = {
        'SERP_API_KEY': SERP_API_KEY
    }
    
    for var, value in optional_vars.items():
        status = "✅ Available" if value else "⚠️ Not available (using fallback)"
        logger.info(f"{var}: {status}")
    
    # Initialize bot
    try:
        logger.info("🤖 Initializing Enhanced Affiliate Bot...")
        bot_instance = EnhancedAffiliateBot()
        
        logger.info(f"📊 Bot Status:")
        logger.info(f"   📎 Total links loaded: {len(bot_instance.links)}")
        logger.info(f"   📍 Starting from index: {bot_instance.current_index}")
        logger.info(f"   🎯 Target channel: {CHANNEL_ID}")
        logger.info(f"   🌐 Target repository: {WEBSITE_REPO}")
        logger.info(f"   🔑 SerpApi integration: {'Enabled' if SERP_API_KEY else 'Disabled (fallback mode)'}")
        
        if len(bot_instance.links) == 0:
            logger.error("❌ No valid links available - cannot proceed")
            exit(1)
        
        # Run session
        logger.info(f"🚀 Starting {SESSION_TYPE} session...")
        sent_count = await bot_instance.send_scheduled_links(SESSION_TYPE)
        
        logger.info("🎉 SESSION COMPLETED SUCCESSFULLY!")
        logger.info(f"✅ Final Result: {sent_count} Telegram links sent, Website updated with enhanced data")
        
    except Exception as e:
        logger.error(f"❌ Critical error in main execution: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        exit(1)

if __name__ == '__main__':
    asyncio.run(main())
