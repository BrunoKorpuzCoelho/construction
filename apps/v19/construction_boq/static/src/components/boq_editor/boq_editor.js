/** @odoo-module **/
/**
 * Construction BOQ Editor — Odoo 19
 * All fixes applied:
 *  [2] addSubChapterById(capId) — looks up cap by id, avoids closure capture issue
 *  [3] state.tree starts as null, template guards with !== null
 *  [4] Controller uses **kw — rpc sends params as named args (already correct on client)
 *  [6] onUomChange() method — no inline parseInt in template
 */
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

function md(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/^- (.+)$/gm, "<li>$1</li>")
        .replace(/((<li>[^<]*<\/li>\n?)+)/g, "<ul>$1</ul>")
        .replace(/\n/g, "<br/>");
}

export class BOQEditorAction extends Component {
    static template = "construction_boq.BOQEditor";
    static props = ["*"];  // accept all Odoo framework props

    setup() {
        this.notification  = useService("notification");
        this.actionService = useService("action");
        this.aiScrollRef   = useRef("aiScroll");
        this.boqId = this.props.action?.context?.boq_id;

        this.state = useState({
            loading: true,
            tree: null,          // null = not loaded, object = loaded
            readonly: false,

            selectedCapId: null,
            selectedSubId: null,

            articles: [],
            articlesTotal: 0,
            page: 0,
            pageSize: 150,
            search: "",

            capTotals: {},
            subTotals: {},
            grandTotal: 0,

            showStock: false,
            uoms: [],

            aiOpen: false,
            aiMessages: [{
                role: "assistant",
                content: "👋 Hello! I'm your **AI BOQ Assistant**.\n\nTry:\n- **Show totals** — value by chapter\n- **Largest chapters** — top 3\n- **By specialty** — HVAC, Elec…\n- **Article counts**",
                ts: "",
            }],
            aiLoading: false,
            aiInput: "",
        });

        onWillStart(async () => {
            await Promise.all([this._loadTree(), this._loadUoms()]);
        });
    }

    // ── Formatters (methods, accessible from template) ─────────────────────
    fmtMoney(n) {
        return Number(n || 0).toLocaleString("en-GB", {
            minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    fmtQty(n) {
        return Number(n || 0).toLocaleString("en-GB", {
            minimumFractionDigits: 3, maximumFractionDigits: 3 });
    }
    parseNum(s) {
        return parseFloat(String(s || 0).replace(/\s/g, "").replace(",", ".")) || 0;
    }
    mdHtml(t) { return md(t); }

    // ── RPC ────────────────────────────────────────────────────────────────
    async _rpc(route, params) {
        return rpc(route, params);
    }

    // ── Load tree ──────────────────────────────────────────────────────────
    async _loadTree() {
        try {
            const tree = await this._rpc("/construction_boq/load_tree", {
                boq_id: this.boqId });
            for (const cap of tree.capitulos || []) {
                this.state.capTotals[cap.id] = cap.total || 0;
                cap._open = true;
                for (const sub of cap.subcapitulos || []) {
                    this.state.subTotals[sub.id] = {
                        total: sub.total || 0, cnt: sub.artigo_count || 0 };
                }
            }
            this._recalcGrand();
            this.state.readonly = !!tree.readonly;
            this.state.tree = tree;   // set last so template sees complete data

            const fc = tree.capitulos?.[0];
            if (fc) {
                this.state.selectedCapId = fc.id;
                const fs = fc.subcapitulos?.[0];
                if (fs) {
                    this.state.selectedSubId = fs.id;
                    await this._loadArticles();
                    return;
                }
            }
        } catch (e) {
            console.error("load_tree error:", e);
            this.notification.add("Error loading BOQ: " + (e.message || ""), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async _loadUoms() {
        try {
            this.state.uoms = await this._rpc("/construction_boq/search_uoms", { query: "" });
        } catch (_) {}
    }

    async _loadArticles(resetPage = true) {
        if (!this.state.selectedSubId) return;
        if (resetPage) this.state.page = 0;
        this.state.loadingArticles = true;
        try {
            const r = await this._rpc("/construction_boq/load_artigos", {
                boq_id: this.boqId,
                subcapitulo_id: this.state.selectedSubId,
                search: this.state.search || null,
                offset: this.state.page * this.state.pageSize,
                limit: this.state.pageSize,
            });
            this.state.articles = r.artigos || [];
            this.state.articlesTotal = r.total || 0;
        } finally {
            this.state.loadingArticles = false;
        }
    }

    async _refreshTotals() {
        const t = await this._rpc("/construction_boq/get_totals", { boq_id: this.boqId });
        this.state.capTotals  = t.cap_totals  || {};
        this.state.subTotals  = t.sub_totals  || {};
        this.state.grandTotal = t.grand_total || 0;
        for (const cap of this.state.tree?.capitulos || []) {
            cap.total = this.state.capTotals[cap.id] || 0;
            for (const sub of cap.subcapitulos || []) {
                const sd = this.state.subTotals[sub.id] || {};
                sub.total = sd.total || 0;
                sub.artigo_count = sd.cnt ?? sub.artigo_count;
            }
        }
    }

    _recalcGrand() {
        this.state.grandTotal = Object.values(this.state.capTotals)
            .reduce((s, v) => s + (v || 0), 0);
    }

    // ── Getters ────────────────────────────────────────────────────────────
    get selectedCap() {
        if (!this.state.tree) return null;
        return this.state.tree.capitulos?.find(c => c.id === this.state.selectedCapId) || null;
    }
    get selectedSub() {
        return this.selectedCap?.subcapitulos?.find(s => s.id === this.state.selectedSubId) || null;
    }
    get totalPages()  { return Math.max(1, Math.ceil(this.state.articlesTotal / this.state.pageSize)); }
    get subTotal()    { return this.state.subTotals[this.state.selectedSubId]?.total || 0; }

    // ── Navigation ─────────────────────────────────────────────────────────
    // Arrow function: preserves `this` when called from template without `this.` prefix
    selectSub = async (capId, subId) => {
        this.state.selectedCapId = capId;
        this.state.selectedSubId = subId;
        this.state.search = "";
        await this._loadArticles();
    };

    // ── Cell save ──────────────────────────────────────────────────────────
    // Arrow function: preserves `this` when called from template without `this.` prefix
    saveCell = async (art, field, value) => {
        if (this.state.readonly) return;
        art[field] = value;
        if (field === "qty_contract" || field === "price_unit") {
            art.total = this.parseNum(art.qty_contract) * this.parseNum(art.price_unit);
        }
        try {
            await this._rpc("/construction_boq/save_artigo", {
                boq_id: this.boqId,
                artigo: {
                    id: art.id,
                    capitulo_id: art.capitulo_id || this.state.selectedCapId,
                    subcapitulo_id: art.subcapitulo_id || this.state.selectedSubId,
                    code: art.code || "",
                    name: art.name || "New article",
                    uom_id: art.uom_id || null,
                    product_id: art.product_id || null,
                    qty_contract: this.parseNum(art.qty_contract),
                    price_unit: this.parseNum(art.price_unit),
                    obs: art.obs || "",
                    show_in_stock: !!art.show_in_stock,
                },
            });
            if (field === "qty_contract" || field === "price_unit") {
                await this._refreshTotals();
            }
        } catch (e) {
            this.notification.add("Save error: " + (e.message || ""), { type: "danger" });
        }
    };

    // Arrow function: preserves `this` when called from template without `this.` prefix
    onUomChange = (art, ev) => {
        const val = parseInt(ev.target.value, 10);
        this.saveCell(art, 'uom_id', isNaN(val) ? null : val);
    };

    // Keyboard: method so no inline statement in template
    onCellKeydown(ev) {
        if (ev.key === "Enter") ev.target.blur();
        if (ev.key === "Tab") {
            ev.preventDefault();
            const inputs = Array.from(document.querySelectorAll(".boq-table .cell-inp"));
            const idx = inputs.indexOf(ev.target);
            if (idx >= 0 && idx < inputs.length - 1) inputs[idx + 1].focus();
        }
    }

    // ── Add article ────────────────────────────────────────────────────────
    async addArticle() {
        if (this.state.readonly || !this.state.selectedSubId) {
            if (!this.state.selectedSubId)
                this.notification.add("Select a sub-chapter first.", { type: "warning" });
            return;
        }
        const sub = this.selectedSub;
        const code = `${sub?.code || ""}.${String(this.state.articlesTotal + 1).padStart(2, "0")}`;
        const newArt = {
            id: null, code, name: "New article",
            uom_id: null, uom_name: "",
            qty_contract: 0, price_unit: 0, total: 0,
            obs: "", show_in_stock: false,
            capitulo_id: this.state.selectedCapId,
            subcapitulo_id: this.state.selectedSubId,
        };
        try {
            const r = await this._rpc("/construction_boq/save_artigo", {
                boq_id: this.boqId, artigo: newArt });
            newArt.id = r.id;
            this.state.articles.push(newArt);
            this.state.articlesTotal++;
            setTimeout(() => {
                const inputs = document.querySelectorAll(".boq-table .cell-inp");
                if (inputs.length) inputs[inputs.length - 1].focus();
            }, 80);
        } catch (e) {
            this.notification.add("Error adding article: " + (e.message || ""), { type: "danger" });
        }
    }

    // Arrow function: preserves `this` when called from template without `this.` prefix
    deleteArticle = async (art) => {
        if (this.state.readonly) return;
        if (!window.confirm(`Delete "${art.name}"?`)) return;
        await this._rpc("/construction_boq/delete_artigo", {
            boq_id: this.boqId, artigo_id: art.id });
        const idx = this.state.articles.indexOf(art);
        if (idx > -1) this.state.articles.splice(idx, 1);
        this.state.articlesTotal = Math.max(0, this.state.articlesTotal - 1);
        await this._refreshTotals();
    };

    // ── Add chapter ────────────────────────────────────────────────────────
    async addChapter() {
        if (this.state.readonly) return;
        const caps = this.state.tree?.capitulos || [];
        const code = String(caps.length + 1).padStart(2, "0");
        const name = window.prompt("Chapter name:", `${code} — New Chapter`);
        if (!name) return;
        const r = await this._rpc("/construction_boq/add_capitulo", {
            boq_id: this.boqId,
            data: { code, name, specialty: "General", color: "#1E3A5F" },
        });
        caps.push({ id: r.id, code, name, specialty: "General",
                    total: 0, subcapitulos: [], _open: true });
    }

    // Arrow function: preserves `this` when called from template without `this.` prefix
    addSubChapterById = async (capId) => {
        if (this.state.readonly) return;
        const cap = this.state.tree?.capitulos?.find(c => c.id === capId);
        if (!cap) return;
        const subs = cap.subcapitulos || [];
        const code = `${cap.code}.${String(subs.length + 1).padStart(2, "0")}`;
        const name = window.prompt("Sub-chapter name:", `Sub-chapter ${subs.length + 1}`);
        if (!name) return;
        const r = await this._rpc("/construction_boq/add_subcapitulo", {
            boq_id: this.boqId,
            data: { capitulo_id: cap.id, code, name },
        });
        const newSub = { id: r.id, code, name, total: 0, artigo_count: 0 };
        subs.push(newSub);
        await this.selectSub(cap.id, newSub.id);
    };

    // ── Search / pagination ────────────────────────────────────────────────
    async onSearch(ev) {
        this.state.search = ev.target.value;
        await this._loadArticles();
    }
    async prevPage() {
        if (this.state.page > 0) { this.state.page--; await this._loadArticles(false); }
    }
    async nextPage() {
        if (this.state.page < this.totalPages - 1) {
            this.state.page++; await this._loadArticles(false);
        }
    }

    // ── Export / import ────────────────────────────────────────────────────
    exportInternal() { window.location.href = `/construction_boq/export/${this.boqId}`; }
    exportClient()   { window.location.href = `/construction_boq/export_client/${this.boqId}`; }
    openImport() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "construction.boq.import.wizard",
            view_mode: "form", views: [[false, "form"]], target: "new",
            context: { default_boq_id: this.boqId },
        });
    }

    // ── AI ─────────────────────────────────────────────────────────────────
    toggleAI() { this.state.aiOpen = !this.state.aiOpen; }

    async sendAI() {
        const q = (this.state.aiInput || "").trim();
        if (!q || this.state.aiLoading) return;
        this.state.aiMessages.push({ role: "user", content: q,
                                     ts: new Date().toLocaleTimeString() });
        this.state.aiInput = "";
        this.state.aiLoading = true;
        this._scrollAI();
        try {
            const history = this.state.aiMessages
                .filter(m => m.role !== "system").slice(-6)
                .map(m => ({ role: m.role, content: m.content }));
            const r = await this._rpc("/construction_boq/ai_query", {
                boq_id: this.boqId, question: q, history });
            let answer = r.answer || "No response.";
            if (r.source === "builtin" && r.hint) answer += `\n\n_ℹ️ ${r.hint}_`;
            this.state.aiMessages.push({
                role: "assistant", content: answer,
                ts: new Date().toLocaleTimeString(), source: r.source });
        } catch (e) {
            this.state.aiMessages.push({
                role: "assistant",
                content: "⚠️ Error: " + (e.message || "Could not reach endpoint."),
                ts: new Date().toLocaleTimeString(), source: "error" });
        } finally {
            this.state.aiLoading = false;
            this._scrollAI();
        }
    }

    onAIKeyDown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); this.sendAI(); }
    }
    // Arrow function: preserves `this` when called from template without `this.` prefix
    sendSuggested = async (q) => {
        this.state.aiInput = q;
        await this.sendAI();
    };
    _scrollAI() {
        setTimeout(() => {
            const el = this.aiScrollRef?.el;
            if (el) el.scrollTop = el.scrollHeight;
        }, 60);
    }
}

registry.category("actions").add("construction_boq.editor", BOQEditorAction);
