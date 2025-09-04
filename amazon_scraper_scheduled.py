#!/usr/bin/env python3
import json
import os
from datetime import datetime

print("🚀 Starting Amazon Link Generator...")

try:
    # Get environment variables
    affiliate_tag = os.environ.get('AMAZON_TAG', 'dealfam-21')
    max_links = int(os.environ.get('MAX_LINKS', '10'))
    
    print(f"🏷️ Affiliate tag: {affiliate_tag}")
    print(f"🎯 Max links: {max_links}")
    
    # Sample Amazon ASINs (real products)
    sample_products = [
        'B08N5WRWNW',  # iPhone 12
        'B07HGJKJL2',  # Samsung Galaxy
        'B08CFSZLQ4',  # OnePlus
        'B08BHBQKP7',  # iPad
        'B07DJ2K9GS',  # MacBook
        'B08XYZ123',  # Headphones
        'B09ABC456',  # Speaker
        'B07DEF789',  # Laptop
        'B08GHI012',  # Watch
        'B09JKL345',  # Camera
        'B07MNO678',  # Gaming
        'B08PQR901'   # Home
    ]
    
    # Generate affiliate links
    affiliate_links = []
    for i, asin in enumerate(sample_products):
        if i >= max_links:
            break
        link = f"https://www.amazon.in/dp/{asin}?tag={affiliate_tag}"
        affiliate_links.append(link)
        print(f"✅ Generated: {link}")
    
    # Create data directory
    if not os.path.exists('data'):
        os.makedirs('data')
        print("📁 Created data directory")
    
    # Save to JSON
    data = {
        "links": affiliate_links,
        "total_count": len(affiliate_links),
        "last_scraped": datetime.now().isoformat(),
        "affiliate_tag": affiliate_tag
    }
    
    with open('data/amazon_links.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"💾 Saved {len(affiliate_links)} links to data/amazon_links.json")
    print("✅ SUCCESS: Link generation completed!")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    exit(1)

print("🎉 All done!")
exit(0)
