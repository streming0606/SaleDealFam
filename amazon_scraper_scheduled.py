#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re
import random
from datetime import datetime
import pytz
from fake_useragent import UserAgent

class ScheduledAmazonScraper:
    def __init__(self):
        self.affiliate_tag = os.environ.get('AMAZON_TAG', 'dealfam-21')
        self.scrape_mode = os.environ.get('SCRAPE_MODE', 'trending')
        self.max_links = int(os.environ.get('MAX_LINKS', 25))
        self.search_keywords = os.environ.get('SEARCH_KEYWORDS', 'electronics').split(',')
        
        # Initialize user agent for realistic requests
        self.ua = UserAgent()
        self.session = requests.Session()
        
        # Load existing links
        self.existing_links = self.load_existing_links()
        self.new_links = []
        
        print(f"🚀 Amazon Scraper initialized:")
        print(f"   📊 Mode: {self.scrape_mode}")
        print(f"   🎯 Target: {self.max_links} links")
        print(f"   📦 Existing links: {len(self.existing_links)}")
        print(f"   🏷️ Affiliate tag: {self.affiliate_tag}")
    
    def get_headers(self):
        """Generate realistic headers for requests"""
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def load_existing_links(self):
        """Load existing links from file"""
        try:
            if os.path.exists('data/amazon_links.json'):
                with open('data/amazon_links.json', 'r') as f:
                    data = json.load(f)
                    return set(data.get('links', []))
        except Exception as e:
            print(f"⚠️ Error loading existing links: {e}")
        return set()
    
    def create_affiliate_link(self, asin):
        """Create affiliate link from ASIN"""
        return f"https://www.amazon.in/dp/{asin}?tag={self.affiliate_tag}"
    
    def extract_asin_from_url(self, url):
        """Extract ASIN from Amazon URL"""
        asin_patterns = [
            r'/dp/([A-Z0-9]{10})',
            r'/product/([A-Z0-9]{10})',
            r'asin=([A-Z0-9]{10})',
            r'/([A-Z0-9]{10})/'
        ]
        
        for pattern in asin_patterns:
            match = re.search(pattern, url)
            if match and len(match.group(1)) == 10:
                return match.group(1)
        return None
    
    def scrape_trending_products(self):
        """Scrape trending/popular products"""
        print("🔥 Scraping trending products...")
        
        for keyword in self.search_keywords:
            if len(self.new_links) >= self.max_links:
                break
                
            keyword = keyword.strip()
            print(f"🔍 Searching for: {keyword}")
            
            try:
                # Amazon India search URL
                search_url = f"https://www.amazon.in/s?k={keyword.replace(' ', '+')}&sort=popularity-rank"
                
                response = self.session.get(search_url, headers=self.get_headers(), timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find product containers
                products = soup.find_all('div', {'data-component-type': 's-search-result'})
                
                for product in products[:10]:  # Top 10 per keyword
                    if len(self.new_links) >= self.max_links:
                        break
                    
                    asin = product.get('data-asin')
                    if asin and len(asin) == 10:
                        affiliate_link = self.create_affiliate_link(asin)
                        
                        if affiliate_link not in self.existing_links:
                            self.new_links.append(affiliate_link)
                            print(f"✅ New trending: {affiliate_link}")
                
                # Rate limiting
                time.sleep(random.uniform(2, 4))
                
            except Exception as e:
                print(f"❌ Error scraping {keyword}: {e}")
    
    def scrape_categories(self):
        """Scrape from specific Amazon categories"""
        print("🏷️ Scraping category bestsellers...")
        
        categories = [
            ('Electronics', 'https://www.amazon.in/gp/bestsellers/electronics'),
            ('Computers', 'https://www.amazon.in/gp/bestsellers/computers'), 
            ('Mobile Phones', 'https://www.amazon.in/gp/bestsellers/electronics/1389401031'),
            ('Home & Kitchen', 'https://www.amazon.in/gp/bestsellers/kitchen'),
            ('Fashion', 'https://www.amazon.in/gp/bestsellers/apparel')
        ]
        
        for category_name, category_url in categories:
            if len(self.new_links) >= self.max_links:
                break
                
            print(f"📂 Scraping: {category_name}")
            
            try:
                response = self.session.get(category_url, headers=self.get_headers(), timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find bestseller product links
                product_links = soup.find_all('a', href=True)
                
                for link in product_links[:15]:  # Top 15 per category
                    if len(self.new_links) >= self.max_links:
                        break
                    
                    href = link.get('href', '')
                    asin = self.extract_asin_from_url(href)
                    
                    if asin:
                        affiliate_link = self.create_affiliate_link(asin)
                        
                        if affiliate_link not in self.existing_links:
                            self.new_links.append(affiliate_link)
                            print(f"✅ New category: {affiliate_link}")
                
                time.sleep(random.uniform(3, 5))
                
            except Exception as e:
                print(f"❌ Error scraping {category_name}: {e}")
    
    def scrape_deals(self):
        """Scrape current deals and offers"""
        print("💰 Scraping deals and offers...")
        
        deals_urls = [
            'https://www.amazon.in/deals',
            'https://www.amazon.in/gp/goldbox',
            'https://www.amazon.in/electronics-deals/s?rh=n%3A976419031'
        ]
        
        for deals_url in deals_urls:
            if len(self.new_links) >= self.max_links:
                break
                
            try:
                response = self.session.get(deals_url, headers=self.get_headers(), timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find deal products
                deal_elements = soup.find_all(['div', 'a'], href=True)
                
                for element in deal_elements[:20]:
                    if len(self.new_links) >= self.max_links:
                        break
                    
                    href = element.get('href', '')
                    asin = self.extract_asin_from_url(href)
                    
                    if asin:
                        affiliate_link = self.create_affiliate_link(asin)
                        
                        if affiliate_link not in self.existing_links:
                            self.new_links.append(affiliate_link)
                            print(f"✅ New deal: {affiliate_link}")
                
                time.sleep(random.uniform(2, 4))
                
            except Exception as e:
                print(f"❌ Error scraping deals: {e}")
    
    def save_links(self):
        """Save all links (existing + new) to file"""
        os.makedirs('data', exist_ok=True)
        
        # Combine existing and new links
        all_links = list(self.existing_links) + self.new_links
        all_links = list(dict.fromkeys(all_links))  # Remove duplicates while preserving order
        
        # Prepare data
        ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        links_data = {
            'links': all_links,
            'total_count': len(all_links),
            'new_links_added': len(self.new_links),
            'last_scraped': ist_now.isoformat(),
            'scrape_mode': self.scrape_mode,
            'affiliate_tag': self.affiliate_tag,
            'search_keywords': self.search_keywords
        }
        
        # Save to file
        with open('data/amazon_links.json', 'w') as f:
            json.dump(links_data, f, indent=2)
        
        print(f"💾 Saved {len(all_links)} total links ({len(self.new_links)} new)")
        return len(self.new_links)
    
    def run_scraper(self):
        """Main scraper execution"""
        ist_time = datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')
        print(f"🚀 Starting scheduled scraper at {ist_time}")
        
        try:
            if self.scrape_mode == 'trending':
                self.scrape_trending_products()
            elif self.scrape_mode == 'categories':
                self.scrape_categories()
            elif self.scrape_mode == 'bestsellers':
                self.scrape_categories()  # Same as categories
            elif self.scrape_mode == 'deals':
                self.scrape_deals()
            else:
                # Default: mixed scraping
                self.scrape_trending_products()
                if len(self.new_links) < self.max_links:
                    self.scrape_categories()
            
            # Save results
            new_count = self.save_links()
            
            print(f"🎉 Scraping completed!")
            print(f"   ✅ New links found: {new_count}")
            print(f"   📊 Total links in database: {len(self.existing_links) + new_count}")
            
            return new_count
            
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            return 0

if __name__ == "__main__":
    scraper = ScheduledAmazonScraper()
    scraper.run_scraper()
