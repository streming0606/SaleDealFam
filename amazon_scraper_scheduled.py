#!/usr/bin/env python3
import requests
import json
import os
import time
import re
from datetime import datetime
import pytz

class SimpleAmazonScraper:
    def __init__(self):
        self.affiliate_tag = os.environ.get('AMAZON_TAG', 'dealfam-21')
        self.max_links = int(os.environ.get('MAX_LINKS', 10))
        self.collected_links = []
        
        print(f"🚀 Simple Amazon Scraper initialized")
        print(f"🏷️ Affiliate tag: {self.affiliate_tag}")
        print(f"🎯 Target links: {self.max_links}")
    
    def create_sample_links(self):
        """Create sample affiliate links for testing"""
        sample_asins = [
            'B08N5WRWNW', 'B07HGJKJL2', 'B08CFSZLQ4', 'B08BHBQKP7', 
            'B07DJ2K9GS', 'B08XYZ123', 'B09ABC456', 'B07DEF789',
            'B08GHI012', 'B09JKL345', 'B07MNO678', 'B08PQR901'
        ]
        
        for i, asin in enumerate(sample_asins):
            if i >= self.max_links:
                break
            affiliate_link = f"https://www.amazon.in/dp/{asin}?tag={self.affiliate_tag}"
            self.collected_links.append(affiliate_link)
            print(f"✅ Generated: {affiliate_link}")
    
    def save_links(self):
        """Save links to JSON file"""
        os.makedirs('data', exist_ok=True)
        
        ist_time = datetime.now(pytz.timezone('Asia/Kolkata'))
        
        links_data = {
            'links': self.collected_links,
            'total_count': len(self.collected_links),
            'last_scraped': ist_time.isoformat(),
            'scrape_mode': 'sample',
            'affiliate_tag': self.affiliate_tag
        }
        
        with open('data/amazon_links.json', 'w') as f:
            json.dump(links_data, f, indent=2)
        
        print(f"💾 Saved {len(self.collected_links)} links to data/amazon_links.json")
    
    def run_scraper(self):
        """Main scraper function"""
        try:
            print("🚀 Starting sample link generation...")
            self.create_sample_links()
            self.save_links()
            print("✅ Scraper completed successfully!")
            return True
        except Exception as e:
            print(f"❌ Scraper error: {e}")
            return False

if __name__ == "__main__":
    scraper = SimpleAmazonScraper()
    success = scraper.run_scraper()
    exit(0 if success else 1)
