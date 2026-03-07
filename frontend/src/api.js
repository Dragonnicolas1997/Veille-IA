const BASE = import.meta.env.VITE_API_BASE || "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Feeds
export const getFeeds = () => request("/feeds");
export const addFeed = (url, name) =>
  request("/feeds", { method: "POST", body: JSON.stringify({ url, name }) });
export const deleteFeed = (id) =>
  request(`/feeds/${id}`, { method: "DELETE" });
export const refreshFeeds = () =>
  request("/feeds/refresh", { method: "POST" });

// Articles
export const getArticles = (params = {}) => {
  const q = new URLSearchParams();
  if (params.category_id) q.set("category_id", params.category_id);
  if (params.days) q.set("days", params.days);
  if (params.per_category) q.set("per_category", params.per_category);
  return request(`/articles?${q}`);
};
export const patchArticle = (id, data) =>
  request(`/articles/${id}`, { method: "PATCH", body: JSON.stringify(data) });

// Categories
export const getCategories = () => request("/categories");
export const createCategory = (data) =>
  request("/categories", { method: "POST", body: JSON.stringify(data) });
export const updateCategory = (id, data) =>
  request(`/categories/${id}`, { method: "PUT", body: JSON.stringify(data) });
export const deleteCategory = (id) =>
  request(`/categories/${id}`, { method: "DELETE" });

// Settings
export const getSettings = () => request("/settings");
export const updateSettings = (data) =>
  request("/settings", { method: "PUT", body: JSON.stringify(data) });

// Stats
export const getStats = () => request("/stats");

// Translate titles
export const translateTitles = () =>
  request("/translate-titles", { method: "POST" });

// Reclassify
export const reclassify = () =>
  request("/reclassify", { method: "POST" });

// Briefing
export const generateBriefing = (articleIds, auto = false, prompt = null) =>
  request("/briefing", {
    method: "POST",
    body: JSON.stringify({ article_ids: articleIds, auto, prompt }),
  });
