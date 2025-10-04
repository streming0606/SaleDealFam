#!/usr/bin/env python3
import os
import json
import asyncio
import logging
import re
import requests
from datetime import datetime
import pytz
import base64
import traceback

# ----- CONFIGURATION -----
WEBSITE_REPO = "streming0606/DealFamSheduler"  # GitHub repo for your website
GITHUB_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')
SERP_API_KEY = os.environ.get('SERP_API_KEY')
SESSION_TYPE = os.environ.get('SESSION_TYPE', 'morning')
PRODUCTS_PER_RUN = int(os.environ.get('PRODUCTS_PER_RUN', 2))  # Products per session (adjust as needed)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebsiteBot")

class WebsiteAffiliateBot:
    def __init__(self):
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        logger.info(f"Loaded {len(self.links)} Amazon links, starting from index {self.current_index}")

    def load_amazon_links(self):
        path = 'data/amazon_links.json'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('links', [])
        logger.warning("No amazon_links.json found.")
        return []

    def load_progress(self):
        try:
            if GITHUB_TOKEN:
                progress = self.get_progress_from_github()
                if progress is not None:
                    return progress
            if os.path.exists('data/progress.json'):
                with open('data/progress.json', 'r') as f:
                    data = json.load(f)
                    return data.get('current_index', 0)
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
        return 0

    def get_progress_from_github(self):
        url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/progress.json"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                file_content = response.json()
                content = base64.b64decode(file_content['content']).decode('utf-8')
                data = json.loads(content)
                return data.get('current_index', 0)
        except Exception:
            return None

    def save_progress(self):
        progress_data = {
            'current_index': self.current_index,
            'total_links': len(self.links),
            'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            'session_type': SESSION_TYPE
        }
        path = 'data/progress.json'
        with open(path, 'w') as f:
            json.dump(progress_data, f, indent=2)
        asyncio.create_task(self.update_progress_on_github(progress_data))

    async def update_progress_on_github(self, progress_data):
        if not GITHUB_TOKEN:
            return False
        await self.commit_to_github(
            'data/progress.json',
            json.dumps(progress_data, indent=2)
        )

    def extract_asin_from_url(self, url):
        match = re.search(r'/dp/([A-Z0-9]{10})', url)
        return match.group(1) if match else None

    def categorize_by_title(self, title):
        # THIS METHOD IS KEPT FOR BACKWARD COMPATIBILITY ONLY, NOT USED BY FIXED FLOW
        title_lower = title.lower()

        categories = {
            'electronics': ['phone', 'smartphone', 'mobile', 'laptop', 'computer', 'tablet', 'earphone', 'headphone', 'charger', 'cable', 'speaker', 'camera', 'television'],
            'fashion': ['shirt', 'tshirt', 'jeans', 'dress', 'shoes', 'watch', 'bag', 'clothing', 'jacket', 'cap', 'sunglasses', 'wallet'],
            'home': ['kitchen', 'furniture', 'home', 'decor', 'appliance', 'bedsheet', 'pillow', 'chair', 'table', 'lamp', 'mattress', 'curtain'],
            'health': ['skincare', 'beauty', 'cosmetic', 'health', 'supplement', 'medicine', 'cream', 'oil', 'soap', 'vitamin', 'hygiene']
        }

        for category, keywords in categories.items():
            for kw in keywords:
                if kw in title_lower:
                    return category

        return 'electronics'  # Default category if none matched

    async def get_real_product_info_serpapi(self, asin):
        if not SERP_API_KEY or not asin:
            return self.get_fallback_product_info(asin)
        try:
            params = {
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'asin': asin,  # Using 'asin' for direct product lookup in SerpAPI
                'api_key': SERP_API_KEY
            }
            resp = requests.get('https://serpapi.com/search', params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                prod = data.get('product_results')

                if not prod:
                    result = data.get('organic_results', [])
                    prod = next((r for r in result if r.get('asin') == asin), None)
                    if not prod and result:
                        prod = result[0]

                if prod:
                    title = prod.get('title', f'Amazon Product {asin}')[:120]

                    # Use improved extraction of category from SerpAPI data
                    category = self.extract_category_from_serpapi(prod)

                    # Fallback to improved title-based categorization if no category found
                    if not category:
                        category = self.categorize_by_title_improved(title)

                    return {
                        'asin': asin,
                        'title': title,
                        'image': prod.get('thumbnail', f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg"),
                        'price': prod.get('price', '₹Special Price'),
                        'rating': prod.get('rating', '⭐⭐⭐⭐☆'),
                        'category': category,
                        'source': 'serpapi'
                    }
        except Exception:
            logger.error(traceback.format_exc())
        return self.get_fallback_product_info(asin)

    def extract_category_from_serpapi(self, product_data):
        """Extract category from SerpAPI response - most accurate method"""
        if 'categories_hierarchy' in product_data:
            categories = product_data['categories_hierarchy']
            if categories:
                main_category = categories[0].lower()
                return self.map_amazon_category_to_simple(main_category)

        if 'categories' in product_data:
            categories = product_data['categories']
            if isinstance(categories, list) and categories:
                main_category = categories[0].lower()
                return self.map_amazon_category_to_simple(main_category)

        return None

    def map_amazon_category_to_simple(self, amazon_category):
        """Map Amazon's detailed categories to your simplified categories"""
        category_lower = amazon_category.lower()

        if any(word in category_lower for word in ['electronics', 'computer', 'mobile', 'phone', 'laptop', 'tablet', 'camera', 'television', 'audio', 'video', 'gaming', 'smart home']):
            return 'electronics'

        if any(word in category_lower for word in ['clothing', 'fashion', 'shoes', 'jewelry', 'watches', 'bags', 'accessories', 'apparel', 'footwear', "men's", "women's", 'kids']):
            return 'fashion'

        if any(word in category_lower for word in ['home', 'kitchen', 'furniture', 'garden', 'tools', 'appliances', 'decor', 'bedding', 'bath', 'storage']):
            return 'home'

        if any(word in category_lower for word in ['health', 'beauty', 'personal care', 'cosmetic', 'skincare', 'wellness', 'vitamins', 'supplements']):
            return 'health'

        return 'electronics'

    def categorize_by_title_improved(self, title):
        """Improved title-based categorization with weighted scoring fallback"""
        title_lower = title.lower()

        category_keywords = {
            'fashion': {
                'primary': ['shirt', 'tshirt', 't-shirt', 'jeans', 'dress', 'shoes', 'trouser', 'jacket', 'coat', 'pants', 'shorts', 'skirt', 'saree', 'kurta', 'lehenga', 'blazer', 'suit', 'hoodie', 'sweater'],
                'secondary': ['men', 'women', 'boys', 'girls', 'kids', 'clothing', 'apparel', 'fashion', 'wear', 'cotton', 'denim', 'leather', 'silk']
            },
            'electronics': {
                'primary': ['phone', 'smartphone', 'mobile', 'laptop', 'computer', 'tablet', 'earphone', 'headphone', 'earbuds', 'speaker', 'camera', 'television', 'tv', 'monitor', 'keyboard', 'mouse', 'processor', 'ram', 'ssd'],
                'secondary': ['electronic', 'digital', 'wireless', 'bluetooth', 'usb', 'hdmi', 'led', 'smart', 'gaming', 'tech']
            },
            'home': {
                'primary': ['kitchen', 'furniture', 'bed', 'sofa', 'chair', 'table', 'mattress', 'pillow', 'curtain', 'cookware', 'utensil', 'mixer', 'grinder', 'cooker', 'pan', 'pot', 'tawa'],
                'secondary': ['home', 'decor', 'appliance', 'bedsheet', 'lamp', 'storage', 'organizer', 'rack', 'cabinet']
            },
            'health': {
                'primary': ['skincare', 'facewash', 'cream', 'lotion', 'serum', 'shampoo', 'conditioner', 'soap', 'vitamin', 'supplement', 'protein', 'medicine', 'sanitizer'],
                'secondary': ['beauty', 'cosmetic', 'health', 'care', 'hygiene', 'wellness', 'natural', 'organic', 'oil']
            }
        }

        scores = {}
        for category, keywords in category_keywords.items():
            score = 0
            for kw in keywords['primary']:
                if kw in title_lower:
                    score += 10
            for kw in keywords['secondary']:
                if kw in title_lower:
                    score += 2
            scores[category] = score

        max_category = max(scores, key=scores.get)
        return max_category if scores[max_category] > 0 else 'electronics'

    def get_fallback_product_info(self, asin):
        return {
            'asin': asin or "UNKNOWN",
            'title': f"Amazon Product {asin}" if asin else "Amazon Product",
            'image': f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg" if asin else "",
            'price': "₹Special Price",
            'rating': "⭐⭐⭐⭐☆",
            'category': "electronics",
            'source': 'fallback'
        }

    async def get_website_products(self):
        if not GITHUB_TOKEN:
            return []
        url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/products.json"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                file_content = resp.json()
                content = base64.b64decode(file_content['content']).decode('utf-8')
                data = json.loads(content)
                return data.get('products', [])
        except Exception:
            pass
        return []

    async def commit_to_github(self, file_path, content):
        url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/{file_path}"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        sha = None
        get_resp = requests.get(url, headers=headers, timeout=10)
        if get_resp.status_code == 200:
            sha = get_resp.json()['sha']
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        commit_data = {
            'message': f'Auto-update: {SESSION_TYPE} - Index {self.current_index}',
            'content': encoded_content,
            'branch': 'main'
        }
        if sha:
            commit_data['sha'] = sha
        resp = requests.put(url, headers=headers, json=commit_data, timeout=30)
        return resp.status_code in [200, 201]

    def get_next_links(self, count):
        links = []
        for _ in range(count):
            if not self.links:
                break
            if self.current_index >= len(self.links):
                self.current_index = 0
            links.append(self.links[self.current_index])
            self.current_index += 1
        self.save_progress()
        return links

    async def run(self):
        logger.info("Posting product links continuously to website -- NO TELEGRAM")
        next_links = self.get_next_links(PRODUCTS_PER_RUN)
        if not next_links:
            logger.warning("No Amazon links to post.")
            return
        website_products = await self.get_website_products()
        for link in next_links:
            asin = self.extract_asin_from_url(link)
            info = await self.get_real_product_info_serpapi(asin)
            product = {
                'id': f"product_{SESSION_TYPE}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'title': info['title'],
                'image': info['image'],
                'affiliate_link': link,
                'price': info['price'],
                'rating': info['rating'],
                'category': info['category'],
                'asin': info['asin'],
                'data_source': info['source'],
                'posted_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
                'session_type': SESSION_TYPE,
                'link_index': self.current_index - 1
            }
            website_products.insert(0, product)
        updated_data = {
            "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            "total_products": len(website_products),
            "products": website_products
        }
        await self.commit_to_github('data/products.json', json.dumps(updated_data, indent=2))
        logger.info(f"Posted {len(next_links)} products. Total now: {len(website_products)}")

async def main():
    bot = WebsiteAffiliateBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
