# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)


class ConstructionBOQ(models.Model):
    _name = 'construction.boq'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Bill of Quantities'
    _order = 'obra_id, version desc'

    # ── Identity ──────────────────────────────────────────────────────────────
    obra_id = fields.Many2one('construction.obra', 'Project', required=True,
                               ondelete='cascade', index=True, tracking=True)
    name = fields.Char('BOQ Name', required=True, tracking=True,
                        default=lambda self: _('Bill of Quantities'))
    version = fields.Integer('Version', default=1, readonly=True, tracking=True)
    revision_label = fields.Char('Rev.', compute='_compute_revision_label', store=True)

    # ── Revision system ───────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('shared', 'Shared (locked)'),
        ('archived', 'Archived'),
    ], 'Status', default='draft', required=True, tracking=True, index=True)

    is_active_revision = fields.Boolean('Active Revision', default=True, tracking=True)
    parent_revision_id = fields.Many2one('construction.boq', 'Previous Revision',
                                          readonly=True)
    child_revision_ids = fields.One2many('construction.boq', 'parent_revision_id',
                                          'Following Revisions')

    date_created = fields.Datetime('Created On', default=fields.Datetime.now, readonly=True)
    date_shared = fields.Datetime('Shared On', readonly=True)
    date_archived = fields.Datetime('Archived On', readonly=True)
    user_id = fields.Many2one('res.users', 'Created By',
                               default=lambda self: self.env.user, readonly=True)
    shared_by_id = fields.Many2one('res.users', 'Shared By', readonly=True)
    notes = fields.Text('Notes')

    # ── Totals (via SQL for performance) ──────────────────────────────────────
    currency_id = fields.Many2one(related='obra_id.currency_id', store=True)
    total_boq = fields.Monetary('BOQ Total', currency_field='currency_id',
                                  compute='_compute_totals_sql', store=True)
    capitulo_count = fields.Integer('Chapters', compute='_compute_totals_sql', store=True)
    artigo_count = fields.Integer('Articles', compute='_compute_totals_sql', store=True)

    # ── Computed ──────────────────────────────────────────────────────────────
    @api.depends('version')
    def _compute_revision_label(self):
        for r in self:
            r.revision_label = f'Rev.{r.version:02d}'

    def _compute_totals_sql(self):
        if not self.ids:
            return
        self.env.cr.execute("""
            SELECT
                a.boq_id,
                COALESCE(SUM(a.qty_contract * a.price_unit), 0.0) AS total,
                COUNT(DISTINCT c.id)                               AS cap_count,
                COUNT(a.id)                                        AS art_count
            FROM construction_boq_artigo a
            JOIN construction_boq_subcapitulo sc ON sc.id = a.subcapitulo_id
            JOIN construction_boq_capitulo    c  ON c.id  = sc.capitulo_id
            WHERE a.boq_id = ANY(%s) AND a.active = TRUE
            GROUP BY a.boq_id
        """, (list(self.ids),))
        rows = {r['boq_id']: r for r in self.env.cr.dictfetchall()}
        for rec in self:
            d = rows.get(rec.id, {})
            rec.total_boq = d.get('total', 0.0)
            rec.capitulo_count = d.get('cap_count', 0)
            rec.artigo_count = d.get('art_count', 0)

    # ── State transitions ─────────────────────────────────────────────────────
    def action_share(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft BOQs can be shared.'))
            rec.write({
                'state': 'shared',
                'date_shared': fields.Datetime.now(),
                'shared_by_id': self.env.user.id,
            })
            rec.message_post(
                body=_('BOQ <b>%s</b> shared by %s — now read-only.')
                     % (rec.revision_label, self.env.user.name),
                message_type='notification',
            )

    def action_new_revision(self):
        self.ensure_one()
        if self.state != 'shared':
            raise UserError(_('A new revision can only be created from a shared BOQ.'))
        # Deactivate all active revisions for this project
        self.obra_id.boq_ids.filtered(
            lambda b: b.is_active_revision and b.id != self.id
        ).write({'is_active_revision': False})
        # Create new BOQ record
        new_boq = self.copy({
            'version': self.version + 1,
            'state': 'draft',
            'is_active_revision': True,
            'parent_revision_id': self.id,
            'date_created': fields.Datetime.now(),
            'date_shared': False,
            'shared_by_id': False,
            'user_id': self.env.user.id,
        })
        # Deep-copy structure via SQL (fast even for 10k+ articles)
        self._sql_deep_copy_structure(self.id, new_boq.id)
        self.write({'is_active_revision': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'construction.boq',
            'res_id': new_boq.id,
            'view_mode': 'form',
        }

    def action_archive_boq(self):
        self.write({'state': 'archived', 'date_archived': fields.Datetime.now()})

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'archived':
                rec.write({'state': 'draft', 'date_archived': False})

    def action_open_editor(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'construction_boq.editor',
            'name': _('BOQ Editor — %s %s') % (
                self.obra_id.name, self.revision_label),
            'context': {
                'boq_id': self.id,
                'readonly': self.state in ('shared', 'archived'),
            },
            'target': 'current',
        }

    # ── Odoo 19 write guard ────────────────────────────────────────────────────
    def write(self, vals):
        meta_only = {
            'state', 'is_active_revision', 'date_archived', 'date_shared',
            'shared_by_id', 'notes', 'message_follower_ids',
            'activity_ids', 'message_ids',
        }
        content_keys = set(vals.keys()) - meta_only
        if content_keys:
            for rec in self:
                if rec.state in ('shared', 'archived') and not self.env.user.has_group(
                        'construction_boq.group_boq_manager'):
                    raise AccessError(
                        _('BOQ %s is %s and cannot be edited.')
                        % (rec.revision_label, rec.state))
        return super().write(vals)

    # ── SQL helpers ───────────────────────────────────────────────────────────
    def _sql_deep_copy_structure(self, src_boq_id, dst_boq_id):
        cr = self.env.cr
        uid = self.env.uid
        # Chapters
        cr.execute("""
            INSERT INTO construction_boq_capitulo
                (boq_id, code, name, sequence, specialty, analytic_account_id,
                 color, notes, create_uid, write_uid, create_date, write_date)
            SELECT %s, code, name, sequence, specialty, analytic_account_id,
                   color, notes, %s, %s, NOW(), NOW()
            FROM construction_boq_capitulo
            WHERE boq_id = %s ORDER BY sequence
            RETURNING id
        """, (dst_boq_id, uid, uid, src_boq_id))
        new_cap_ids = [r[0] for r in cr.fetchall()]
        cr.execute("SELECT id FROM construction_boq_capitulo WHERE boq_id=%s ORDER BY sequence",
                   (src_boq_id,))
        old_cap_ids = [r[0] for r in cr.fetchall()]
        cap_map = dict(zip(old_cap_ids, new_cap_ids))
        if not cap_map:
            return
        # Sub-chapters and articles per chapter
        for old_cap, new_cap in cap_map.items():
            cr.execute("""
                INSERT INTO construction_boq_subcapitulo
                    (boq_id, capitulo_id, code, name, sequence, notes,
                     create_uid, write_uid, create_date, write_date)
                SELECT %s, %s, code, name, sequence, notes, %s, %s, NOW(), NOW()
                FROM construction_boq_subcapitulo
                WHERE capitulo_id = %s ORDER BY sequence
                RETURNING id
            """, (dst_boq_id, new_cap, uid, uid, old_cap))
            new_sub_ids = [r[0] for r in cr.fetchall()]
            cr.execute("""
                SELECT id FROM construction_boq_subcapitulo
                WHERE capitulo_id=%s ORDER BY sequence
            """, (old_cap,))
            old_sub_ids = [r[0] for r in cr.fetchall()]
            sub_map = dict(zip(old_sub_ids, new_sub_ids))
            for old_sub, new_sub in sub_map.items():
                cr.execute("""
                    INSERT INTO construction_boq_artigo
                        (boq_id, capitulo_id, subcapitulo_id, code, name,
                         product_id, uom_id, qty_contract, price_unit,
                         obs, sequence, active, show_in_stock,
                         create_uid, write_uid, create_date, write_date)
                    SELECT %s, %s, %s, code, name,
                           product_id, uom_id, qty_contract, price_unit,
                           obs, sequence, active, show_in_stock,
                           %s, %s, NOW(), NOW()
                    FROM construction_boq_artigo
                    WHERE subcapitulo_id=%s ORDER BY sequence
                """, (dst_boq_id, new_cap, new_sub, uid, uid, old_sub))

    # ── SQL: load tree for OWL editor ─────────────────────────────────────────
    def sql_load_boq_tree(self):
        self.ensure_one()
        cr = self.env.cr
        cr.execute("""
            SELECT c.id, c.code, c.name, c.sequence, c.specialty, c.color, c.notes,
                   COALESCE((
                       SELECT SUM(a.qty_contract * a.price_unit)
                       FROM construction_boq_artigo a
                       JOIN construction_boq_subcapitulo sc ON sc.id = a.subcapitulo_id
                       WHERE sc.capitulo_id = c.id AND a.active = TRUE
                   ), 0) AS total
            FROM construction_boq_capitulo c
            WHERE c.boq_id = %s ORDER BY c.sequence
        """, (self.id,))
        caps = cr.dictfetchall()
        cap_ids = [c['id'] for c in caps]
        if cap_ids:
            cr.execute("""
                SELECT sc.id, sc.capitulo_id, sc.code, sc.name, sc.sequence, sc.notes,
                       COALESCE(SUM(a.qty_contract * a.price_unit) FILTER (WHERE a.active), 0) AS total,
                       COUNT(a.id) FILTER (WHERE a.active) AS artigo_count
                FROM construction_boq_subcapitulo sc
                LEFT JOIN construction_boq_artigo a ON a.subcapitulo_id = sc.id
                WHERE sc.capitulo_id = ANY(%s)
                GROUP BY sc.id ORDER BY sc.sequence
            """, (cap_ids,))
            subs = cr.dictfetchall()
            sub_by_cap = {}
            for s in subs:
                sub_by_cap.setdefault(s['capitulo_id'], []).append(s)
            for cap in caps:
                cap['subcapitulos'] = sub_by_cap.get(cap['id'], [])
                cap['total'] = float(cap['total'])
        return {
            'boq_id': self.id,
            'readonly': self.state in ('shared', 'archived'),
            'state': self.state,
            'revision_label': self.revision_label,
            'boq_name': self.name,
            'project_name': self.obra_id.name,
            'capitulos': caps,
        }

    # ── SQL: load articles ────────────────────────────────────────────────────
    def sql_load_artigos(self, subcapitulo_id, search=None, offset=0, limit=150):
        self.ensure_one()
        cr = self.env.cr
        params = [self.id, int(subcapitulo_id)]
        extra = ''
        if search:
            extra = ' AND (a.code ILIKE %s OR a.name ILIKE %s)'
            params += [f'%{search}%', f'%{search}%']
        cr.execute(f"""
            SELECT a.id, a.code, a.name, a.sequence,
                   a.qty_contract, a.price_unit,
                   COALESCE(a.qty_contract * a.price_unit, 0) AS total,
                   a.obs, a.show_in_stock,
                   a.uom_id,    u.name AS uom_name,
                   a.product_id, pp.default_code AS product_ref,
                   pt.name      AS product_name,
                   a.capitulo_id, a.subcapitulo_id
            FROM construction_boq_artigo a
            LEFT JOIN uom_uom u           ON u.id  = a.uom_id
            LEFT JOIN product_product pp  ON pp.id = a.product_id
            LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE a.boq_id = %s AND a.subcapitulo_id = %s AND a.active = TRUE
            {extra}
            ORDER BY a.sequence, a.id
            LIMIT %s OFFSET %s
        """, params + [int(limit), int(offset)])
        artigos = cr.dictfetchall()
        # Convert Decimal to float for JSON serialisation
        for a in artigos:
            a['qty_contract'] = float(a['qty_contract'] or 0)
            a['price_unit'] = float(a['price_unit'] or 0)
            a['total'] = float(a['total'] or 0)
        # Count
        count_params = [self.id, int(subcapitulo_id)]
        count_extra = ''
        if search:
            count_extra = ' AND (a.code ILIKE %s OR a.name ILIKE %s)'
            count_params += [f'%{search}%', f'%{search}%']
        cr.execute(f"""
            SELECT COUNT(*) FROM construction_boq_artigo a
            WHERE a.boq_id = %s AND a.subcapitulo_id = %s AND a.active = TRUE {count_extra}
        """, count_params)
        return {'artigos': artigos, 'total': cr.fetchone()[0]}

    # ── SQL: save article ─────────────────────────────────────────────────────
    def sql_save_artigo(self, artigo_data):
        self.ensure_one()
        if self.state in ('shared', 'archived'):
            raise AccessError(_('BOQ is locked — articles cannot be edited.'))
        cr = self.env.cr
        uid = self.env.uid
        art_id = artigo_data.get('id')
        code = artigo_data.get('code') or ''
        name = artigo_data.get('name') or 'New article'
        uom_id = artigo_data.get('uom_id') or None
        prod_id = artigo_data.get('product_id') or None
        qty = float(artigo_data.get('qty_contract') or 0)
        pu = float(artigo_data.get('price_unit') or 0)
        obs = artigo_data.get('obs') or ''
        stock = bool(artigo_data.get('show_in_stock'))
        if art_id:
            cr.execute("""
                UPDATE construction_boq_artigo
                SET code=%s, name=%s, uom_id=%s, product_id=%s,
                    qty_contract=%s, price_unit=%s, obs=%s,
                    show_in_stock=%s, write_uid=%s, write_date=NOW()
                WHERE id=%s AND boq_id=%s RETURNING id
            """, (code, name, uom_id, prod_id, qty, pu, obs, stock,
                  uid, int(art_id), self.id))
            row = cr.fetchone()
            return {'id': row[0] if row else None, 'action': 'updated'}
        else:
            cap_id = int(artigo_data.get('capitulo_id', 0))
            sub_id = int(artigo_data.get('subcapitulo_id', 0))
            cr.execute("""
                INSERT INTO construction_boq_artigo
                    (boq_id, capitulo_id, subcapitulo_id, code, name,
                     uom_id, product_id, qty_contract, price_unit, obs,
                     show_in_stock, sequence, active,
                     create_uid, write_uid, create_date, write_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    (SELECT COALESCE(MAX(sequence),0)+10
                     FROM construction_boq_artigo WHERE subcapitulo_id=%s),
                    TRUE,%s,%s,NOW(),NOW())
                RETURNING id
            """, (self.id, cap_id, sub_id, code, name, uom_id, prod_id,
                  qty, pu, obs, stock, sub_id, uid, uid))
            return {'id': cr.fetchone()[0], 'action': 'created'}

    def sql_delete_artigo(self, artigo_id):
        self.ensure_one()
        if self.state in ('shared', 'archived'):
            raise AccessError(_('BOQ is locked.'))
        self.env.cr.execute("""
            UPDATE construction_boq_artigo
            SET active=FALSE, write_uid=%s, write_date=NOW()
            WHERE id=%s AND boq_id=%s
        """, (self.env.uid, int(artigo_id), self.id))

    def sql_add_capitulo(self, data):
        self.ensure_one()
        if self.state in ('shared', 'archived'):
            raise AccessError(_('BOQ is locked.'))
        cr = self.env.cr
        cr.execute("""
            INSERT INTO construction_boq_capitulo
                (boq_id, code, name, sequence, specialty, color, notes,
                 create_uid, write_uid, create_date, write_date)
            VALUES (%s,%s,%s,
                (SELECT COALESCE(MAX(sequence),0)+10
                 FROM construction_boq_capitulo WHERE boq_id=%s),
                %s,%s,%s,%s,%s,NOW(),NOW())
            RETURNING id
        """, (self.id, data.get('code',''), data.get('name',''),
              self.id, data.get('specialty','General'),
              data.get('color','#1E3A5F'), data.get('notes',''),
              self.env.uid, self.env.uid))
        return {'id': cr.fetchone()[0]}

    def sql_add_subcapitulo(self, data):
        self.ensure_one()
        if self.state in ('shared', 'archived'):
            raise AccessError(_('BOQ is locked.'))
        cr = self.env.cr
        cap_id = int(data['capitulo_id'])
        cr.execute("""
            INSERT INTO construction_boq_subcapitulo
                (boq_id, capitulo_id, code, name, sequence, notes,
                 create_uid, write_uid, create_date, write_date)
            VALUES (%s,%s,%s,%s,
                (SELECT COALESCE(MAX(sequence),0)+10
                 FROM construction_boq_subcapitulo WHERE capitulo_id=%s),
                %s,%s,%s,NOW(),NOW())
            RETURNING id
        """, (self.id, cap_id, data.get('code',''), data.get('name',''),
              cap_id, data.get('notes',''), self.env.uid, self.env.uid))
        return {'id': cr.fetchone()[0]}

    # ── AI context builder ────────────────────────────────────────────────────
    def build_ai_context(self):
        """Build a text summary of the BOQ for the AI assistant."""
        self.ensure_one()
        cr = self.env.cr
        cr.execute("""
            SELECT c.code, c.name, c.specialty,
                   COUNT(DISTINCT sc.id) AS sub_count,
                   COUNT(a.id) FILTER (WHERE a.active) AS art_count,
                   COALESCE(SUM(a.qty_contract * a.price_unit)
                            FILTER (WHERE a.active), 0) AS total
            FROM construction_boq_capitulo c
            LEFT JOIN construction_boq_subcapitulo sc ON sc.capitulo_id = c.id
            LEFT JOIN construction_boq_artigo a ON a.subcapitulo_id = sc.id
            WHERE c.boq_id = %s
            GROUP BY c.id, c.code, c.name, c.specialty
            ORDER BY c.sequence
        """, (self.id,))
        chapters = cr.dictfetchall()
        cr.execute("""
            SELECT COALESCE(SUM(qty_contract * price_unit), 0) AS grand_total,
                   COUNT(*) FILTER (WHERE active) AS total_articles
            FROM construction_boq_artigo WHERE boq_id = %s
        """, (self.id,))
        row = cr.fetchone()
        grand_total = float(row[0])
        total_articles = row[1]
        lines = [
            f"PROJECT: {self.obra_id.name}",
            f"BOQ: {self.name} {self.revision_label} | Status: {self.state}",
            f"Grand Total: €{grand_total:,.2f} | Total Articles: {total_articles}",
            f"Chapters: {len(chapters)}", "",
        ]
        for ch in chapters:
            pct = float(ch['total']) / grand_total * 100 if grand_total else 0
            lines.append(
                f"  [{ch['code']}] {ch['name']} ({ch['specialty']}) — "
                f"{ch['art_count']} articles — €{float(ch['total']):,.2f} ({pct:.1f}%)"
            )
        return "\n".join(lines), grand_total, total_articles, chapters
