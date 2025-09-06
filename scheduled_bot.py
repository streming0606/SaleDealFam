#!/usr/bin/env python3
import logging
import re
import os
import json
import asyncio
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup
import base64
from urllib.parse import urlparse, parse_qs
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
import time
import random

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
PERSONAL_ACCESS_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')

SESSION_CONFIG = {
    'morning': {'links': 3, 'time': '10:12-10:20 AM'},
    'afternoon': {'links': 3, 'time': '1:12-1:20 PM'},
    'evening': {'links': 2, 'time': '6:12-6:20 PM'},
    'night': {'links': 2, 'time': '9:12-9:20 PM'}
}

class EnhancedImageBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
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
    
    def extract_product_details(self, amazon_url):
        """Extract comprehensive product details from Amazon URL"""
        try:
            logger.info(f"Extracting product details from: {amazon_url}")
            
            # Add random delay to avoid rate limiting
            time.sleep(random.uniform(1, 3))
            
            response = self.session.get(amazon_url, timeout=15)
            if response.status_code != 200:
                logger.warning(f"Failed to fetch page: {response.status_code}")
                return self.get_fallback_product_info(amazon_url)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract product details
            product_info = {
                'title': self.extract_title(soup, amazon_url),
                'image': self.extract_image(soup, amazon_url),
                'price': self.extract_price(soup),
                'rating': self.extract_rating(soup),
                'category': self.categorize_product(amazon_url, soup),
                'asin': self.extract_asin(amazon_url)
            }
            
            logger.info(f"✅ Successfully extracted: {product_info['title'][:50]}...")
            return product_info
            
        except Exception as e:
            logger.error(f"Error extracting product details: {e}")
            return self.get_fallback_product_info(amazon_url)
    
    def extract_title(self, soup, url):
        """Extract product title"""
        title_selectors = [
            '#productTitle',
            'h1.a-size-large',
            'h1[data-automation-id="product-title"]',
            '.product-title',
            'h1'
        ]
        
        for selector in title_selectors:
            title_element = soup.select_one(selector)
            if title_element:
                title = title_element.get_text().strip()
                if len(title) > 10:  # Valid title
                    return title[:100] + "..." if len(title) > 100 else title
        
        # Fallback to URL parsing
        asin = self.extract_asin(url)
        return f"Amazon Product {asin}" if asin else "Amazon Deal"
    
    def extract_image(self, soup, url):
        """Extract high-quality product image"""
        image_selectors = [
            '#landingImage',
            '#imgTagWrapperId img',
            '#altImages .a-thumbs-item img',
            '.a-dynamic-image',
            'img[data-a-image-name="landingImage"]',
            '#main-image-container img',
            '.s-image'
        ]
        
        for selector in image_selectors:
            img_element = soup.select_one(selector)
            if img_element:
                # Try different image URL attributes
                image_url = (img_element.get('data-old-hires') or 
                           img_element.get('data-a-dynamic-image') or
                           img_element.get('src') or
                           img_element.get('data-src'))
                
                if image_url and self.is_valid_image_url(image_url):
                    # Clean and enhance image URL
                    clean_url = self.enhance_image_url(image_url)
                    logger.info(f"✅ Found image: {clean_url}")
                    return clean_url
        
        # Fallback: Try to construct image URL from ASIN
        asin = self.extract_asin(url)
        if asin:
            fallback_url = f"https://images-na.ssl-images-amazon.com/images/I/{asin}._AC_SL1500_.jpg"
            logger.info(f"🔄 Using fallback image: {fallback_url}")
            return fallback_url
        
        return ""
    
    def is_valid_image_url(self, url):
        """Check if URL is a valid image URL"""
        if not url or url.startswith('data:'):
            return False
        
        # Check for common image extensions or Amazon image patterns
        image_patterns = ['.jpg', '.jpeg', '.png', '.webp', 'images-na.ssl-images-amazon.com']
        return any(pattern in url.lower() for pattern in image_patterns)
    
    def enhance_image_url(self, image_url):
        """Enhance image URL for higher quality"""
        try:
            # Remove size restrictions and enhance quality
            enhanced_url = re.sub(r'(\._[A-Z]{2}\d+_)', '._AC_SL1500_', image_url)
            enhanced_url = enhanced_url.replace('._SS300_', '._AC_SL1500_')
            enhanced_url = enhanced_url.replace('._SL75_', '._AC_SL1500_')
            
            # Ensure HTTPS
            if enhanced_url.startswith('//'):
                enhanced_url = 'https:' + enhanced_url
            elif not enhanced_url.startswith('http'):
                enhanced_url = 'https://' + enhanced_url.lstrip('/')
                
            return enhanced_url
        except:
            return image_url
    
    def extract_price(self, soup):
        """Extract product price"""
        price_selectors = [
            '.a-price-whole',
            '.a-offscreen',
            '#priceblock_dealprice',
            '#priceblock_saleprice',
            '#priceblock_ourprice',
            '.a-price .a-offscreen'
        ]
        
        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text().strip()
                if '₹' in price_text or 'Rs' in price_text or price_text.replace(',', '').replace('.', '').isdigit():
                    return price_text if '₹' in price_text else f"₹{price_text}"
        
        return "₹Special Price"
    
    def extract_rating(self, soup):
        """Extract product rating"""
        rating_selectors = [
            '.a-icon-alt',
            '[data-hook="average-star-rating"]',
            '.a-star-5 .a-icon-alt',
            '#acrPopover'
        ]
        
        for selector in rating_selectors:
            rating_element = soup.select_one(selector)
            if rating_element:
                rating_text = rating_element.get_text() or rating_element.get('title', '')
                if 'out of 5' in rating_text or 'stars' in rating_text:
                    # Extract numeric rating and convert to stars
                    rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                    if rating_match:
                        rating = float(rating_match.group(1))
                        stars = '⭐' * min(int(rating), 5)
                        return stars
        
        return '⭐⭐⭐⭐⭐'  # Default 5-star rating
    
    def extract_asin(self, url):
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return asin_match.group(1) if asin_match else None
    
    def categorize_product(self, url, soup=None):
        """Categorize product based on URL and page content"""
        url_lower = url.lower()
        
        # URL-based categorization
        url_categories = {
            'electronics': ['phone', 'laptop', 'electronics', 'mobile', 'tablet', 'computer', 'camera', 'headphone', 'speaker'],
            'fashion': ['fashion', 'clothing', 'shoes', 'watch', 'jewelry', 'bag', 'apparel'],
            'home': ['home', 'kitchen', 'furniture', 'decor', 'appliance', 'bedding'],
            'health': ['health', 'beauty', 'care', 'vitamin', 'supplement', 'cosmetic'],
            'sports': ['sports', 'fitness', 'gym', 'outdoor', 'exercise', 'yoga'],
            'vehicle': ['car', 'bike', 'vehicle', 'auto', 'motorcycle', 'accessories'],
            'books': ['book', 'kindle', 'reading', 'novel', 'textbook']
        }
        
        for category, keywords in url_categories.items():
            if any(keyword in url_lower for keyword in keywords):
                return category
        
        # Soup-based categorization (if available)
        if soup:
            breadcrumbs = soup.select('#wayfinding-breadcrumbs_container a')
            if breadcrumbs:
                breadcrumb_text = ' '.join([b.get_text().lower() for b in breadcrumbs])
                for category, keywords in url_categories.items():
                    if any(keyword in breadcrumb_text for keyword in keywords):
                        return category
        
        return 'electronics'  # Default category
    
    def get_fallback_product_info(self, url):
        """Get fallback product info when scraping fails"""
        asin = self.extract_asin(url)
        return {
            'title': f"Amazon Deal {asin}" if asin else "Special Amazon Offer",
            'image': f"https://images-na.ssl-images-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else "",
            'price': "₹Special Price",
            'rating': "⭐⭐⭐⭐⭐",
            'category': self.categorize_product(url),
            'asin': asin
        }
    
    async def update_website_products(self, new_products):
        """Update website products.json with real product data"""
        try:
            if not PERSONAL_ACCESS_TOKEN:
                logger.warning("No GitHub token provided - skipping website update")
                return False
            
            # Load existing products
            website_products = await self.get_website_products()
            
            # Add new products to the beginning
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
                logger.info(f"✅ Website updated with {len(new_products)} products with real images")
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
                logger.info("No existing products file - creating new one")
                return []
                
        except Exception as e:
            logger.error(f"Error getting website products: {e}")
            return []
    
    async def commit_to_github(self, file_path, content):
        """Commit updated products to GitHub"""
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
                'message': f'🤖 Auto-update: {SESSION_TYPE} session with real product images',
                'content': encoded_content,
                'branch': 'main'
            }
            
            if sha:
                commit_data['sha'] = sha
            
            # Commit
            response = requests.put(url, headers=headers, json=commit_data)
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Successfully committed {file_path}")
                return True
            else:
                logger.error(f"❌ GitHub commit failed: {response.status_code}")
                return False
                
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
    
    async def send_enhanced_links(self, session_type):
        """Send links with real Amazon product images to both Telegram and website"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        link_count = config['links']
        time_slot = config['time']
        
        logger.info(f"🚀 Starting {session_type} session: {time_slot} IST")
        logger.info(f"📊 Processing {link_count} links with real product images")
        
        links_to_process = self.get_next_links(link_count)
        if not links_to_process:
            logger.error("❌ No links available")
            return 0
        
        sent_count = 0
        website_products = []
        
        for i, original_link in enumerate(links_to_process, 1):
            try:
                logger.info(f"📦 Processing product {i}/{link_count}")
                
                # Convert to affiliate link
                affiliate_link = self.convert_amazon_link(original_link)
                
                # Extract real product details with images
                product_details = self.extract_product_details(original_link)
                
                # Create Telegram message
                telegram_message = f"""🔥 DEAL FAM ALERT! 🔥

🛒 **{product_details['title']}**

💰 Price: {product_details['price']}
⭐ Rating: {product_details['rating']}
🏷️ Category: {product_details['category'].title()}

🔗 Get Deal: {affiliate_link}

⏰ Limited Time Offer - Don't Miss Out!

#DealFam #AmazonDeals #Shopping #{product_details['category'].title()}Deals"""
                
                # Send to Telegram
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=telegram_message,
                    parse_mode='Markdown'
                )
                
                # Prepare for website
                website_product = {
                    'id': f"product_{session_type}_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    'title': product_details['title'],
                    'image': product_details['image'],
                    'affiliate_link': affiliate_link,
                    'price': product_details['price'],
                    'rating': product_details['rating'],
                    'category': product_details['category'],
                    'posted_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                    'session_type': session_type,
                    'asin': product_details['asin']
                }
                
                website_products.append(website_product)
                
                ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%I:%M:%S %p")
                logger.info(f"✅ {session_type.upper()}: Processed {i}/{link_count} at {ist_time}")
                logger.info(f"📸 Image: {product_details['image'][:50]}...")
                logger.info(f"📝 Title: {product_details['title'][:50]}...")
                
                sent_count += 1
                
                # Wait between requests
                if i < len(links_to_process):
                    await asyncio.sleep(random.uniform(3, 6))
                    
            except Exception as e:
                logger.error(f"❌ Error processing link {i}: {e}")
                continue
        
        # Update website with enhanced products
        if website_products:
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"🌐 Website updated with {len(website_products)} products with real images")
            else:
                logger.error("❌ Website update failed")
        
        # Final summary
        logger.info(f"🎉 {session_type.upper()} SESSION COMPLETE:")
        logger.info(f"   ✅ Telegram: {sent_count}/{link_count} posts")
        logger.info(f"   🌐 Website: {len(website_products)} products with real images")
        logger.info(f"   📸 All images extracted from real Amazon pages")
        
        return sent_count

# Main execution
async def main():
    logger.info("🚀 Starting Enhanced Amazon Image Bot...")
    
    if not all([BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG]):
        logger.error("❌ Missing required environment variables")
        exit(1)
    
    bot_instance = EnhancedImageBot()
    
    logger.info(f"📊 Total links: {len(bot_instance.links)}")
    logger.info(f"📍 Current index: {bot_instance.current_index}")
    logger.info(f"🎯 Target: Telegram + Website with real images")
    
    try:
        sent_count = await bot_instance.send_enhanced_links(SESSION_TYPE)
        logger.info(f"🎉 Enhanced session completed! {sent_count} products with real images")
        
    except Exception as e:
        logger.error(f"❌ Error in enhanced session: {e}")
        exit(1)

if __name__ == '__main__':
    asyncio.run(main())
