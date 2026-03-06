/** @odoo-module **/
/**
 * Construction BOQ Editor — Odoo 19
 * Infinite hierarchy via flat sections list (any depth, ordered by path).
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
    static template = "construction_boq_new.BOQEditor";
    static props = ["*"];

    setup() {
        this.notification  = useService("notification");
        this.actionService = useService("action");
        this.aiScrollRef   = useRef("aiScroll");

        const _urlBoqId = (() => {
            const m = window.location.pathname.match(
                /\/(\d+)\/action-construction_boq_new\.editor/);
            return m ? parseInt(m[1], 10) : null;
        })();

        this.boqId = this.props.action?.context?.boq_id
                  || this.props.action?.state?.boq_id
                  || _urlBoqId;

        if (this.boqId) {
            this.props.updateActionState?.({ boq_id: this.boqId });
        }

        this.state = useState({
            loading: true,
            readonly: false,

            // Flat sections list (any depth), ordered by path
            sections: [],
            selectedSectionId: null,
            secTotals: {},         // { sec_id: { total, cnt } }
            expandedIds: new Set(),

            articles: [],
            articlesTotal: 0,
            page: 0,
            pageSize: 150,
            search: "",

            grandTotal: 0,

            showStock: false,
            uoms: [],

            aiOpen: false,
            aiMessages: [{
                role: "assistant",
                content: "👋 Hello! I'm your **AI BOQ Assistant**.\n\nTry:\n- **Show totals** — value by section\n- **Largest sections** — top 3\n- **By specialty** — HVAC, Elec…\n- **Article counts**",
                ts: "",
            }],
            aiLoading: false,
            aiInput: "",
        });

        onWillStart(async () => {
            await Promise.all([this._loadTree(), this._loadUoms()]);
        });
    }

    // ── Formatters ─────────────────────────────────────────────────────────
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
        if (!this.boqId) {
            this.notification.add("No BOQ selected. Please open the editor from a BOQ record.", { type: "warning" });
            this.state.loading = false;
            return;
        }
        try {
            const tree = await this._rpc("/construction_boq/load_tree", {
                boq_id: this.boqId });
            this.state.sections = tree.sections || [];

            // Build rolled-up totals locally from flat list
            const totalMap = {};
            for (const s of this.state.sections) {
                totalMap[s.id] = s.direct_total || 0;
            }
            for (const s of [...this.state.sections].reverse()) {
                if (s.parent_id && totalMap[s.parent_id] !== undefined) {
                    totalMap[s.parent_id] += totalMap[s.id];
                }
            }
            for (const s of this.state.sections) {
                s.total = totalMap[s.id] || 0;
            }
            this.state.grandTotal = this.state.sections
                .filter(s => !s.parent_id)
                .reduce((sum, s) => sum + s.total, 0);

            // Auto-expand root sections
            this.state.sections
                .filter(s => s.depth === 0)
                .forEach(s => this.state.expandedIds.add(s.id));

            this.state.readonly = !!tree.readonly;

            // Auto-select first leaf
            const firstLeaf = this.state.sections.find(s => s.is_leaf);
            if (firstLeaf) {
                this.state.selectedSectionId = firstLeaf.id;
                await this._loadArticles();
                return;
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
        if (!this.state.selectedSectionId) return;
        if (resetPage) this.state.page = 0;
        this.state.loadingArticles = true;
        try {
            const r = await this._rpc("/construction_boq/load_artigos", {
                boq_id: this.boqId,
                section_id: this.state.selectedSectionId,
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
        this.state.secTotals  = t.sec_totals  || {};
        this.state.grandTotal = t.grand_total || 0;
        for (const s of this.state.sections) {
            const d = this.state.secTotals[s.id] || {};
            s.direct_total = d.total || 0;
            s.artigo_count = d.cnt   ?? s.artigo_count;
        }
        // Re-roll totals upward
        const totalMap = {};
        for (const s of this.state.sections) {
            totalMap[s.id] = s.direct_total || 0;
        }
        for (const s of [...this.state.sections].reverse()) {
            if (s.parent_id && totalMap[s.parent_id] !== undefined) {
                totalMap[s.parent_id] += totalMap[s.id];
            }
        }
        for (const s of this.state.sections) {
            s.total = totalMap[s.id] || 0;
        }
    }

    // ── Getters ────────────────────────────────────────────────────────────
    get selectedSection() {
        return this.state.sections.find(s => s.id === this.state.selectedSectionId) || null;
    }

    get visibleSections() {
        return this.state.sections.filter(s => {
            if (!s.parent_id) return true;
            let pid = s.parent_id;
            while (pid) {
                if (!this.state.expandedIds.has(pid)) return false;
                const p = this.state.sections.find(x => x.id === pid);
                pid = p ? p.parent_id : null;
            }
            return true;
        });
    }

    get totalPages()  { return Math.max(1, Math.ceil(this.state.articlesTotal / this.state.pageSize)); }

    // ── Navigation ─────────────────────────────────────────────────────────
    selectSection = async (sectionId) => {
        const sec = this.state.sections.find(s => s.id === sectionId);
        if (!sec) return;
        if (!sec.is_leaf) {
            if (this.state.expandedIds.has(sectionId)) {
                this.state.expandedIds.delete(sectionId);
            } else {
                this.state.expandedIds.add(sectionId);
            }
            return;
        }
        this.state.selectedSectionId = sectionId;
        this.state.search = "";
        await this._loadArticles();
    };

    // ── Cell save ──────────────────────────────────────────────────────────
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
                    section_id: art.section_id || this.state.selectedSectionId,
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

    onUomChange = (art, ev) => {
        const val = parseInt(ev.target.value, 10);
        this.saveCell(art, 'uom_id', isNaN(val) ? null : val);
    };

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
        if (this.state.readonly || !this.state.selectedSectionId) {
            if (!this.state.selectedSectionId)
                this.notification.add("Select a leaf section first.", { type: "warning" });
            return;
        }
        const sec = this.selectedSection;
        const code = `${sec?.code || ""}.${String(this.state.articlesTotal + 1).padStart(2, "0")}`;
        const newArt = {
            id: null, code, name: "New article",
            uom_id: null, uom_name: "",
            qty_contract: 0, price_unit: 0, total: 0,
            obs: "", show_in_stock: false,
            section_id: this.state.selectedSectionId,
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

    // ── Add section ────────────────────────────────────────────────────────
    addSection = async (parentId) => {
        if (this.state.readonly) return;
        const parent = parentId
            ? this.state.sections.find(s => s.id === parentId)
            : null;
        const defaultCode = parent
            ? `${parent.code}.${String(this.state.sections.filter(s => s.parent_id === parentId).length + 1).padStart(2, "0")}`
            : String(this.state.sections.filter(s => !s.parent_id).length + 1).padStart(2, "0");
        const name = window.prompt("Section name:", defaultCode + " — New Section");
        if (!name) return;
        const r = await this._rpc("/construction_boq/add_section", {
            boq_id: this.boqId,
            data: {
                parent_id:  parentId || null,
                code:       defaultCode,
                name,
                specialty:  "General",
                color:      "#1E3A5F",
            },
        });
        const newSec = {
            id:           r.id,
            parent_id:    parentId || null,
            code:         defaultCode,
            name,
            depth:        r.depth,
            path:         r.path,
            is_leaf:      true,
            specialty:    "General",
            total:        0,
            direct_total: 0,
            artigo_count: 0,
        };
        // Insert at correct position (path order)
        const insertIdx = this.state.sections.findIndex(
            s => s.path > r.path && s.depth <= r.depth);
        if (insertIdx === -1) {
            this.state.sections.push(newSec);
        } else {
            this.state.sections.splice(insertIdx, 0, newSec);
        }
        if (parentId) {
            const p = this.state.sections.find(s => s.id === parentId);
            if (p) p.is_leaf = false;
            this.state.expandedIds.add(parentId);
        }
        await this.selectSection(newSec.id);
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

registry.category("actions").add("construction_boq_new.editor", BOQEditorAction);
