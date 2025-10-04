#!/usr/bin/env python3
import logging
import os
import json
import asyncio
import time
from datetime import datetime
import pytz
import requests
import re
import traceback

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebsiteProductBot")

# Environment variables
WEBSITE_REPO = "streming0606/DealFamSheduler"
GITHUB_TOKEN = os.environ.get('PERSONAL_ACCESS_TOKEN')
SERP_API_KEY = os.environ.get('SERP_API_KEY')

SESSION_TYPE = os.environ.get('SESSION_TYPE', 'morning')
PRODUCTS_PER_RUN = int(os.environ.get('PRODUCTS_PER_RUN', 2))  # How many products to post per run

class WebsiteAffiliateBot:
    def __init__(self):
        self.links = self.load_amazon_links()
        self.current_index = self.load_progress()
        logger.info(f"Loaded {len(self.links)} links, starting from index {self.current_index}")

    def load_amazon_links(self):
        path = 'data/amazon_links.json'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('links', [])
        logger.warning("No links loaded.")
        return []

    def load_progress(self):
        try:
            github_progress = self.get_progress_from_github()
            if github_progress is not None:
                return github_progress
            path = 'data/progress.json'
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    return data.get('current_index', 0)
        except Exception as e:
            logger.error(f"Error loading progress: {e}")
        return 0

    def get_progress_from_github(self):
        if not GITHUB_TOKEN:
            return None
        url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/data/progress.json"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                import base64
                content = base64.b64decode(response.json()['content']).decode('utf-8')
                data = json.loads(content)
                return data.get('current_index', 0)
        except Exception:
            pass
        return None

    def save_progress(self):
        progress_data = {
            'current_index': self.current_index,
            'total_links': len(self.links),
            'last_updated': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            'session_type': SESSION_TYPE
        }
        with open('data/progress.json', 'w') as f:
            json.dump(progress_data, f, indent=2)
        asyncio.create_task(self.update_progress_on_github(progress_data))

    async def update_progress_on_github(self, progress_data):
        if not GITHUB_TOKEN:
            return False
        return await self.commit_to_github(
            'data/progress.json',
            json.dumps(progress_data, indent=2)
        )

    def extract_asin_from_url(self, amazon_url):
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', amazon_url)
        if asin_match:
            return asin_match.group(1)
        return None

    async def get_real_product_info_serpapi(self, asin):
        if not SERP_API_KEY or not asin:
            return self.get_fallback_product_info(asin)
        try:
            params = {
                'engine': 'amazon',
                'amazon_domain': 'amazon.in',
                'k': asin,
                'api_key': SERP_API_KEY
            }
            response = requests.get('https://serpapi.com/search', params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                organic_results = data.get('organic_results', [])
                product_result = None
                for result in organic_results:
                    if result.get('asin') == asin:
                        product_result = result
                        break
                if not product_result and organic_results:
                    product_result = organic_results[0]
                if product_result:
                    title = product_result.get('title', '')
                    price = product_result.get('price', '₹Special Price')
                    rating = product_result.get('rating', '⭐⭐⭐⭐☆')
                    thumbnail = product_result.get('thumbnail', '')
                    return {
                        'asin': asin,
                        'title': title[:100] + '...' if len(title) > 100 else title,
                        'image': thumbnail or f"https://m.media-amazon.com/images/I/{asin}._AC_SL1500_.jpg",
                        'price': price,
                        'rating': rating,
                        'category': 'electronics',
                        'source': 'serpapi'
                    }
        except Exception:
            logger.error(traceback.format_exc())
        return self.get_fallback_product_info(asin)

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
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                import base64
                content = base64.b64decode(response.json()['content']).decode('utf-8')
                data = json.loads(content)
                return data.get('products', [])
        except Exception:
            pass
        return []

    async def commit_to_github(self, file_path, content):
        url = f"https://api.github.com/repos/{WEBSITE_REPO}/contents/{file_path}"
        headers = {'Authorization': f'token {GITHUB_TOKEN}'}
        sha = None
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            sha = response.json()['sha']

        import base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

        commit_data = {
            'message': f'Auto-update: {SESSION_TYPE} - Index {self.current_index}',
            'content': encoded_content,
            'branch': 'main'
        }
        if sha:
            commit_data['sha'] = sha

        response = requests.put(url, headers=headers, json=commit_data, timeout=30)
        return response.status_code in [200, 201]

    def get_next_links(self, count):
        result = []
        for _ in range(count):
            if not self.links:
                break
            if self.current_index >= len(self.links):
                self.current_index = 0
            result.append(self.links[self.current_index])
            self.current_index += 1
        self.save_progress()
        return result

    async def run(self):
        logger.info("Posting product links to website (no Telegram)...")
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
                'link_index': self.current_index-1
            }
            website_products.insert(0, product)

        updated_data = {
            "last_updated": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            "total_products": len(website_products),
            "products": website_products
        }
        await self.commit_to_github('data/products.json', json.dumps(updated_data, indent=2))
        logger.info(f"Posted {len(next_links)} products. Now total {len(website_products)} on website.")

async def main():
    bot = WebsiteAffiliateBot()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
