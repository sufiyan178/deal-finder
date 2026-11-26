import os
import asyncio
import re
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def scrape_and_save(url: str):
    print(f"Starting scrape for: {url}")
    
    async with async_playwright() as p:
        # Launch browser with headless=False so you can see it run and avoid bot blocks
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            extra_http_headers={
                "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7"
            }
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            
            # Debug: print the actual browser tab title
            page_title = await page.title()
            print(f"Browser Tab Title: {page_title}")
            
            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            title = "Unknown Product"
            price = 0.0
            image_url = None
            store_name = "unknown"
            
            # --- AMAZON PARSER ---
            if "amazon" in url:
                store_name = "amazon"
                title_el = soup.select_one("#productTitle")
                if title_el:
                    title = title_el.get_text(strip=True)
                    
                # Comprehensive Amazon price selectors
                price_el = (
                    soup.select_one("#corePriceDisplay_desktop_feature_div .a-price-whole")
                    or soup.select_one("#corePrice_feature_div .a-price-whole")
                    or soup.select_one(".a-price .a-offscreen")
                    or soup.select_one(".a-price-whole")
                )
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    price = float(re.sub(r'[^\d.]', '', price_text))
                    
                img_el = soup.select_one("#landingImage")
                if img_el:
                    image_url = img_el.get("src")

            # --- FLIPKART PARSER ---
            elif "flipkart" in url:
                store_name = "flipkart"
                title_el = soup.select_one("span.B_NuCI") or soup.select_one("h1._6EBuvT")
                if title_el:
                    title = title_el.get_text(strip=True)
                    
                price_el = soup.select_one("div._30jeq3") or soup.select_one("div.Nx9bqj")
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    price = float(re.sub(r'[^\d.]', '', price_text))
                    
                img_el = soup.select_one("img._396cs4") or soup.select_one("img.DByuf4")
                if img_el:
                    image_url = img_el.get("src")

            print(f"Extracted -> Title: {title} | Price: {price} | Store: {store_name}")
            
            if price == 0.0 or title == "Unknown Product":
                print("Failed to extract valid product details. Check selectors or look at the browser window for a captcha.")
                return

            # --- DATABASE INSERTION LOGIC ---
            product_res = supabase.table("products").insert({
                "name": title,
                "category": "Electronics",
                "image_url": image_url
            }).execute()
            
            product_id = product_res.data[0]["id"]
            print(f"Saved product to DB with ID: {product_id}")

            listing_res = supabase.table("store_listings").insert({
                "product_id": product_id,
                "store_name": store_name,
                "product_url": url,
                "current_price": price,
                "in_stock": True
            }).execute()
            
            listing_id = listing_res.data[0]["id"]
            print(f"Saved store listing to DB with ID: {listing_id}")

            supabase.table("price_history").insert({
                "listing_id": listing_id,
                "price": price
            }).execute()
            print("Logged initial price into price_history table successfully!")

        except Exception as e:
            print(f"Scraping or Database error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    # Replace this with any active Amazon India or Flipkart product link of your choice
    test_url = "https://www.amazon.in/gp/product/B0GDPT78SG/ref=ewc_pr_img_1?smid=A3KZ28HCTE4XHB&th=1" 
    asyncio.run(scrape_and_save(test_url))