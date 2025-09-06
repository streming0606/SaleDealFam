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
SERPAPI_KEY = os.environ.get('SERPAPI_KEY')  # NEW: Add this secret

SESSION_CONFIG = {
    'morning': {'links': 3, 'time': '10:12-10:20 AM'},
    'afternoon': {'links': 3, 'time': '1:12-1:20 PM'},
    'evening': {'links': 2, 'time': '6:12-6:20 PM'},
    'night': {'links': 2, 'time': '9:12-9:20 PM'}
}

class SerpApiBot:
    def _init_(self):
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
    
    def extract_asin(self, url):
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return asin_match.group(1) if asin_match else None
    
    def get_product_data_from_serpapi(self, amazon_url):
        """Get product data using SerpApi - RELIABLE METHOD"""
        try:
            asin = self.extract_asin(amazon_url)
            if not asin:
                logger.error("No ASIN found in URL")
                return self.get_fallback_data(amazon_url)
            
            logger.info(f"🔍 Fetching data for ASIN: {asin} via SerpApi")
            
            # SerpApi parameters for Amazon product lookup
            params = {
                'api_key': SERPAPI_KEY,
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'type': 'product',
                'asin': asin
            }
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'product' in data:
                    product = data['product']
                    
                    # Extract comprehensive product data
                    product_data = {
                        'title': self.clean_title(product.get('title', '')),
                        'price': self.format_price(product.get('price', '')),
                        'image': self.get_best_image(product.get('images', [])),
                        'rating': self.format_rating(product.get('rating', 0)),
                        'category': self.categorize_product(amazon_url, product.get('title', '')),
                        'asin': asin
                    }
                    
                    # Validate data quality
                    if self.is_valid_product_data(product_data):
                        logger.info(f"✅ SerpApi: Successfully fetched {product_data['title'][:50]}...")
                        return product_data
                    else:
                        logger.warning("⚠ SerpApi returned invalid data")
                        
                else:
                    logger.warning("⚠ No product data in SerpApi response")
                    
            else:
                logger.error(f"❌ SerpApi API error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ SerpApi request failed: {e}")
        
        # Fallback if SerpApi fails
        return self.get_fallback_data(amazon_url)
    
    def clean_title(self, title):
        """Clean and format product title"""
        if not title:
            return "Amazon Product"
        
        # Remove extra whitespace and truncate
        cleaned = re.sub(r'\s+', ' ', title.strip())
        return cleaned[:120] + "..." if len(cleaned) > 120 else cleaned
    
    def format_price(self, price):
        """Format price consistently"""
        if not price:
            return "₹Special Price"
        
        price_str = str(price)
        if '₹' in price_str:
            return price_str
        elif 'Rs' in price_str:
            return price_str.replace('Rs', '₹')
        else:
            # Extract numbers and add currency
            numbers = re.findall(r'[\d,]+\.?\d*', price_str)
            if numbers:
                return f"₹{numbers[0]}"
        
        return "₹Special Price"
    
    def get_best_image(self, images):
        """Get highest quality image from SerpApi images array"""
        if not images or not isinstance(images, list):
            return ""
        
        # SerpApi usually provides images in quality order
        for image in images:
            if isinstance(image, dict):
                # Get the link from image object
                image_url = image.get('link') or image.get('url')
                if image_url and self.is_valid_image_url(image_url):
                    return image_url
            elif isinstance(image, str) and self.is_valid_image_url(image):
                return image
        
        return ""
    
    def is_valid_image_url(self, url):
        """Validate image URL"""
        if not url:
            return False
        
        valid_patterns = [
            'images-na.ssl-images-amazon.com',
            'm.media-amazon.com',
            'images-amazon.com',
            '.jpg', '.jpeg', '.png', '.webp'
        ]
        
        return any(pattern in url.lower() for pattern in valid_patterns)
    
    def format_rating(self, rating):
        """Format rating as stars"""
        if not rating:
            return "⭐⭐⭐⭐⭐"
        
        try:
            rating_num = float(rating)
            stars = '⭐' * min(int(round(rating_num)), 5)
            return f"{stars} ({rating_num})" if rating_num > 0 else "⭐⭐⭐⭐⭐"
        except:
            return "⭐⭐⭐⭐⭐"
    
    def categorize_product(self, url, title):
        """Enhanced product categorization"""
        text_to_analyze = f"{url} {title}".lower()
        
        categories = {
            'electronics': ['phone', 'mobile', 'smartphone', 'laptop', 'computer', 'tablet', 'electronics', 'camera', 'headphone', 'speaker', 'smart', 'watch'],
            'fashion': ['fashion', 'clothing', 'shirt', 'dress', 'shoes', 'footwear', 'jewelry', 'bag', 'apparel', 'wear'],
            'home': ['home', 'kitchen', 'furniture', 'decor', 'appliance', 'bedding', 'bath'],
            'health': ['health', 'beauty', 'care', 'vitamin', 'supplement', 'cosmetic'],
            'sports': ['sports', 'fitness', 'gym', 'exercise', 'outdoor', 'yoga'],
            'vehicle': ['car', 'bike', 'vehicle', 'auto', 'parts'],
            'books': ['book', 'kindle', 'reading', 'novel']
        }
        
        for category, keywords in categories.items():
            if any(keyword in text_to_analyze for keyword in keywords):
                return category
        
        return 'electronics'  # Default
    
    def is_valid_product_data(self, product_data):
        """Validate product data quality"""
        title = product_data.get('title', '')
        return len(title) > 15 and not title.startswith('Amazon Product')
    
    def get_fallback_data(self, url):
        """Fallback data when SerpApi fails"""
        asin = self.extract_asin(url)
        category = self.categorize_product(url, "")
        
        return {
            'title': f"Premium {category.title()} Deal - {asin}" if asin else f"Amazon {category.title()} Product",
            'price': "₹Special Price",
            'image': f"https://images-na.ssl-images-amazon.com/images/I/{asin}.AC_SL1500.jpg" if asin else "",
            'rating': "⭐⭐⭐⭐⭐",
            'category': category,
            'asin': asin
        }
    
    async def update_website_products(self, new_products):
        """Update website with SerpApi data"""
        try:
            if not PERSONAL_ACCESS_TOKEN:
                logger.warning("No GitHub token - skipping website update")
                return False
            
            # Get existing products
            website_products = await self.get_website_products()
            
            # Add new products to beginning
            for product in reversed(new_products):
                website_products.insert(0, product)
            
            # Keep latest 100 products
            website_products = website_products[:100]
            
            # Update JSON
            updated_data = {
                "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                "total_products": len(website_products),
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
                'message': f'🎯 SerpApi Update: {SESSION_TYPE} session with real product data',
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
    
    async def send_serpapi_products(self, session_type):
        """Send products using SerpApi data to both Telegram and Website"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        link_count = config['links']
        time_slot = config['time']
        
        logger.info(f"🚀 Starting SerpApi {session_type} session: {time_slot} IST")
        logger.info(f"📊 Processing {link_count} links via SerpApi")
        
        links_to_process = self.get_next_links(link_count)
        if not links_to_process:
            logger.error("❌ No links available")
            return 0
        
        sent_count = 0
        website_products = []
        
        for i, original_link in enumerate(links_to_process, 1):
            try:
                logger.info(f"🔍 Processing product {i}/{link_count} via SerpApi")
                
                # Convert to affiliate link
                affiliate_link = self.convert_amazon_link(original_link)
                
                # Get product data from SerpApi
                product_data = self.get_product_data_from_serpapi(original_link)
                
                # Create enhanced Telegram message
                telegram_message = f"""🔥 DEAL FAM ALERT! 🔥

📱 *{product_data['title']}*

💰 *Price:* {product_data['price']}
⭐ *Rating:* {product_data['rating']}
🏷 *Category:* {product_data['category'].title()}

🛒 *Get Deal:* {affiliate_link}

⏰ *Limited Time Offer - Grab Now!*

#DealFam #AmazonDeals #Shopping #{product_data['category'].title()}Deals"""
                
                # Send to Telegram (keep existing 10 daily posts)
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=telegram_message,
                    parse_mode='Markdown'
                )
                
                # For website: Only process if it's one of the 6 daily website posts
                # We'll process fewer products for website to stay within SerpApi limits
                if i <= min(2, link_count):  # Only first 2 products per session for website
                    website_product = {
                        'id': f"product_{session_type}{i}{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        'title': product_data['title'],
                        'image': product_data['image'],
                        'affiliate_link': affiliate_link,
                        'price': product_data['price'],
                        'rating': product_data['rating'],
                        'category': product_data['category'],
                        'posted_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                        'session_type': session_type,
                        'asin': product_data['asin']
                    }
                    
                    website_products.append(website_product)
                
                # Log success
                ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                logger.info(f"✅ {session_type.upper()}: SerpApi product {i}/{link_count} at {ist_time}")
                logger.info(f"📝 Title: {product_data['title'][:50]}...")
                logger.info(f"💰 Price: {product_data['price']}")
                logger.info(f"📸 Image: {'✅' if product_data['image'] else '❌'}")
                
                sent_count += 1
                
                # Wait between requests to avoid rate limiting
                if i < len(links_to_process):
                    await asyncio.sleep(5)
                    
            except Exception as e:
                logger.error(f"❌ Error processing product {i}: {e}")
                continue
        
        # Update website with SerpApi products (only 6 daily, not all 10)
        if website_products:
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"🌐 Website updated with {len(website_products)} SerpApi products")
        
        # Final summary
        logger.info(f"🎉 {session_type.upper()} SESSION COMPLETE:")
        logger.info(f"   ✅ Telegram: {sent_count}/{link_count} posts (all products)")
        logger.info(f"   🌐 Website: {len(website_products)} products (SerpApi enhanced)")
        logger.info(f"   📊 SerpApi calls used: {len(website_products)}")
        
        return sent_count

# Main execution
async def main():
    logger.info("🚀 Starting SerpApi Enhanced Bot...")
    
    if not all([BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG]):
        logger.error("❌ Missing required environment variables")
        exit(1)
    
    if not SERPAPI_KEY:
        logger.error("❌ SERPAPI_KEY not found - please add to GitHub secrets")
        exit(1)
    
    bot_instance = SerpApiBot()
    
    logger.info(f"📊 Total links: {len(bot_instance.links)}")
    logger.info(f"📍 Current index: {bot_instance.current_index}")
    logger.info(f"🎯 Target: Telegram (10 posts) + Website (6 SerpApi enhanced)")
    
    try:
        sent_count = await bot_instance.send_serpapi_products(SESSION_TYPE)
        logger.info(f"🎉 SerpApi session completed! {sent_count} posts sent")
        
    except Exception as e:
        logger.error(f"❌ Error in SerpApi session: {e}")
        exit(1)

if _name_ == '_main_':
    asyncio.run(main())
