import { useState, useEffect, useMemo } from "react";
import {
  Settings,
  RefreshCw,
  Rss,
  Tag,
  ExternalLink,
  Trash2,
  Filter,
  Search,
  AlertCircle,
  Loader2,
  Plus,
  X,
  LayoutDashboard,
  BrainCircuit,
  Info,
  FileText,
  Sparkles,
  Check,
  Copy,
  Download,
  RotateCw,
  Pencil,
  ChevronDown,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import html2pdf from "html2pdf.js";
import * as api from "./api";

export default function App() {
  // Data state
  const [feeds, setFeeds] = useState([]);
  const [categories, setCategories] = useState([]);
  const [articles, setArticles] = useState([]);
  const [settings, setSettings] = useState({});
  const [stats, setStats] = useState(null);

  // UI state
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [showSettings, setShowSettings] = useState(false);
  const [showBriefingModal, setShowBriefingModal] = useState(false);
  const [selectedForBriefing, setSelectedForBriefing] = useState([]);
  const [generatedBriefing, setGeneratedBriefing] = useState(null);
  const [isGeneratingBriefing, setIsGeneratingBriefing] = useState(false);
  const [briefingPrompt, setBriefingPrompt] = useState("");
  const [isEditingBriefing, setIsEditingBriefing] = useState(false);
  const [lastBriefingMode, setLastBriefingMode] = useState(null);
  const [expandedCatId, setExpandedCatId] = useState(null);
  const [descriptionChanged, setDescriptionChanged] = useState(false);
  const [isReclassifying, setIsReclassifying] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [days, setDays] = useState(7);
  const [searchQuery, setSearchQuery] = useState("");

  // Settings form state
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [refreshInterval, setRefreshInterval] = useState(4);

  // Derived
  const filteredArticles = useMemo(() => {
    let list = articles;
    if (selectedCategory === "unclassified")
      list = list.filter((a) => !a.category_id);
    else if (selectedCategory !== "all")
      list = list.filter((a) => String(a.category_id) === String(selectedCategory));

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (a) =>
          (a.title_fr || "").toLowerCase().includes(q) ||
          (a.title || "").toLowerCase().includes(q) ||
          (a.summary_fr || "").toLowerCase().includes(q) ||
          (a.description || "").toLowerCase().includes(q)
      );
    }
    return list;
  }, [articles, selectedCategory, searchQuery]);

  const categoryCounts = useMemo(() => {
    const counts = {};
    articles.forEach((a) => {
      if (a.category_id) {
        counts[a.category_id] = (counts[a.category_id] || 0) + 1;
      }
    });
    return counts;
  }, [articles]);

  // Load everything on mount
  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    try {
      const [f, c, s, st] = await Promise.all([
        api.getFeeds(),
        api.getCategories(),
        api.getSettings(),
        api.getStats(),
      ]);
      setFeeds(f);
      setCategories(c);
      setSettings(s);
      setStats(st);
      if (s.refresh_interval_hours)
        setRefreshInterval(Number(s.refresh_interval_hours));
    } catch (e) {
      console.error("Load error:", e);
    }
    loadArticles();
  }

  // Recharger les articles quand le filtre jours change
  useEffect(() => {
    loadArticles();
  }, [days]);

  async function loadArticles() {
    try {
      setArticles(await api.getArticles({ days: days || undefined, per_category: 100 }));
    } catch (e) {
      console.error("Articles error:", e);
    }
  }

  // Actions
  async function handleRefresh() {
    setIsRefreshing(true);
    setStatusMessage("Actualisation en cours...");
    try {
      await api.refreshFeeds();
      setDescriptionChanged(false);
      setStatusMessage(null);
      await loadAll();
    } catch (e) {
      setStatusMessage("Erreur lors de la mise à jour.");
    }
    setIsRefreshing(false);
  }

  async function handleAddFeed(e) {
    e.preventDefault();
    const label = document.getElementById("new-feed-label");
    const url = document.getElementById("new-feed-url");
    if (!label.value || !url.value) return;
    try {
      await api.addFeed(url.value, label.value);
      label.value = "";
      url.value = "";
      setFeeds(await api.getFeeds());
    } catch (err) {
      setStatusMessage("Erreur: ce flux existe peut-être déjà.");
    }
  }

  async function handleRemoveFeed(id) {
    await api.deleteFeed(id);
    setFeeds(await api.getFeeds());
  }

  async function handleSaveSettings() {
    const data = {};
    if (apiKeyInput) data.anthropic_api_key = apiKeyInput;
    data.refresh_interval_hours = refreshInterval;
    await api.updateSettings(data);
    setApiKeyInput("");
    setSettings(await api.getSettings());
    setShowSettings(false);
  }

  async function handleUpdateCategory(id, updates = {}) {
    const cat = categories.find((c) => c.id === id);
    if (!cat) return;
    if (updates.description !== undefined && updates.description !== (cat.description || "")) {
      setDescriptionChanged(true);
    }
    await api.updateCategory(id, {
      name: updates.name ?? cat.name,
      color: updates.color ?? cat.color,
      description: updates.description ?? cat.description ?? "",
      position: cat.position ?? 0,
    });
    setCategories(await api.getCategories());
  }

  async function handleAddCategory(name, description) {
    if (!name.trim()) return;
    const pos = categories.length + 1;
    await api.createCategory({ name, color: "#6b7280", description, position: pos });
    setCategories(await api.getCategories());
  }

  async function handleRemoveArticle(id) {
    await api.patchArticle(id, { manually_removed: true });
    setArticles((prev) => prev.filter((a) => a.id !== id));
  }

  async function handleMoveArticle(id, newCatId) {
    await api.patchArticle(id, { category_id: Number(newCatId) });
    await loadArticles();
  }

  function toggleArticleSelection(id) {
    setSelectedForBriefing((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function handleGenerateBriefing(isAuto, usePrompt = false) {
    setIsGeneratingBriefing(true);
    setGeneratedBriefing(null);
    setIsEditingBriefing(false);
    setLastBriefingMode({ isAuto, usePrompt });
    try {
      const result = await api.generateBriefing(
        isAuto || usePrompt ? [] : selectedForBriefing,
        isAuto,
        usePrompt ? briefingPrompt : null
      );
      setGeneratedBriefing(result.briefing);
    } catch (e) {
      setStatusMessage("Erreur lors de la génération de la veille.");
    }
    setIsGeneratingBriefing(false);
  }

  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#1A1A1A] font-sans flex flex-col">
      {/* Top Bar */}
      <header className="h-16 border-b border-black/5 bg-white flex items-center justify-between px-6 sticky top-0 z-30 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-black rounded-xl flex items-center justify-center text-white">
            <BrainCircuit size={24} />
          </div>
          <div>
            <h1 className="font-bold text-xl tracking-tight">Veille IA</h1>
            <p className="text-[10px] uppercase tracking-widest text-black/40 font-semibold">
              Intelligence Monitoring
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {stats?.last_refresh && (
            <div className="text-xs text-black/40 font-medium hidden sm:block">
              Dernière MAJ:{" "}
              <span className="text-black/70">
                {new Date(stats.last_refresh).toLocaleTimeString("fr-FR")}
              </span>
            </div>
          )}
          <div className="h-8 w-[1px] bg-black/5 hidden sm:block" />
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold px-2 py-1 bg-black/5 rounded-md">
              {articles.length} articles
            </span>
            <button
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-black/80 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-black/10"
            >
              {isRefreshing ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <RefreshCw size={16} />
              )}
              <span>Actualiser</span>
            </button>
            <button
              onClick={() => setShowSettings(true)}
              className="p-2 hover:bg-black/5 rounded-lg transition-colors text-black/60 hover:text-black"
            >
              <Settings size={20} />
            </button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="w-72 border-r border-black/5 bg-white flex flex-col p-6 gap-8 overflow-y-auto">
          {/* Période */}
          <section>
            <h2 className="text-[11px] font-bold uppercase tracking-widest text-black/30 mb-4 flex items-center gap-2">
              <Filter size={12} /> Période
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {[
                { label: "24h", value: 1 },
                { label: "3j", value: 3 },
                { label: "7j", value: 7 },
                { label: "14j", value: 14 },
                { label: "1 mois", value: 31 },
                { label: "Tout", value: null },
              ].map((p) => (
                <button
                  key={p.value}
                  onClick={() => setDays(p.value)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    days === p.value
                      ? "bg-black text-white shadow-md"
                      : "bg-black/5 text-black/50 hover:bg-black/10"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </section>

          <section>
            <h2 className="text-[11px] font-bold uppercase tracking-widest text-black/30 mb-4 flex items-center gap-2">
              <Filter size={12} /> Catégories
            </h2>
            <nav className="flex flex-col gap-1">
              <button
                onClick={() => setSelectedCategory("all")}
                className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-all ${selectedCategory === "all" ? "bg-black text-white shadow-md" : "hover:bg-black/5 text-black/60"}`}
              >
                <div className="flex items-center gap-3">
                  <LayoutDashboard size={16} />
                  <span>Tous les articles</span>
                </div>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-md ${selectedCategory === "all" ? "bg-white/20" : "bg-black/5"}`}
                >
                  {articles.length}
                </span>
              </button>

              {categories.map((cat) => (
                <button
                  key={cat.id}
                  onClick={() => setSelectedCategory(String(cat.id))}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-all ${String(selectedCategory) === String(cat.id) ? "bg-black text-white shadow-md" : "hover:bg-black/5 text-black/60"}`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: cat.color }}
                    />
                    <span>{cat.name}</span>
                  </div>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-md ${String(selectedCategory) === String(cat.id) ? "bg-white/20" : "bg-black/5"}`}
                  >
                    {categoryCounts[cat.id] || 0}
                  </span>
                </button>
              ))}

            </nav>
          </section>

          <section>
            <h2 className="text-[11px] font-bold uppercase tracking-widest text-black/30 mb-4 flex items-center gap-2">
              <Sparkles size={12} /> Outils
            </h2>
            <button
              onClick={() => setShowBriefingModal(true)}
              className="w-full flex items-center gap-3 px-3 py-3 bg-emerald-500 text-white rounded-xl text-sm font-bold shadow-lg shadow-emerald-500/20 hover:bg-emerald-600 transition-all"
            >
              <FileText size={18} />
              <span>Créer une Veille</span>
              {selectedForBriefing.length > 0 && (
                <span className="ml-auto bg-white/20 px-2 py-0.5 rounded-md text-[10px]">
                  {selectedForBriefing.length}
                </span>
              )}
            </button>
          </section>

          <section className="mt-auto">
            <div className="p-4 bg-black/5 rounded-2xl border border-black/5">
              <div className="flex items-center gap-2 mb-2">
                <Info size={14} className="text-black/40" />
                <h3 className="text-xs font-bold">À propos</h3>
              </div>
              <p className="text-[11px] text-black/50 leading-relaxed">
                Veille IA utilise Claude pour filtrer et résumer l'actualité IA
                en temps réel.
              </p>
            </div>
          </section>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto p-8 relative">
          <AnimatePresence mode="wait">
            {isRefreshing && (
              <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-black text-white px-6 py-3 rounded-full shadow-2xl flex items-center gap-3 text-sm font-medium"
              >
                <Loader2 size={18} className="animate-spin text-emerald-400" />
                <span>{statusMessage || "Mise à jour en cours..."}</span>
              </motion.div>
            )}
          </AnimatePresence>

          {statusMessage && !isRefreshing && (
            <div className="mb-8 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center gap-3 text-amber-800 text-sm">
              <AlertCircle size={18} />
              <p>{statusMessage}</p>
              <button
                onClick={() => setStatusMessage(null)}
                className="ml-auto"
              >
                <X size={16} />
              </button>
            </div>
          )}

          <div className="max-w-5xl mx-auto">
            <div className="relative mb-6">
              <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-black/30" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Rechercher par mots-clés..."
                className="w-full bg-white border border-black/5 rounded-2xl pl-12 pr-4 py-3 text-sm focus:ring-2 focus:ring-black/10 focus:border-black/10 outline-none transition-all shadow-sm placeholder:text-black/30"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-black/30 hover:text-black/60"
                >
                  <X size={16} />
                </button>
              )}
            </div>

            <div className="mb-8 flex items-end justify-between">
              <div>
                <h2 className="text-3xl font-bold tracking-tight mb-2">
                  {selectedCategory === "all"
                    ? "Flux d'actualités"
                    : selectedCategory === "unclassified"
                      ? "Non classifiés"
                      : categories.find(
                            (c) =>
                              String(c.id) === String(selectedCategory)
                          )?.name || "Articles"}
                </h2>
                <p className="text-black/40 text-sm font-medium">
                  {filteredArticles.length} articles — {!days ? "toutes les dates" : days <= 1 ? "dernières 24h" : `${days} derniers jours`}
                </p>
              </div>
            </div>

            {filteredArticles.length === 0 ? (
              <div className="h-96 border-2 border-dashed border-black/5 rounded-3xl flex flex-col items-center justify-center text-black/20 gap-4">
                <Rss size={48} strokeWidth={1} />
                <p className="text-lg font-medium italic">
                  Aucun article à afficher
                </p>
                <button
                  onClick={() => setShowSettings(true)}
                  className="text-sm text-black/60 underline hover:text-black"
                >
                  Configurez votre clé API pour commencer
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-6">
                {filteredArticles.map((article, idx) => (
                  <motion.article
                    key={article.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="group bg-white border border-black/5 rounded-3xl p-6 hover:shadow-xl hover:shadow-black/5 transition-all flex flex-col md:flex-row gap-6 relative overflow-hidden"
                  >
                    {/* Selection bar */}
                    <div
                      onClick={() => toggleArticleSelection(article.id)}
                      className={`absolute top-0 left-0 w-1.5 h-full cursor-pointer transition-all ${selectedForBriefing.includes(article.id) ? "bg-emerald-500" : "bg-transparent group-hover:bg-black/10"}`}
                    />

                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-3">
                        <button
                          onClick={() => toggleArticleSelection(article.id)}
                          className={`w-5 h-5 rounded-md border flex items-center justify-center transition-all ${selectedForBriefing.includes(article.id) ? "bg-emerald-500 border-emerald-500 text-white" : "border-black/10 hover:border-black/30"}`}
                        >
                          {selectedForBriefing.includes(article.id) && (
                            <Check size={12} strokeWidth={4} />
                          )}
                        </button>
                        <span className="text-[10px] font-bold uppercase tracking-widest text-black/40 bg-black/5 px-2 py-1 rounded">
                          {article.feed_name}
                        </span>
                        <span className="text-[10px] text-black/30 font-medium">
                          {article.published_at
                            ? new Date(article.published_at).toLocaleDateString(
                                "fr-FR",
                                { day: "numeric", month: "long" }
                              )
                            : ""}
                        </span>
                      </div>

                      <h3 className="text-xl font-bold mb-3 group-hover:text-black transition-colors leading-snug">
                        {article.title_fr || article.title}
                      </h3>

                      {article.summary_fr && (
                        <p className="text-black/60 text-sm leading-relaxed mb-6 italic">
                          "{article.summary_fr}"
                        </p>
                      )}

                      <div className="flex flex-wrap items-center gap-4">
                        <div className="flex items-center gap-2">
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{
                              backgroundColor:
                                article.category_color || "#ccc",
                            }}
                          />
                          <select
                            value={article.category_id || ""}
                            onChange={(e) =>
                              handleMoveArticle(article.id, e.target.value)
                            }
                            className="text-xs font-bold bg-transparent border-none p-0 focus:ring-0 cursor-pointer text-black/70 hover:text-black"
                          >
                            {categories.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="h-4 w-[1px] bg-black/5" />

                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-bold text-black/40 uppercase tracking-tighter">
                            Score
                          </span>
                          <div className="flex gap-0.5">
                            {[...Array(10)].map((_, i) => (
                              <div
                                key={i}
                                className={`w-1.5 h-3 rounded-full ${i < article.relevance_score ? "bg-emerald-500" : "bg-black/5"}`}
                              />
                            ))}
                          </div>
                          <span className="text-xs font-bold ml-1">
                            {article.relevance_score}/10
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex md:flex-col justify-between items-end gap-4 min-w-[140px]">
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2 text-xs font-bold bg-black/5 hover:bg-black hover:text-white px-4 py-2 rounded-xl transition-all w-full justify-center"
                      >
                        Lire l'article <ExternalLink size={12} />
                      </a>
                      <button
                        onClick={() => handleRemoveArticle(article.id)}
                        className="p-2 text-black/20 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all"
                        title="Retirer de la veille"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </motion.article>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>

      {/* Settings Modal */}
      <AnimatePresence>
        {showSettings && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowSettings(false)}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="bg-white w-full max-w-4xl max-h-[90vh] rounded-[40px] shadow-2xl relative z-10 overflow-hidden flex flex-col"
            >
              <div className="p-8 border-b border-black/5 flex items-center justify-between bg-white sticky top-0 z-10">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-black/5 rounded-2xl flex items-center justify-center text-black">
                    <Settings size={24} />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold tracking-tight">
                      Paramètres de Veille
                    </h2>
                    <p className="text-black/40 text-sm font-medium">
                      Configurez vos sources et l'IA
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setShowSettings(false)}
                  className="p-3 hover:bg-black/5 rounded-2xl transition-colors"
                >
                  <X size={24} />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-8 grid grid-cols-1 md:grid-cols-2 gap-12">
                {/* Left Column */}
                <div className="space-y-10">
                  <section>
                    <h3 className="text-sm font-bold uppercase tracking-widest text-black/30 mb-6 flex items-center gap-2">
                      <BrainCircuit size={14} /> Intelligence Artificielle
                    </h3>
                    <div className="space-y-4">
                      <div>
                        <label className="block text-xs font-bold text-black/60 mb-2 uppercase tracking-wider">
                          Intervalle de refresh (heures)
                        </label>
                        <input
                          type="number"
                          min={1}
                          value={refreshInterval}
                          onChange={(e) =>
                            setRefreshInterval(Number(e.target.value))
                          }
                          className="w-24 bg-black/5 border-none rounded-2xl px-5 py-4 text-sm focus:ring-2 focus:ring-black transition-all"
                        />
                      </div>
                    </div>
                  </section>

                  <section>
                    <h3 className="text-sm font-bold uppercase tracking-widest text-black/30 mb-6 flex items-center gap-2">
                      <Tag size={14} /> Catégories Thématiques (
                      {categories.length})
                    </h3>
                    <div className="space-y-3">
                      {categories.map((cat) => (
                        <div key={cat.id} className="bg-black/5 rounded-2xl border border-black/5 overflow-hidden">
                          <div className="flex items-center gap-3 p-3">
                            <input
                              type="color"
                              value={cat.color}
                              onChange={(e) => handleUpdateCategory(cat.id, { color: e.target.value })}
                              className="w-8 h-8 rounded-lg border-none p-0 cursor-pointer bg-transparent shrink-0"
                            />
                            <input
                              type="text"
                              defaultValue={cat.name}
                              onBlur={(e) => handleUpdateCategory(cat.id, { name: e.target.value })}
                              className="flex-1 bg-white border-none rounded-xl px-3 py-1.5 text-sm focus:ring-2 focus:ring-black transition-all font-medium"
                            />
                            <button
                              onClick={() => setExpandedCatId(expandedCatId === cat.id ? null : cat.id)}
                              className={`p-1.5 rounded-lg transition-all text-black/30 hover:text-black/60 hover:bg-white ${expandedCatId === cat.id ? "rotate-180" : ""}`}
                              title="Voir la description"
                            >
                              <ChevronDown size={16} />
                            </button>
                            <button
                              onClick={async () => {
                                await api.deleteCategory(cat.id);
                                setCategories(await api.getCategories());
                              }}
                              className="p-1.5 rounded-lg transition-all text-black/20 hover:text-red-500 hover:bg-red-50"
                              title="Supprimer la catégorie"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                          {expandedCatId === cat.id && (
                            <div className="px-3 pb-3">
                              <label className="block text-[10px] font-bold text-black/40 uppercase tracking-wider mb-1.5 ml-1">
                                Description (critères pour Claude)
                              </label>
                              <textarea
                                defaultValue={cat.description || ""}
                                onBlur={(e) => handleUpdateCategory(cat.id, { description: e.target.value })}
                                placeholder="Décrivez les critères de cette catégorie..."
                                rows={4}
                                className="w-full bg-white border-none rounded-xl px-3 py-2 text-xs focus:ring-2 focus:ring-black transition-all resize-none leading-relaxed"
                              />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    <div className="mt-6 p-4 bg-black text-white rounded-2xl space-y-3">
                      <h4 className="text-[10px] font-bold uppercase tracking-widest opacity-60">
                        Ajouter une catégorie
                      </h4>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          const name = e.target.elements["new-cat-name"].value;
                          const desc = e.target.elements["new-cat-desc"].value;
                          handleAddCategory(name, desc);
                          e.target.reset();
                        }}
                        className="space-y-2"
                      >
                        <input
                          name="new-cat-name"
                          type="text"
                          placeholder="Nom de la catégorie"
                          className="w-full bg-white/10 border-none rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-white/30 placeholder:text-white/30"
                        />
                        <textarea
                          name="new-cat-desc"
                          placeholder="Description / critères de filtrage pour Claude..."
                          rows={3}
                          className="w-full bg-white/10 border-none rounded-xl px-4 py-2.5 text-xs focus:ring-2 focus:ring-white/30 placeholder:text-white/30 resize-none"
                        />
                        <button
                          type="submit"
                          className="w-full bg-white text-black py-2.5 rounded-xl text-sm font-bold hover:bg-white/90 transition-all flex items-center justify-center gap-2"
                        >
                          <Plus size={16} /> Ajouter
                        </button>
                      </form>
                    </div>

                    {descriptionChanged && (
                      <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-2xl">
                        <p className="text-xs text-amber-800 font-medium mb-3">
                          Les descriptions ont été modifiées. Reclassifiez les articles pour que Claude applique les nouveaux critères.
                        </p>
                        <button
                          onClick={async () => {
                            setIsReclassifying(true);
                            try {
                              await api.reclassify();
                              setDescriptionChanged(false);
                              await loadAll();
                            } catch (e) {
                              setStatusMessage("Erreur lors de la reclassification.");
                            }
                            setIsReclassifying(false);
                          }}
                          disabled={isReclassifying}
                          className="w-full py-2.5 bg-amber-500 text-white rounded-xl text-sm font-bold hover:bg-amber-600 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                        >
                          {isReclassifying ? (
                            <Loader2 size={16} className="animate-spin" />
                          ) : (
                            <RefreshCw size={16} />
                          )}
                          {isReclassifying ? "Reclassification en cours..." : "Reclassifier tous les articles"}
                        </button>
                      </div>
                    )}
                  </section>
                </div>

                {/* Right Column */}
                <div className="space-y-10">
                  <section>
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="text-sm font-bold uppercase tracking-widest text-black/30 flex items-center gap-2">
                        <Rss size={14} /> Sources RSS
                      </h3>
                    </div>

                    <div className="space-y-4 mb-6">
                      {feeds.map((feed) => (
                        <div
                          key={feed.id}
                          className="flex items-center justify-between p-4 bg-black/5 rounded-2xl border border-black/5 group"
                        >
                          <div className="overflow-hidden">
                            <p className="text-sm font-bold truncate">
                              {feed.name}
                            </p>
                            <p className="text-[10px] text-black/40 truncate font-mono">
                              {feed.url}
                            </p>
                          </div>
                          <button
                            onClick={() => handleRemoveFeed(feed.id)}
                            className="p-2 text-black/20 hover:text-red-500 hover:bg-white rounded-xl transition-all opacity-0 group-hover:opacity-100"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      ))}
                    </div>

                    <div className="p-6 bg-black text-white rounded-[32px] space-y-4 shadow-xl shadow-black/10">
                      <h4 className="text-xs font-bold uppercase tracking-widest opacity-60">
                        Ajouter une source
                      </h4>
                      <form onSubmit={handleAddFeed} className="space-y-3">
                        <input
                          id="new-feed-label"
                          type="text"
                          placeholder="Nom de la source (ex: TechCrunch)"
                          className="w-full bg-white/10 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-white/30 placeholder:text-white/30"
                        />
                        <div className="flex gap-2">
                          <input
                            id="new-feed-url"
                            type="text"
                            placeholder="URL du flux RSS"
                            className="flex-1 bg-white/10 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-white/30 placeholder:text-white/30"
                          />
                          <button
                            type="submit"
                            className="bg-white text-black p-3 rounded-xl hover:bg-white/90 transition-all"
                          >
                            <Plus size={20} />
                          </button>
                        </div>
                      </form>
                    </div>
                  </section>
                </div>
              </div>

              <div className="p-8 bg-black/5 flex justify-end gap-4">
                <button
                  onClick={handleSaveSettings}
                  className="px-8 py-3 bg-black text-white rounded-2xl font-bold text-sm hover:bg-black/80 transition-all shadow-lg shadow-black/10"
                >
                  Enregistrer et Fermer
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Briefing Modal */}
      <AnimatePresence>
        {showBriefingModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowBriefingModal(false)}
              className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className="bg-white w-full max-w-5xl max-h-[90vh] rounded-[40px] shadow-2xl relative z-10 overflow-hidden flex flex-col"
            >
              <div className="p-8 border-b border-black/5 flex items-center justify-between bg-white sticky top-0 z-10">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-emerald-500 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-emerald-500/20">
                    <FileText size={24} />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold tracking-tight">
                      Générer ma Veille
                    </h2>
                    <p className="text-black/40 text-sm font-medium">
                      Synthèse intelligente de vos articles sélectionnés
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setShowBriefingModal(false)}
                  className="p-3 hover:bg-black/5 rounded-2xl transition-colors"
                >
                  <X size={24} />
                </button>
              </div>

              <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
                {/* Selection Sidebar */}
                <div className="w-full md:w-80 border-r border-black/5 bg-black/[0.02] flex flex-col">
                  <div className="p-6 border-b border-black/5">
                    <h3 className="text-xs font-bold uppercase tracking-widest text-black/30 mb-4">
                      Articles sélectionnés
                    </h3>
                    <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto pr-2">
                      {selectedForBriefing.length === 0 ? (
                        <p className="text-xs text-black/30 italic py-4 text-center">
                          Aucun article sélectionné
                        </p>
                      ) : (
                        articles
                          .filter((a) => selectedForBriefing.includes(a.id))
                          .map((a) => (
                            <div
                              key={a.id}
                              className="p-3 bg-white rounded-xl border border-black/5 flex items-start gap-3"
                            >
                              <div
                                className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0"
                                style={{
                                  backgroundColor:
                                    a.category_color || "#ccc",
                                }}
                              />
                              <p className="text-[11px] font-bold leading-tight line-clamp-2">
                                {a.title_fr || a.title}
                              </p>
                              <button
                                onClick={() => toggleArticleSelection(a.id)}
                                className="text-black/20 hover:text-red-500 ml-auto"
                              >
                                <X size={12} />
                              </button>
                            </div>
                          ))
                      )}
                    </div>
                  </div>

                  <div className="p-6 border-t border-black/5">
                    <h3 className="text-xs font-bold uppercase tracking-widest text-black/30 mb-3">
                      Prompt personnalisé
                    </h3>
                    <textarea
                      value={briefingPrompt}
                      onChange={(e) => setBriefingPrompt(e.target.value)}
                      placeholder="Ex: Focus sur la réglementation européenne et l'impact sur les grandes entreprises françaises..."
                      className="w-full bg-black/5 border-none rounded-xl px-4 py-3 text-sm focus:ring-2 focus:ring-emerald-500 transition-all resize-none placeholder:text-black/30"
                      rows={3}
                    />
                    <button
                      onClick={() => handleGenerateBriefing(false, true)}
                      disabled={isGeneratingBriefing || !briefingPrompt.trim()}
                      className="w-full mt-3 py-3 bg-emerald-500 text-white rounded-xl text-sm font-bold hover:bg-emerald-600 transition-all disabled:opacity-50 flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20"
                    >
                      {isGeneratingBriefing ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Sparkles size={16} />
                      )}
                      Générer avec prompt
                    </button>
                  </div>

                  <div className="p-6 pt-0 mt-auto space-y-3">
                    <div className="flex items-center gap-3 my-2">
                      <div className="flex-1 h-[1px] bg-black/10" />
                      <span className="text-[10px] font-bold uppercase tracking-widest text-black/20">ou</span>
                      <div className="flex-1 h-[1px] bg-black/10" />
                    </div>
                    <button
                      onClick={() => handleGenerateBriefing(false)}
                      disabled={
                        isGeneratingBriefing ||
                        selectedForBriefing.length === 0
                      }
                      className="w-full py-3 bg-black text-white rounded-xl text-sm font-bold hover:bg-black/80 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      {isGeneratingBriefing ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <FileText size={16} />
                      )}
                      Générer la sélection
                    </button>
                    <button
                      onClick={() => handleGenerateBriefing(true)}
                      disabled={isGeneratingBriefing}
                      className="w-full py-3 bg-white border border-black/10 text-black rounded-xl text-sm font-bold hover:bg-black/5 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      <Sparkles size={16} className="text-emerald-500" />
                      Génération Auto
                    </button>
                  </div>
                </div>

                {/* Preview Area */}
                <div className="flex-1 bg-white overflow-y-auto p-8">
                  {!generatedBriefing && !isGeneratingBriefing ? (
                    <div className="h-full flex flex-col items-center justify-center text-black/20 gap-4 text-center max-w-sm mx-auto">
                      <Sparkles size={64} strokeWidth={1} />
                      <div>
                        <p className="text-lg font-bold text-black/40">
                          Prêt à synthétiser
                        </p>
                        <p className="text-sm">
                          Sélectionnez vos articles préférés ou laissez Claude
                          choisir les plus pertinents pour créer votre rapport
                          de veille.
                        </p>
                      </div>
                    </div>
                  ) : isGeneratingBriefing ? (
                    <div className="h-full flex flex-col items-center justify-center gap-6">
                      <div className="relative">
                        <Loader2
                          size={48}
                          className="animate-spin text-emerald-500"
                        />
                        <Sparkles
                          size={20}
                          className="absolute top-0 right-0 text-amber-400 animate-pulse"
                        />
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-bold">
                          Claude rédige votre veille...
                        </p>
                        <p className="text-sm text-black/40">
                          Synthèse thématique et analyse d'expert en cours
                        </p>
                      </div>
                    </div>
                  ) : (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="max-w-3xl mx-auto"
                    >
                      <div className="flex items-center justify-between mb-8">
                        <h3 className="text-xl font-bold">
                          Aperçu du rapport
                        </h3>
                        <div className="flex gap-2">
                          <button
                            onClick={() => setIsEditingBriefing(!isEditingBriefing)}
                            className={`p-2 rounded-lg transition-all flex items-center gap-2 text-xs font-bold ${isEditingBriefing ? "bg-amber-100 text-amber-700" : "hover:bg-black/5 text-black/60"}`}
                          >
                            <Pencil size={16} /> {isEditingBriefing ? "Aperçu" : "Modifier"}
                          </button>
                          <button
                            onClick={() => lastBriefingMode && handleGenerateBriefing(lastBriefingMode.isAuto, lastBriefingMode.usePrompt)}
                            disabled={isGeneratingBriefing}
                            className="p-2 hover:bg-black/5 rounded-lg transition-all text-black/60 flex items-center gap-2 text-xs font-bold disabled:opacity-50"
                          >
                            <RotateCw size={16} /> Regénérer
                          </button>
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(
                                generatedBriefing || ""
                              );
                            }}
                            className="p-2 hover:bg-black/5 rounded-lg transition-all text-black/60 flex items-center gap-2 text-xs font-bold"
                          >
                            <Copy size={16} /> Copier
                          </button>
                          <button
                            className="p-2 hover:bg-black/5 rounded-lg transition-all text-black/60 flex items-center gap-2 text-xs font-bold"
                            onClick={() => {
                              const el = document.getElementById("briefing-render");
                              if (!el) return;
                              html2pdf()
                                .set({
                                  margin: [15, 15, 15, 15],
                                  filename: `veille-ia-${new Date().toISOString().split("T")[0]}.pdf`,
                                  image: { type: "jpeg", quality: 0.98 },
                                  html2canvas: { scale: 2, useCORS: true },
                                  jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
                                  pagebreak: { mode: ["avoid-all", "css", "legacy"] },
                                })
                                .from(el)
                                .save();
                            }}
                          >
                            <Download size={16} /> Export PDF
                          </button>
                        </div>
                      </div>

                      {isEditingBriefing ? (
                        <textarea
                          value={generatedBriefing || ""}
                          onChange={(e) => setGeneratedBriefing(e.target.value)}
                          className="w-full min-h-[500px] bg-white p-8 rounded-[32px] border border-black/10 focus:border-black/30 focus:ring-0 font-mono text-sm leading-relaxed text-black/80 resize-y outline-none"
                        />
                      ) : (
                        <div id="briefing-render" className="bg-white p-10 rounded-[32px] border border-black/5 prose prose-neutral max-w-none
                          prose-h1:text-2xl prose-h1:font-extrabold prose-h1:tracking-tight prose-h1:mb-1
                          prose-h2:text-lg prose-h2:font-bold prose-h2:mt-8 prose-h2:mb-3 prose-h2:pb-2 prose-h2:border-b prose-h2:border-black/10
                          prose-h3:text-base prose-h3:font-semibold prose-h3:mt-5 prose-h3:mb-1
                          prose-p:text-[14px] prose-p:leading-relaxed prose-p:my-1.5
                          prose-a:text-emerald-600 prose-a:font-medium prose-a:no-underline hover:prose-a:underline
                          prose-strong:font-bold
                          prose-hr:my-6 prose-hr:border-black/8
                        ">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {generatedBriefing}
                          </ReactMarkdown>
                        </div>
                      )}
                    </motion.div>
                  )}
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Footer */}
      <footer className="py-6 px-8 border-t border-black/5 bg-white text-center">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-black/20">
          Veille IA &copy; {new Date().getFullYear()} &mdash; Powered by Claude
        </p>
      </footer>
    </div>
  );
}
