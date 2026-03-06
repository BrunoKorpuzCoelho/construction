# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class BOQController(http.Controller):

    def _boq(self, boq_id):
        boq = request.env['construction.boq'].browse(int(boq_id))
        if not boq.exists():
            raise UserError('BOQ not found.')
        return boq

    @http.route('/construction_boq/load_tree', type='jsonrpc', auth='user', methods=['POST'])
    def load_tree(self, **kw):
        return self._boq(kw['boq_id']).sql_load_boq_tree()

    @http.route('/construction_boq/load_artigos', type='jsonrpc', auth='user', methods=['POST'])
    def load_artigos(self, **kw):
        return self._boq(kw['boq_id']).sql_load_artigos(
            kw['section_id'],
            search=kw.get('search'),
            offset=int(kw.get('offset', 0)),
            limit=int(kw.get('limit', 150)),
        )

    @http.route('/construction_boq/save_artigo', type='jsonrpc', auth='user', methods=['POST'])
    def save_artigo(self, **kw):
        return self._boq(kw['boq_id']).sql_save_artigo(kw['artigo'])

    @http.route('/construction_boq/delete_artigo', type='jsonrpc', auth='user', methods=['POST'])
    def delete_artigo(self, **kw):
        self._boq(kw['boq_id']).sql_delete_artigo(kw['artigo_id'])
        return {'ok': True}

    @http.route('/construction_boq/add_section', type='jsonrpc', auth='user', methods=['POST'])
    def add_section(self, **kw):
        return self._boq(kw['boq_id']).sql_add_section(kw['data'])

    @http.route('/construction_boq/search_products', type='jsonrpc', auth='user', methods=['POST'])
    def search_products(self, **kw):
        return request.env['product.product'].search_read(
            [('name', 'ilike', kw.get('query', '')), ('active', '=', True)],
            fields=['id', 'name', 'default_code', 'uom_id', 'lst_price'],
            limit=int(kw.get('limit', 20)),
        )

    @http.route('/construction_boq/search_uoms', type='jsonrpc', auth='user', methods=['POST'])
    def search_uoms(self, **kw):
        query = kw.get('query', '')
        dom = [('active', '=', True)]
        if query:
            dom.append(('name', 'ilike', query))
        return request.env['uom.uom'].search_read(dom, fields=['id', 'name'],
                                                   limit=int(kw.get('limit', 50)))

    @http.route('/construction_boq/get_totals', type='jsonrpc', auth='user', methods=['POST'])
    def get_totals(self, **kw):
        boq = self._boq(kw['boq_id'])
        cr  = request.env.cr

        cr.execute("""
            SELECT s.id AS sec_id,
                   COALESCE(SUM(a.qty_contract * a.price_unit)
                            FILTER (WHERE a.active), 0) AS total,
                   COUNT(a.id) FILTER (WHERE a.active) AS cnt
            FROM construction_boq_section s
            LEFT JOIN construction_boq_artigo a ON a.section_id = s.id
            WHERE s.boq_id = %s
            GROUP BY s.id
        """, (boq.id,))
        sec_totals = {
            r['sec_id']: {'total': float(r['total']), 'cnt': r['cnt']}
            for r in cr.dictfetchall()
        }

        cr.execute("""
            SELECT COALESCE(SUM(qty_contract * price_unit), 0)
            FROM construction_boq_artigo WHERE boq_id=%s AND active=TRUE
        """, (boq.id,))
        grand = float(cr.fetchone()[0])

        return {'sec_totals': sec_totals, 'grand_total': grand}

    @http.route('/construction_boq/ai_query', type='jsonrpc', auth='user', methods=['POST'])
    def ai_query(self, **kw):
        boq = self._boq(kw['boq_id'])
        question = kw.get('question', '')
        history = kw.get('history') or []
        boq_context, grand_total, total_articles, sections = boq.build_ai_context()

        system_prompt = (
            "You are an expert construction quantity surveyor (QS). "
            "Analyse the BOQ data and answer concisely. "
            "Use Markdown: **bold** for key figures, - bullet lists.\n\n"
            "BOQ CONTEXT:\n" + boq_context
        )

        try:
            IAI = request.env.get('llm.provider') or request.env.get('mail.ai.provider')
            if IAI:
                provider = IAI.search([], limit=1)
                if provider:
                    return {'answer': provider.generate_text(
                        prompt=question, system=system_prompt, max_tokens=800),
                            'source': 'odoo_ai'}
        except Exception as e:
            _logger.info('Odoo AI not available: %s', e)

        try:
            cfg = request.env['ir.config_parameter'].sudo()
            key = cfg.get_param('openai.api_key') or cfg.get_param('ai.api_key')
            if key:
                import urllib.request, json as _j
                msgs = [{'role': 'system', 'content': system_prompt}]
                msgs += [{'role': m['role'], 'content': m['content']} for m in history]
                msgs.append({'role': 'user', 'content': question})
                req = urllib.request.Request(
                    'https://api.openai.com/v1/chat/completions',
                    data=_j.dumps({'model': 'gpt-4o-mini', 'messages': msgs,
                                   'max_tokens': 800}).encode(),
                    headers={'Authorization': f'Bearer {key}',
                             'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = _j.loads(resp.read())
                    return {'answer': data['choices'][0]['message']['content'],
                            'source': 'openai'}
        except Exception as e:
            _logger.info('OpenAI not available: %s', e)

        return {'answer': _builtin(question, sections, grand_total, total_articles),
                'source': 'builtin',
                'hint': 'Set openai.api_key in Settings > Technical > Parameters for AI answers.'}


def _builtin(q, sections, grand_total, total_articles):
    q = q.lower()
    root_sections = [s for s in sections if s['depth'] == 0]
    if any(w in q for w in ['total', 'value', 'cost', 'amount']):
        lines = [f'**Grand Total: €{grand_total:,.2f}**\n']
        for s in sorted(root_sections, key=lambda x: float(x['total']), reverse=True):
            pct = float(s['total']) / grand_total * 100 if grand_total else 0
            lines.append(f'- **{s["code"]}** {s["name"]}: €{float(s["total"]):,.2f} ({pct:.1f}%)')
        return '\n'.join(lines)
    if any(w in q for w in ['chapter', 'breakdown', 'structure', 'section']):
        lines = [f'**{len(root_sections)} root sections, {total_articles} articles:**\n']
        for s in root_sections:
            lines.append(f'- **{s["code"]}** {s["name"]} ({s["specialty"]}) — {s["art_count"]} art. — €{float(s["total"]):,.2f}')
        return '\n'.join(lines)
    if any(w in q for w in ['largest', 'biggest', 'top']):
        top = sorted(root_sections, key=lambda x: float(x['total']), reverse=True)[:3]
        lines = ['**Top 3 by value:**\n']
        for i, s in enumerate(top, 1):
            pct = float(s['total']) / grand_total * 100 if grand_total else 0
            lines.append(f'{i}. **{s["code"]} {s["name"]}**: €{float(s["total"]):,.2f} ({pct:.1f}%)')
        return '\n'.join(lines)
    if any(w in q for w in ['article', 'item', 'count', 'how many']):
        lines = [f'**{total_articles} articles across {len(root_sections)} root sections:**\n']
        for s in root_sections:
            lines.append(f'- **{s["code"]}**: {s["art_count"]} articles')
        return '\n'.join(lines)
    if any(w in q for w in ['specialty', 'hvac', 'bms', 'electrical']):
        by_spec = {}
        for s in root_sections:
            sp = s['specialty']
            by_spec.setdefault(sp, {'total': 0.0, 'cnt': 0})
            by_spec[sp]['total'] += float(s['total'])
            by_spec[sp]['cnt'] += s['art_count']
        lines = ['**By specialty:**\n']
        for sp, d in sorted(by_spec.items(), key=lambda x: x[1]['total'], reverse=True):
            pct = d['total'] / grand_total * 100 if grand_total else 0
            lines.append(f'- **{sp}**: €{d["total"]:,.2f} ({pct:.1f}%) — {d["cnt"]} articles')
        return '\n'.join(lines)
    return (f'**BOQ: {len(root_sections)} root sections, {total_articles} articles, '
            f'€{grand_total:,.2f} total**\n\n'
            '💡 Try: "show totals", "largest section", "by specialty", "how many articles"')
