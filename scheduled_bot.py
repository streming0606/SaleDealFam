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
import random
import time
from urllib.parse import urljoin
from telegram import Bot
from telegram.error import TelegramError

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
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

class RobustAmazonScraper:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        
        # Enhanced session with multiple user agents
        self.session = requests.Session()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        
    def get_random_headers(self):
        """Get random headers to avoid detection"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
    
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
    
    def extract_comprehensive_product_data(self, amazon_url):
        """Extract product data with multiple fallback methods"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"🔍 Extracting data from: {amazon_url} (Attempt {attempt + 1})")
                
                # Random delay between requests
                time.sleep(random.uniform(2, 5))
                
                # Make request with random headers
                headers = self.get_random_headers()
                response = self.session.get(amazon_url, headers=headers, timeout=20)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Extract all product data
                    product_data = {
                        'title': self.extract_title_robust(soup, amazon_url),
                        'price': self.extract_price_robust(soup),
                        'image': self.extract_image_robust(soup, amazon_url),
                        'rating': self.extract_rating_robust(soup),
                        'category': self.categorize_product_robust(amazon_url, soup),
                        'asin': self.extract_asin(amazon_url)
                    }
                    
                    # Validate extracted data
                    if self.is_valid_product_data(product_data):
                        logger.info(f"✅ Successfully extracted: {product_data['title'][:50]}...")
                        return product_data
                    else:
                        logger.warning(f"⚠️ Invalid data extracted, trying again...")
                        
                else:
                    logger.warning(f"⚠️ HTTP {response.status_code}, retrying...")
                    
            except Exception as e:
                logger.error(f"❌ Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(random.uniform(3, 7))
        
        # Final fallback
        logger.warning("🔄 Using fallback data...")
        return self.get_enhanced_fallback_data(amazon_url)
    
    def extract_title_robust(self, soup, url):
        """Extract title with multiple selectors"""
        title_selectors = [
            'span#productTitle',
            'h1.a-size-large.a-spacing-none.a-color-base',
            'h1[data-automation-id="product-title"]',
            'h1.it-ttl',
            '.product-title',
            'h1.a-size-large',
            'span.product-title-word-break',
            '#btAsinTitle',
            '.parseasinTitle',
            'h1',
            'title'
        ]
        
        for selector in title_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    title = element.get_text(strip=True)
                    # Clean and validate title
                    title = re.sub(r'\s+', ' ', title)
                    if len(title) > 15 and 'Amazon' not in title[:20]:
                        return title[:120] + "..." if len(title) > 120 else title
            except Exception as e:
                continue
        
        # Fallback: Extract from meta tags
        try:
            meta_title = soup.find('meta', {'property': 'og:title'})
            if meta_title and meta_title.get('content'):
                title = meta_title['content'].strip()
                if len(title) > 15:
                    return title[:120] + "..." if len(title) > 120 else title
        except:
            pass
        
        # Final fallback
        asin = self.extract_asin(url)
        return f"Amazon Product {asin}" if asin else "Amazon Deal"
    
    def extract_price_robust(self, soup):
        """Extract price with multiple selectors"""
        price_selectors = [
            # Primary price selectors
            'span.a-price.a-text-price.a-size-medium.apexPriceToPay .a-offscreen',
            'span.a-price-whole',
            'span#priceblock_ourprice',
            'span#priceblock_saleprice',
            'span#priceblock_dealprice',
            'span.a-price.a-text-price .a-offscreen',
            'span.a-price .a-offscreen',
            '.a-price-current .a-offscreen',
            '.a-price .a-price-whole',
            
            # Alternative selectors
            'span[data-a-size="xl"] .a-offscreen',
            'span.a-size-medium.a-color-price.priceBlockBuyingPriceString',
            '.a-price-range .a-offscreen',
            'span.a-color-price',
            'span.a-text-bold',
            
            # Fallback selectors
            '.price',
            '[data-testid="price"]',
            '.a-offscreen'
        ]
        
        for selector in price_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    price_text = element.get_text(strip=True)
                    # Clean price text
                    price_text = re.sub(r'\s+', ' ', price_text)
                    
                    # Validate Indian price format
                    if any(currency in price_text for currency in ['₹', 'Rs.', 'INR']):
                        return price_text
                    elif re.search(r'[\d,]+\.?\d*', price_text):
                        numbers = re.findall(r'[\d,]+\.?\d*', price_text)
                        if numbers:
                            return f"₹{numbers[0]}"
            except Exception:
                continue
        
        # Try to find any number that looks like a price
        try:
            text_content = soup.get_text()
            price_matches = re.findall(r'₹\s*[\d,]+(?:\.\d{2})?', text_content)
            if price_matches:
                return price_matches[0].strip()
        except:
            pass
        
        return "₹Special Price"
    
    def extract_image_robust(self, soup, url):
        """Extract image with multiple selectors and enhance quality"""
        image_selectors = [
            # Primary image selectors
            'img#landingImage',
            'img[data-a-image-name="landingImage"]',
            'img.a-dynamic-image',
            'div#imgTagWrapperId img',
            'div#main-image-container img',
            
            # Alternative selectors
            'img[data-old-hires]',
            'img[data-a-dynamic-image]',
            'div.imgTagWrapper img',
            'span[data-action="main-image-click"] img',
            'div#altImages img',
            
            # Fallback selectors
            'img.s-image',
            'img[src*="images-na.ssl-images-amazon.com"]',
            'img[src*="m.media-amazon.com"]',
            'img[alt*="product"]',
            'img[data-src]'
        ]
        
        for selector in image_selectors:
            try:
                img_element = soup.select_one(selector)
                if img_element:
                    # Try different attributes for image URL
                    image_url = None
                    for attr in ['data-old-hires', 'data-a-dynamic-image', 'src', 'data-src']:
                        if img_element.get(attr):
                            if attr == 'data-a-dynamic-image':
                                # Parse JSON data for highest resolution
                                try:
                                    import json
                                    image_data = json.loads(img_element[attr])
                                    if image_data:
                                        # Get the highest resolution URL
                                        image_url = max(image_data.keys(), key=len)
                                        break
                                except:
                                    continue
                            else:
                                image_url = img_element[attr]
                                break
                    
                    if image_url and self.is_valid_image_url(image_url):
                        # Enhance image quality
                        enhanced_url = self.enhance_image_quality(image_url)
                        logger.info(f"📸 Found image: {enhanced_url[:50]}...")
                        return enhanced_url
            except Exception:
                continue
        
        # Fallback: construct from ASIN
        asin = self.extract_asin(url)
        if asin:
            fallback_urls = [
                f"https://images-na.ssl-images-amazon.com/images/I/{asin}._AC_SX679_.jpg",
                f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg",
                f"https://images-na.ssl-images-amazon.com/images/I/{asin}._AC_SL1500_.jpg"
            ]
            
            for fallback_url in fallback_urls:
                if self.test_image_accessibility(fallback_url):
                    logger.info(f"🔄 Using fallback image: {fallback_url}")
                    return fallback_url
        
        return ""
    
    def extract_rating_robust(self, soup):
        """Extract rating with multiple selectors"""
        rating_selectors = [
            'span.a-icon-alt',
            'i.a-icon.a-icon-star span.a-icon-alt',
            'span[data-hook="rating-out-of-text"]',
            'div.a-row.a-spacing-small span.a-icon-alt',
            'div#acrPopover span.a-icon-alt',
            'span.reviewCountTextLinkedHistogram',
            '.a-star-5 .a-icon-alt',
            '.cr-original-review-text'
        ]
        
        for selector in rating_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    rating_text = element.get_text(strip=True)
                    if 'out of 5' in rating_text or 'stars' in rating_text:
                        # Extract numeric rating
                        rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                        if rating_match:
                            rating_num = float(rating_match.group(1))
                            stars = '⭐' * min(int(round(rating_num)), 5)
                            return f"{stars} ({rating_num})"
            except Exception:
                continue
        
        # Default rating
        return '⭐⭐⭐⭐⭐'
    
    def is_valid_image_url(self, url):
        """Validate image URL"""
        if not url or len(url) < 10:
            return False
        
        valid_patterns = [
            'images-na.ssl-images-amazon.com',
            'm.media-amazon.com',
            'images-amazon.com',
            '.jpg', '.jpeg', '.png', '.webp'
        ]
        
        return any(pattern in url.lower() for pattern in valid_patterns)
    
    def enhance_image_quality(self, image_url):
        """Enhance image URL for better quality"""
        try:
            # Replace size parameters for higher quality
            enhanced = re.sub(r'(\._[A-Z]{2})\d*(_)', r'\1679\2', image_url)
            enhanced = re.sub(r'(\._AC_)[A-Z]*\d*(_)', r'\1SL1500\2', enhanced)
            enhanced = enhanced.replace('._SS300_', '._AC_SL1500_')
            enhanced = enhanced.replace('._SL75_', '._AC_SL1500_')
            
            # Ensure HTTPS
            if enhanced.startswith('//'):
                enhanced = 'https:' + enhanced
            elif not enhanced.startswith('http'):
                enhanced = 'https://' + enhanced.lstrip('/')
                
            return enhanced
        except:
            return image_url
    
    def test_image_accessibility(self, image_url):
        """Test if image URL is accessible"""
        try:
            response = requests.head(image_url, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def categorize_product_robust(self, url, soup):
        """Enhanced product categorization"""
        url_lower = url.lower()
        
        # URL-based categorization with more keywords
        url_categories = {
            'electronics': ['phone', 'mobile', 'smartphone', 'laptop', 'computer', 'tablet', 'electronics', 'gadget', 'device', 'tech', 'camera', 'headphone', 'speaker', 'smart', 'digital'],
            'fashion': ['fashion', 'clothing', 'clothes', 'shirt', 'dress', 'shoes', 'footwear', 'watch', 'jewelry', 'bag', 'apparel', 'wear', 'style'],
            'home': ['home', 'house', 'kitchen', 'furniture', 'decor', 'appliance', 'bedding', 'bath', 'garden', 'living'],
            'health': ['health', 'medical', 'beauty', 'skincare', 'care', 'vitamin', 'supplement', 'cosmetic', 'wellness'],
            'sports': ['sports', 'fitness', 'gym', 'exercise', 'outdoor', 'yoga', 'running', 'athletic'],
            'vehicle': ['car', 'bike', 'motorcycle', 'vehicle', 'auto', 'automotive', 'parts'],
            'books': ['book', 'kindle', 'reading', 'novel', 'textbook', 'education', 'learn']
        }
        
        # Check URL first
        for category, keywords in url_categories.items():
            if any(keyword in url_lower for keyword in keywords):
                return category
        
        # Check page content
        if soup:
            try:
                page_text = soup.get_text().lower()
                for category, keywords in url_categories.items():
                    keyword_count = sum(1 for keyword in keywords if keyword in page_text)
                    if keyword_count >= 2:  # At least 2 keywords match
                        return category
            except:
                pass
        
        return 'electronics'  # Default category
    
    def extract_asin(self, url):
        """Extract ASIN from Amazon URL"""
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return asin_match.group(1) if asin_match else None
    
    def is_valid_product_data(self, product_data):
        """Validate that product data is meaningful"""
        # Check if title is meaningful
        title = product_data.get('title', '')
        if len(title) < 15 or title.startswith('Amazon Product') or title == 'Amazon Deal':
            return False
        
        # Check if we have some real data
        price = product_data.get('price', '')
        image = product_data.get('image', '')
        
        # At least title should be real
        return len(title) > 15
    
    def get_enhanced_fallback_data(self, url):
        """Enhanced fallback data"""
        asin = self.extract_asin(url)
        category = self.categorize_product_robust(url, None)
        
        # Try to create meaningful title from URL
        title_parts = url.split('/')
        for part in title_parts:
            if len(part) > 20 and any(char.isalpha() for char in part):
                # Clean up URL part to make it title-like
                clean_title = re.sub(r'[^\w\s-]', ' ', part)
                clean_title = re.sub(r'\s+', ' ', clean_title).strip().title()
                if len(clean_title) > 15:
                    title = clean_title[:80] + "..."
                    break
        else:
            title = f"Premium {category.title()} Product"
        
        return {
            'title': title,
            'price': "₹Special Price",
            'image': f"https://images-na.ssl-images-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else "",
            'rating': "⭐⭐⭐⭐⭐",
            'category': category,
            'asin': asin
        }
    
    async def update_website_products(self, new_products):
        """Update website with enhanced products"""
        try:
            if not PERSONAL_ACCESS_TOKEN:
                logger.warning("No GitHub token - skipping website update")
                return False
            
            # Load existing products
            website_products = await self.get_website_products()
            
            # Add new products to beginning
            for product in reversed(new_products):
                website_products.insert(0, product)
            
            # Keep latest 100
            website_products = website_products[:100]
            
            # Update JSON structure
            updated_data = {
                "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                "total_products": len(website_products),
                "products": website_products
            }
            
            # Commit to GitHub
            success = await self.commit_to_github('data/products.json', json.dumps(updated_data, indent=2))
            
            if success:
                logger.info(f"✅ Website updated with {len(new_products)} enhanced products")
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
                'message': f'🚀 Enhanced update: {SESSION_TYPE} session with robust product data',
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
    
    async def send_enhanced_products(self, session_type):
        """Send enhanced products to both Telegram and website"""
        config = SESSION_CONFIG.get(session_type, SESSION_CONFIG['morning'])
        link_count = config['links']
        time_slot = config['time']
        
        logger.info(f"🚀 Starting enhanced {session_type} session: {time_slot} IST")
        logger.info(f"📊 Processing {link_count} links with robust extraction")
        
        links_to_process = self.get_next_links(link_count)
        if not links_to_process:
            logger.error("❌ No links available")
            return 0
        
        sent_count = 0
        website_products = []
        
        for i, original_link in enumerate(links_to_process, 1):
            try:
                logger.info(f"🔍 Processing product {i}/{link_count}")
                
                # Convert to affiliate link
                affiliate_link = self.convert_amazon_link(original_link)
                
                # Extract comprehensive product data
                product_data = self.extract_comprehensive_product_data(original_link)
                
                # Create enhanced Telegram message
                telegram_message = f"""🔥 DEAL FAM ALERT! 🔥

📱 **{product_data['title']}**

💰 **Price:** {product_data['price']}
⭐ **Rating:** {product_data['rating']}
🏷️ **Category:** {product_data['category'].title()}

🛒 **Get Deal:** {affiliate_link}

⏰ **Limited Time Offer - Grab Now!**

#DealFam #AmazonDeals #Shopping #{product_data['category'].title()}Deals #SpecialOffer"""
                
                # Send to Telegram
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=telegram_message,
                    parse_mode='Markdown'
                )
                
                # Prepare for website with enhanced data
                website_product = {
                    'id': f"product_{session_type}_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
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
                logger.info(f"✅ {session_type.upper()}: Enhanced product {i}/{link_count} at {ist_time}")
                logger.info(f"📝 Title: {product_data['title'][:60]}...")
                logger.info(f"💰 Price: {product_data['price']}")
                logger.info(f"📸 Image: {'✅ Available' if product_data['image'] else '❌ No image'}")
                
                sent_count += 1
                
                # Wait between requests
                if i < len(links_to_process):
                    await asyncio.sleep(random.uniform(4, 8))
                    
            except Exception as e:
                logger.error(f"❌ Error processing product {i}: {e}")
                continue
        
        # Update website with enhanced products
        if website_products:
            website_success = await self.update_website_products(website_products)
            if website_success:
                logger.info(f"🌐 Website updated with {len(website_products)} enhanced products")
            else:
                logger.error("❌ Website update failed")
        
        # Final summary
        logger.info(f"🎉 {session_type.upper()} SESSION COMPLETE:")
        logger.info(f"   ✅ Telegram: {sent_count}/{link_count} enhanced posts")
        logger.info(f"   🌐 Website: {len(website_products)} products with robust data")
        logger.info(f"   📊 Success Rate: {(sent_count/link_count)*100:.1f}%")
        
        return sent_count

# Main execution
async def main():
    logger.info("🚀 Starting Robust Amazon Product Scraper...")
    
    if not all([BOT_TOKEN, CHANNEL_ID, AMAZON_AFFILIATE_TAG]):
        logger.error("❌ Missing required environment variables")
        exit(1)
    
    scraper = RobustAmazonScraper()
    
    logger.info(f"📊 Total links: {len(scraper.links)}")
    logger.info(f"📍 Current index: {scraper.current_index}")
    logger.info(f"🎯 Target: Enhanced Telegram + Website with robust data extraction")
    
    try:
        sent_count = await scraper.send_enhanced_products(SESSION_TYPE)
        logger.info(f"🎉 Enhanced session completed! {sent_count} products with robust data")
        
    except Exception as e:
        logger.error(f"❌ Error in enhanced session: {e}")
        exit(1)

if __name__ == '__main__':
    asyncio.run(main())
