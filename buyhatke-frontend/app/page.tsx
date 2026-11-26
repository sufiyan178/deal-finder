"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

const API_BASE = "http://127.0.0.1:8000";

interface PriceHistoryEntry {
  id: string;
  price: number;
  recorded_at: string;
}

interface StoreListing {
  id: string;
  store_name: string;
  product_url: string;
  current_price: number;
  in_stock: boolean;
  price_history: PriceHistoryEntry[];
}

interface Product {
  id: string;
  name: string;
  category: string;
  created_at?: string;
  image_url: string | null;
  store_listings: StoreListing[];
}

interface SearchListing {
  title: string;
  store: string;
  price: number;
  mrp: number | null;
  rating: number;
  reviews: number;
  url: string;
  image_url: string | null;
  deal_score: number;
  relevance_score?: number;
}

interface SearchResponse {
  status: string;
  query: string;
  count: number;
  amazon_count?: number;
  flipkart_count?: number;
  average_price: number;
  best_deal: SearchListing | null;
  results: SearchListing[];
  diagnostics?: string[];
}

interface RealHistoryPoint {
  dateLabel: string;
  fullDate: string;
  price: number;
}

type SortOption = "price-asc" | "price-desc" | "featured" | "alpha-asc";

const formatINR = (val: unknown): string => {
  const num = Number(val ?? 0);
  return `₹${Number.isNaN(num) ? 0 : Math.round(num).toLocaleString("en-IN")}`;
};

const formatCompactINR = (val: number): string => {
  if (val === 0) return "₹0";
  if (val >= 1000) return `₹${Math.round(val / 1000)}K`;
  return `₹${val}`;
};

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    payload: RealHistoryPoint;
  }>;
}

function PriceHistoryTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;

  return (
    <div className="bg-white text-slate-900 rounded-xl shadow-lg border border-slate-200 px-4 py-3 min-w-[200px]">
      <p className="text-xs font-medium text-slate-500 mb-1.5">
        {point.fullDate}
      </p>
      <div className="flex items-center justify-between gap-4 text-sm">
        <span className="text-slate-600">Price:</span>
        <span className="font-bold text-slate-950">
          {formatINR(point.price)}
        </span>
      </div>
    </div>
  );
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<"search" | "tracked">("search");

  // Search by name + Search by URL inputs inside Product Search
  const [searchQuery, setSearchQuery] = useState("");
  const [urlInput, setUrlInput] = useState("");
  const [searching, setSearching] = useState(false);
  const [comparingUrl, setComparingUrl] = useState(false);
  const [searchData, setSearchData] = useState<SearchResponse | null>(null);
  const [searchError, setSearchError] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOption>("price-asc");
  const [trackingUrl, setTrackingUrl] = useState<string | null>(null);

  const [refreshingAll, setRefreshingAll] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(
    null,
  );
  const [selectedListingId, setSelectedListingId] = useState<string | null>(
    null,
  );

  const hasAutoRefreshed = useRef(false);

  const fetchProducts = async (preferredProductId?: string | null) => {
    try {
      const res = await fetch(`${API_BASE}/products`);
      const json = await res.json();
      if (json.status === "success" && Array.isArray(json.data)) {
        const sortedProducts: Product[] = [...json.data].sort((a, b) => {
          const aTime = a.created_at || "";
          const bTime = b.created_at || "";
          return bTime.localeCompare(aTime);
        });

        setProducts(sortedProducts);

        if (preferredProductId) {
          setSelectedProductId(preferredProductId);
        } else if (sortedProducts.length > 0) {
          setSelectedProductId((prev) =>
            prev && sortedProducts.some((p) => p.id === prev)
              ? prev
              : sortedProducts[0].id,
          );
        }
      }
    } catch (err) {
      console.error("Failed to fetch tracked products:", err);
    }
  };

  useEffect(() => {
    const initAndAutoRefresh = async () => {
      await fetchProducts();
      if (!hasAutoRefreshed.current) {
        hasAutoRefreshed.current = true;
        try {
          setRefreshingAll(true);
          const res = await fetch(`${API_BASE}/refresh-prices`, {
            method: "POST",
          });
          if (res.ok) {
            await fetchProducts();
          }
        } catch {
          // Ignore background refresh error when list is empty
        } finally {
          setRefreshingAll(false);
        }
      }
    };
    initAndAutoRefresh();
  }, []);

  const runKeywordSearch = async (keyword: string) => {
    const trimmed = keyword.trim();
    if (!trimmed) return;

    setSearching(true);
    setSearchError("");
    setSearchData(null);

    try {
      const res = await fetch(
        `${API_BASE}/search?q=${encodeURIComponent(trimmed)}&per_store=5`,
      );
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || "Search failed");
      }
      setSearchData(json);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to search products.";
      setSearchError(msg);
    } finally {
      setSearching(false);
    }
  };

  // Compares a pasted URL across Amazon & Flipkart WITHOUT tracking/saving to DB
  const handleCompareByUrl = async (targetUrl: string) => {
    const cleaned = targetUrl.trim();
    if (!cleaned) return;

    const normalizedTarget = /^https?:\/\//i.test(cleaned)
      ? cleaned
      : `https://${cleaned}`;

    setComparingUrl(true);
    setSearchError("");
    setSearchData(null);

    try {
      const res = await fetch(`${API_BASE}/compare-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalizedTarget }),
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || `Failed with status ${res.status}`);
      }
      setSearchData(json);
    } catch (err: unknown) {
      const rawMsg =
        err instanceof Error ? err.message : "Failed to compare product URL.";
      const friendlyMsg =
        rawMsg === "Failed to fetch"
          ? "Cannot reach backend at http://127.0.0.1:8000. Make sure FastAPI is running."
          : rawMsg;
      setSearchError(friendlyMsg);
    } finally {
      setComparingUrl(false);
    }
  };

  // Only runs when user explicitly clicks "Track & Graph" on a product card
  const handleTrackProduct = async (targetUrl: string) => {
    const cleaned = targetUrl.trim();
    if (!cleaned) return;

    const normalizedTarget = /^https?:\/\//i.test(cleaned)
      ? cleaned
      : `https://${cleaned}`;

    setTrackingUrl(normalizedTarget);
    setStatusMessage("");

    try {
      const res = await fetch(`${API_BASE}/track`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalizedTarget }),
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(
          json.detail || `Request failed with status ${res.status}`,
        );
      }

      const data = json.data;
      setStatusMessage(
        `Tracked: ${data.title} (Best price: ${formatINR(data.best_offer?.price ?? data.price)})`,
      );

      const newProductId = data?.product_id || null;
      await fetchProducts(newProductId);
      if (newProductId) {
        setSelectedProductId(newProductId);
        setSelectedListingId(null);
      }
      setActiveTab("tracked");
    } catch (err: unknown) {
      const rawMsg =
        err instanceof Error ? err.message : "Error tracking product";
      setStatusMessage(`Error: ${rawMsg}`);
    } finally {
      setTrackingUrl(null);
    }
  };

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await runKeywordSearch(searchQuery);
  };

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await handleCompareByUrl(urlInput);
  };

  const handleDeleteProduct = async (
    e: React.MouseEvent,
    productId: string,
    productName: string,
  ) => {
    e.stopPropagation();
    setDeletingId(productId);
    setStatusMessage("");

    try {
      const res = await fetch(`${API_BASE}/products/${productId}`, {
        method: "DELETE",
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || "Failed to remove product");
      }

      const updated = products.filter((p) => p.id !== productId);
      setProducts(updated);
      if (selectedProductId === productId) {
        setSelectedProductId(updated.length > 0 ? updated[0].id : null);
        setSelectedListingId(null);
      }
      setStatusMessage(`Removed "${productName}" from tracked products.`);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to remove product";
      setStatusMessage(`Error: ${msg}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleRefreshAllPrices = async () => {
    setRefreshingAll(true);
    setStatusMessage("Checking live prices across tracked items...");
    try {
      const res = await fetch(`${API_BASE}/refresh-prices`, { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || "Failed to refresh prices");
      }
      setStatusMessage(
        `Updated prices for ${json.refreshed_count} tracked listing(s).`,
      );
      await fetchProducts(selectedProductId);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Refresh failed";
      setStatusMessage(`Error: ${msg}`);
    } finally {
      setRefreshingAll(false);
    }
  };

  const sortedSearchResults = useMemo(() => {
    if (!searchData?.results) return [];
    const list = [...searchData.results];

    switch (sortOrder) {
      case "price-asc":
        return list.sort((a, b) => a.price - b.price);
      case "price-desc":
        return list.sort((a, b) => b.price - a.price);
      case "featured":
        return list.sort((a, b) => {
          const scoreDiff = (b.deal_score || 0) - (a.deal_score || 0);
          if (scoreDiff !== 0) return scoreDiff;
          return (b.relevance_score || 0) - (a.relevance_score || 0);
        });
      case "alpha-asc":
        return list.sort((a, b) =>
          a.title.localeCompare(b.title, undefined, { sensitivity: "base" }),
        );
      default:
        return list;
    }
  }, [searchData, sortOrder]);

  const selectedProduct =
    products.find((p) => p.id === selectedProductId) || products[0] || null;

  const sortedProductListings = useMemo(() => {
    if (!selectedProduct?.store_listings) return [];
    return [...selectedProduct.store_listings].sort(
      (a, b) => (a.current_price || 0) - (b.current_price || 0),
    );
  }, [selectedProduct]);

  const activeListing =
    sortedProductListings.find((l) => l.id === selectedListingId) ||
    sortedProductListings[0] ||
    null;

  const realHistorySeries: RealHistoryPoint[] = useMemo(() => {
    if (!activeListing?.price_history) return [];

    const sorted = [...activeListing.price_history].sort(
      (a, b) =>
        new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime(),
    );

    return sorted.map((entry) => {
      const d = new Date(entry.recorded_at);
      return {
        dateLabel: d.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        }),
        fullDate: d.toLocaleString("en-US", {
          weekday: "short",
          day: "numeric",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        }),
        price: entry.price,
      };
    });
  }, [activeListing]);

  const priceStats = useMemo(() => {
    if (realHistorySeries.length === 0) {
      return { avgPrice: 0, currentPrice: 0, diffPct: 0, isLower: true };
    }
    const avg =
      realHistorySeries.reduce((acc, item) => acc + item.price, 0) /
      realHistorySeries.length;
    const current = realHistorySeries[realHistorySeries.length - 1].price;
    const pct = avg > 0 ? Math.abs(((avg - current) / avg) * 100) : 0;
    return {
      avgPrice: Math.round(avg),
      currentPrice: current,
      diffPct: Number(pct.toFixed(2)),
      isLower: current <= avg,
    };
  }, [realHistorySeries]);

  const comparisonChartData = sortedSearchResults.map((item, idx) => ({
    name: `#${idx + 1} (${item.store === "amazon" ? "AMZ" : "FLK"})`,
    price: item.price,
  }));

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 p-6 md:p-10 flex flex-col">
      <div className="max-w-7xl w-full mx-auto space-y-8 flex-1">
        <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-6">
          <div>
            <h1 className="text-3xl font-bold text-emerald-400">
              BuyHatke Smart Price Tracker
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Compare prices by product name or link across Amazon and Flipkart,
              then track any deal.
            </p>
          </div>

          <div className="flex gap-2 bg-slate-900 p-1.5 rounded-xl border border-slate-800">
            <button
              onClick={() => setActiveTab("search")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition cursor-pointer ${
                activeTab === "search"
                  ? "bg-emerald-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Product Search
            </button>
            <button
              onClick={() => setActiveTab("tracked")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition cursor-pointer ${
                activeTab === "tracked"
                  ? "bg-emerald-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Tracked &amp; Graph ({products.length})
            </button>
          </div>
        </header>

        {statusMessage && (
          <div
            className={`border px-4 py-3 rounded-xl text-sm flex justify-between items-center ${
              statusMessage.startsWith("Error:")
                ? "bg-red-950/50 border-red-800/70 text-red-200"
                : "bg-slate-900 border-emerald-500/40 text-emerald-200"
            }`}
          >
            <span>{statusMessage}</span>
            <button
              onClick={() => setStatusMessage("")}
              className="text-slate-400 hover:text-white text-xs ml-4 cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        {activeTab === "search" && (
          <div className="space-y-8">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <form
                onSubmit={handleSearchSubmit}
                className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-2.5"
              >
                <label
                  htmlFor="product-name-input"
                  className="block text-xs font-semibold uppercase tracking-wider text-emerald-400"
                >
                  Search by Product Name
                </label>
                <div className="flex flex-col sm:flex-row gap-2.5">
                  <input
                    id="product-name-input"
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="e.g., ASUS TUF, Hot Wheels, Sony headphones..."
                    className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                  />
                  <button
                    type="submit"
                    disabled={searching || comparingUrl}
                    className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition cursor-pointer shrink-0"
                  >
                    {searching ? "Searching..." : "Search"}
                  </button>
                </div>
              </form>

              <form
                onSubmit={handleUrlSubmit}
                className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-2.5"
              >
                <label
                  htmlFor="product-url-input"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-300"
                >
                  Search &amp; Compare by Product URL
                </label>
                <div className="flex flex-col sm:flex-row gap-2.5">
                  <input
                    id="product-url-input"
                    type="text"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder="Paste Amazon or Flipkart product link to compare..."
                    className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                  />
                  <button
                    type="submit"
                    disabled={comparingUrl || searching}
                    className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-emerald-300 border border-slate-700 text-sm font-semibold px-5 py-2.5 rounded-xl transition cursor-pointer shrink-0"
                  >
                    {comparingUrl ? "Comparing..." : "Search URL"}
                  </button>
                </div>
              </form>
            </div>

            {searchError && (
              <div className="bg-red-950/60 border border-red-800 text-red-200 px-4 py-3 rounded-xl text-sm">
                {searchError}
              </div>
            )}

            {searchData && !searchData.best_deal && (
              <div className="bg-amber-950/40 border border-amber-700/50 text-amber-200 px-5 py-4 rounded-2xl text-sm">
                No listings returned for &ldquo;{searchData.query}&rdquo;.
                {searchData.diagnostics &&
                  searchData.diagnostics.length > 0 && (
                    <p className="text-xs text-amber-300/80 mt-1">
                      {searchData.diagnostics.join(" • ")}
                    </p>
                  )}
              </div>
            )}

            {searchData && searchData.best_deal && (
              <>
                <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                  <h3 className="text-lg font-semibold text-white mb-4 line-clamp-1">
                    Price Comparison for &ldquo;{searchData.query}&rdquo;
                  </h3>
                  <div className="h-72 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={comparisonChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                        <YAxis stroke="#94a3b8" fontSize={12} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#0f172a",
                            borderColor: "#334155",
                            color: "#f8fafc",
                          }}
                          formatter={(value) => [formatINR(value), "Price"]}
                        />
                        <Bar
                          dataKey="price"
                          fill="#00A86B"
                          radius={[6, 6, 0, 0]}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </section>

                <section className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <h3 className="text-lg font-semibold text-white">
                      Ranked Listings ({sortedSearchResults.length})
                    </h3>

                    <div className="flex items-center gap-2.5">
                      <label
                        htmlFor="sort-select"
                        className="text-xs font-medium text-slate-400"
                      >
                        Sort by:
                      </label>
                      <select
                        id="sort-select"
                        value={sortOrder}
                        onChange={(e) =>
                          setSortOrder(e.target.value as SortOption)
                        }
                        className="bg-slate-900 border border-slate-700 hover:border-slate-600 focus:border-emerald-500 focus:outline-none text-slate-100 text-xs font-medium rounded-xl px-3.5 py-2 cursor-pointer"
                      >
                        <option value="price-asc">Lowest Price</option>
                        <option value="price-desc">Highest Price</option>
                        <option value="featured">
                          Featured (Best Deal Score)
                        </option>
                        <option value="alpha-asc">Alphabetical (A – Z)</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3">
                    {sortedSearchResults.map((item, idx) => (
                      <div
                        key={`${item.url}-${idx}`}
                        className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4"
                      >
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-bold bg-slate-800 text-emerald-300 px-2 py-0.5 rounded">
                              #{idx + 1}
                            </span>
                            <span
                              className={`text-xs uppercase font-semibold px-2 py-0.5 rounded ${
                                item.store === "flipkart"
                                  ? "bg-amber-500/15 text-amber-300"
                                  : "bg-emerald-500/15 text-emerald-300"
                              }`}
                            >
                              {item.store}
                            </span>
                            <span className="text-xs text-amber-400">
                              ★ {item.rating} (
                              {item.reviews.toLocaleString("en-IN")})
                            </span>
                            <span className="text-xs text-emerald-400">
                              Score: {item.deal_score}
                            </span>
                          </div>
                          <p className="text-sm font-medium text-slate-100">
                            {item.title}
                          </p>
                        </div>

                        <div className="flex items-center gap-2.5 shrink-0">
                          <span className="text-lg font-bold text-emerald-400 mr-1">
                            {formatINR(item.price)}
                          </span>
                          <button
                            onClick={() => handleTrackProduct(item.url)}
                            disabled={trackingUrl === item.url}
                            className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-3.5 py-2 rounded-lg transition cursor-pointer"
                          >
                            {trackingUrl === item.url
                              ? "Saving..."
                              : "Track & Graph"}
                          </button>
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-3.5 py-2 rounded-lg transition"
                          >
                            Visit Store ↗
                          </a>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </>
            )}
          </div>
        )}

        {activeTab === "tracked" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-white">
                  Tracked Products ({products.length})
                </h2>
                <button
                  onClick={handleRefreshAllPrices}
                  disabled={refreshingAll || products.length === 0}
                  className="bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-emerald-300 text-xs font-medium px-3 py-1.5 rounded-lg transition cursor-pointer"
                >
                  {refreshingAll ? "Updating..." : "Update Now"}
                </button>
              </div>

              {products.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No tracked products yet. Search by name or URL in Product
                  Search and click &ldquo;Track &amp; Graph&rdquo;.
                </p>
              ) : (
                <div className="space-y-2.5 max-h-[480px] overflow-y-auto pr-1">
                  {products.map((product) => {
                    const bestListing = [
                      ...(product.store_listings || []),
                    ].sort(
                      (a, b) => (a.current_price || 0) - (b.current_price || 0),
                    )[0];
                    const isSelected = selectedProduct?.id === product.id;

                    return (
                      <div
                        key={product.id}
                        onClick={() => {
                          setSelectedProductId(product.id);
                          setSelectedListingId(null);
                        }}
                        className={`w-full text-left p-3.5 rounded-xl border transition cursor-pointer ${
                          isSelected
                            ? "bg-emerald-950/40 border-emerald-500"
                            : "bg-slate-950 border-slate-800 hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-medium text-slate-100 line-clamp-2">
                            {product.name}
                          </p>
                          <button
                            type="button"
                            onClick={(e) =>
                              handleDeleteProduct(e, product.id, product.name)
                            }
                            disabled={deletingId === product.id}
                            className="text-xs text-red-400 hover:text-red-300 bg-red-950/40 hover:bg-red-900/50 border border-red-800/50 px-2 py-0.5 rounded transition shrink-0 cursor-pointer"
                          >
                            {deletingId === product.id ? "..." : "Remove"}
                          </button>
                        </div>

                        <div className="flex items-center justify-between mt-2 text-xs">
                          <span className="text-slate-400">
                            {product.store_listings?.length || 0} listing(s)
                          </span>
                          <span className="text-emerald-400 font-bold">
                            Best: {formatINR(bestListing?.current_price || 0)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="lg:col-span-8 space-y-6">
              {selectedProduct && sortedProductListings.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {sortedProductListings.map((listing, idx) => {
                    const isCharted = activeListing?.id === listing.id;
                    return (
                      <div
                        key={listing.id}
                        onClick={() => setSelectedListingId(listing.id)}
                        className={`p-3.5 rounded-xl border transition cursor-pointer flex items-center justify-between gap-3 ${
                          isCharted
                            ? "bg-emerald-950/40 border-emerald-500"
                            : "bg-slate-900 border-slate-800 hover:border-slate-700"
                        }`}
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold bg-slate-800 text-emerald-300 px-2 py-0.5 rounded">
                              #{idx + 1}
                            </span>
                            <span className="text-xs uppercase font-bold text-emerald-400">
                              {listing.store_name}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400 mt-1">
                            {listing.price_history?.length || 0} recorded
                            check(s)
                          </p>
                        </div>

                        <div className="flex items-center gap-2.5">
                          <span className="text-lg font-extrabold text-emerald-400">
                            {formatINR(listing.current_price)}
                          </span>
                          {listing.product_url && (
                            <a
                              href={listing.product_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-2.5 py-1.5 rounded-lg transition"
                            >
                              Visit Store ↗
                            </a>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="bg-white text-slate-900 rounded-2xl shadow-xl border border-slate-200 p-6 flex flex-col justify-between">
                <div className="flex flex-wrap items-center justify-between gap-4 pb-4">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white bg-[#00A86B]">
                      {priceStats.isLower ? "↓" : "↑"}
                    </span>
                    <span className="text-base font-medium text-slate-800">
                      {realHistorySeries.length > 1
                        ? `${priceStats.diffPct}% ${
                            priceStats.isLower ? "lower" : "higher"
                          } than tracked average`
                        : realHistorySeries.length === 1
                          ? `Tracking started ${realHistorySeries[0].dateLabel} • Current: ${formatINR(
                              realHistorySeries[0].price,
                            )}`
                          : "Select or track a product to view price history"}
                    </span>
                  </div>

                  {activeListing?.product_url && (
                    <a
                      href={activeListing.product_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-semibold text-emerald-700 hover:text-emerald-600"
                    >
                      Visit Store ↗
                    </a>
                  )}
                </div>

                <div className="h-[320px] w-full">
                  {realHistorySeries.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={realHistorySeries}
                        margin={{ top: 16, right: 12, left: 8, bottom: 8 }}
                      >
                        <defs>
                          <linearGradient
                            id="realPriceFade"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                          >
                            <stop
                              offset="0%"
                              stopColor="#00A86B"
                              stopOpacity={0.28}
                            />
                            <stop
                              offset="100%"
                              stopColor="#00A86B"
                              stopOpacity={0.03}
                            />
                          </linearGradient>
                        </defs>

                        <CartesianGrid vertical={false} stroke="#f1f5f9" />
                        <XAxis
                          dataKey="dateLabel"
                          axisLine={{ stroke: "#e2e8f0" }}
                          tickLine={false}
                          tick={{ fill: "#334155", fontSize: 12 }}
                        />
                        <YAxis
                          orientation="right"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "#334155", fontSize: 12 }}
                          tickFormatter={formatCompactINR}
                          domain={[
                            0,
                            (dataMax: number) =>
                              Math.max(
                                1000,
                                Math.ceil((dataMax * 1.15) / 1000) * 1000,
                              ),
                          ]}
                        />
                        <Tooltip content={<PriceHistoryTooltip />} />
                        <Area
                          type="linear"
                          dataKey="price"
                          stroke="#00A86B"
                          strokeWidth={2.5}
                          fill="url(#realPriceFade)"
                          dot={{
                            r: 4,
                            fill: "#00A86B",
                            stroke: "#ffffff",
                            strokeWidth: 2,
                          }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-full flex items-center justify-center text-sm text-slate-400 border border-dashed border-slate-200 rounded-xl">
                      No price history points recorded yet.
                    </div>
                  )}
                </div>

                <div className="pt-4 border-t border-slate-100">
                  <h3 className="text-lg font-bold text-slate-900">
                    Price history
                  </h3>
                  {selectedProduct && (
                    <p className="text-xs text-slate-500 line-clamp-1 mt-0.5">
                      {selectedProduct.name}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Team & Guidance Footer */}
      <footer className="max-w-7xl w-full mx-auto mt-12 pt-6 border-t border-slate-800 text-xs text-slate-400 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <span className="text-slate-300 font-medium">Team:</span> Niyati Shah,
          M.Sufiyan Makandar &amp; Amogh Pawar
        </div>
        <div>
          <span className="text-slate-300 font-medium">
            Under the guidance of:
          </span>{" "}
          Varun Sarvade
        </div>
      </footer>
    </main>
  );
}
