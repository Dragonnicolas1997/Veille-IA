const BASE = import.meta.env.VITE_API_BASE || "/api";

function getToken() {
  return localStorage.getItem("auth_token");
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, {
    headers,
    ...options,
  });
  if (res.status === 401) {
    localStorage.removeItem("auth_token");
    window.dispatchEvent(new Event("auth-expired"));
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Auth
export const login = async (password) => {
  const res = await fetch(`${BASE}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) throw new Error("Mot de passe incorrect");
  const data = await res.json();
  localStorage.setItem("auth_token", data.token);
  return data;
};

export const logout = () => {
  localStorage.removeItem("auth_token");
};

export const isAuthenticated = () => !!getToken();

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
export const deleteArticle = (id) =>
  request(`/articles/${id}`, { method: "DELETE" });
export const likeArticle = (id) =>
  request(`/articles/${id}/like`, { method: "POST" });

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

// Add article manually
export const addArticle = (url, category_id) =>
  request("/articles/add", { method: "POST", body: JSON.stringify({ url, category_id }) });

// Reclassify
export const reclassify = () =>
  request("/reclassify", { method: "POST" });

// Briefing
export const generateBriefing = (articleIds, auto = false, prompt = null) =>
  request("/briefing", {
    method: "POST",
    body: JSON.stringify({ article_ids: articleIds, auto, prompt }),
  });
