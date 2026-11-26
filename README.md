# Deal Finder — Smart E-Commerce Price Tracker & Comparator

A full-stack price comparison and historical price-tracking web application for **Amazon.in** and **Flipkart**. Search by product name or paste any product URL to compare live listings across stores, rank deals using a weighted scoring algorithm, and track price history graphs over time.

---

## Key Features & Techniques

- **Multi-Store Scraping (`curl_cffi` + `BeautifulSoup4`):**
  - Uses `curl_cffi` with browser TLS fingerprint impersonation (`impersonate="chrome"`) alongside `BeautifulSoup4` HTML parsing to retrieve live product titles, prices, ratings, review counts, discounts, stock availability, and product images from Amazon.in and Flipkart without heavy headless-browser overhead.
  - Normalizes Indian Rupee (`₹`) price strings and product URLs across stores.
- **Dual Search & Comparison Modes:**
  - **Product Name Search (`GET /search`):** Aggregates top results from both Amazon.in and Flipkart, renders a side-by-side price comparison bar chart, and supports sorting by **Featured (Deal Score)**, **Lowest Price**, **Highest Price**, and **Alphabetical (A–Z)**.
  - **Product URL Comparison (`POST /compare-url`):** Extracts product metadata from a pasted Amazon or Flipkart link and searches competing listings across stores without automatically writing to the database.
- **Weighted Deal Scoring Algorithm:**
  - Ranks listings using a composite score combining keyword/title token relevance, price competitiveness relative to the result-set average, customer star rating, review volume, and discount percentage.
- **Historical Price Tracking & Auto-Refresh (`POST /track`, `GET /products`, `POST /refresh-prices`):**
  - Upserts tracked products and store listings into Supabase PostgreSQL, appends timestamped checkpoints to `price_history`, refreshes live prices on demand, and plots historical trends via an interactive Recharts area chart.

---

## Tech Stack

- **Frontend:** Next.js (App Router, React 19, TypeScript), Tailwind CSS v4, Recharts
- **Backend:** FastAPI (Python), Uvicorn, BeautifulSoup4, `curl_cffi`, `python-dotenv`
- **Database:** Supabase (PostgreSQL)

---

## Project Structure

```text
deal-finder/
├── main.py                  # FastAPI server, scrapers, deal-scoring logic & REST endpoints
├── database.py              # Supabase client & database helper utilities
├── main_scraper.py          # Standalone scraper utilities
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── start-app.bat            # Windows one-click launcher (starts Backend, Frontend & Browser)
└── deal-finder-frontend/    # Next.js frontend application
    ├── app/
    │   └── page.tsx         # Main dashboard UI (Search, Comparison Charts & Price History)
    └── package.json
```

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Health check confirming the FastAPI backend is running |
| `GET` | `/search?q=<query>` | Searches Amazon.in & Flipkart, scores deals, and returns sorted listings |
| `POST` | `/compare-url` | Parses a pasted product URL and fetches matching store comparisons |
| `POST` | `/track` | Saves a product listing to Supabase and records an initial price checkpoint |
| `GET` | `/products` | Retrieves all tracked products with nested store listings and price history |
| `POST` | `/refresh-prices` | Re-scrapes live prices for tracked listings and appends new history points |

---

## Database Setup (Supabase PostgreSQL)

1. Create a new project in [Supabase](https://supabase.com).
2. Open **SQL Editor -> New query**, paste the schema below, and click **Run**:

```sql
create extension if not exists "pgcrypto";

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category text not null default 'Electronics',
  image_url text,
  user_id text not null default 'guest',
  created_at timestamptz not null default now()
);

create table if not exists public.store_listings (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id) on delete cascade,
  store_name text not null,
  product_url text not null unique,
  current_price numeric(12, 2) not null,
  in_stock boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.price_history (
  id uuid primary key default gen_random_uuid(),
  listing_id uuid not null references public.store_listings(id) on delete cascade,
  price numeric(12, 2) not null,
  recorded_at timestamptz not null default now()
);

create index if not exists idx_products_user_id on public.products(user_id);
create index if not exists idx_store_listings_product_id on public.store_listings(product_id);
create index if not exists idx_price_history_listing_id on public.price_history(listing_id);
create index if not exists idx_price_history_recorded_at on public.price_history(listing_id, recorded_at);
```

---

## Local Setup & Running the App

### 1. Environment Variables
Copy `.env.example` to `.env` in the root folder (`deal-finder/.env`) and add your Supabase credentials:
```env
```

### 2. First-Time Installation

**Backend (FastAPI):**
```bash
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash (or venv\Scripts\activate.bat in cmd)
pip install -r requirements.txt
```

**Frontend (Next.js):**
```bash
cd deal-finder-frontend
npm install
cd ..
```

### 3. Running the Application

- **Option A — One-Click Windows Launcher:** Double-click `start-app.bat` in the root folder to start FastAPI (`http://127.0.0.1:8000`), start Next.js (`http://localhost:3000`), and open the dashboard in your browser.
- **Option B — Manual Startup (Two Terminals):**
  - Terminal 1 (Root): `uvicorn main:app --reload`
  - Terminal 2 (`deal-finder-frontend/`): `npm run dev`

---

## Team & Guidance

- **Developed by:** Niyati Shah, M. Sufiyan Makandar, and Amogh Pawar
- **Under the guidance of:** Varun Sarvade
