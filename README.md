# Deal Finder — Smart E-Commerce Price Tracker & Comparator

A full-stack price comparison and historical price-tracking web application for **Amazon.in** and **Flipkart**. Search by product name or paste any product URL to compare live listings across stores, rank deals by value, and track price history graphs over time.

## Key Features

- **Search by Product Name:** Compares top listings across Amazon.in and Flipkart in an interactive bar chart with sorting (**Lowest Price**, **Highest Price**, **Featured**, **Alphabetical A–Z**).
- **Compare by Product URL (`/compare-url`):** Fetches matching listings across stores without automatically saving to the database.
- **Smart Deal Scoring:** Ranks products using title relevance, price competitiveness, star rating, review count, and discount percentage.
- **Price History Tracking (`/track` & `/refresh-prices`):** Saves tracked items in Supabase PostgreSQL and plots price trends over time.

## Tech Stack

- **Frontend:** Next.js (App Router, TypeScript), Tailwind CSS, Recharts
- **Backend:** FastAPI (Python), BeautifulSoup4, `curl_cffi`
- **Database:** Supabase (PostgreSQL)

## Local Setup

### Backend (FastAPI)
1. Create and activate a virtual environment: `python -m venv venv` then `source venv/Scripts/activate`
2. Install dependencies: `pip install -r requirements.txt`
3. Add `SUPABASE_URL` and `SUPABASE_KEY` in a root `.env` file.
4. Start the server: `uvicorn main:app --reload`

### Frontend (Next.js)
1. Open `buyhatke-frontend`: `cd buyhatke-frontend`
2. Install packages: `npm install`
3. Start dev server: `npm run dev`

## Team & Guidance

- **Team:** Niyati Shah, M. Sufiyan Makandar & Amogh Pawar
- **Under the guidance of:** Varun Sarvade
