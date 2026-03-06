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
    section_count = fields.Integer('Sections', compute='_compute_totals_sql', store=True)
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
                COUNT(DISTINCT s.id)                               AS sec_count,
                COUNT(a.id)                                        AS art_count
            FROM construction_boq_artigo a
            JOIN construction_boq_section s ON s.id = a.section_id
            WHERE a.boq_id = ANY(%s) AND a.active = TRUE
            GROUP BY a.boq_id
        """, (list(self.ids),))
        rows = {r['boq_id']: r for r in self.env.cr.dictfetchall()}
        for rec in self:
            d = rows.get(rec.id, {})
            rec.total_boq     = d.get('total', 0.0)
            rec.section_count = d.get('sec_count', 0)
            rec.artigo_count  = d.get('art_count', 0)

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
        self.obra_id.boq_ids.filtered(
            lambda b: b.is_active_revision and b.id != self.id
        ).write({'is_active_revision': False})
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
            'tag': 'construction_boq_new.editor',
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
                        'construction_boq_new.group_boq_manager'):
                    raise AccessError(
                        _('BOQ %s is %s and cannot be edited.')
                        % (rec.revision_label, rec.state))
        return super().write(vals)

    # ── SQL helpers ───────────────────────────────────────────────────────────
    def _sql_deep_copy_structure(self, src_boq_id, dst_boq_id):
        """
        Copy all sections (any depth) and articles from src_boq to dst_boq.
        Uses path ordering to ensure parents are inserted before children.
        """
        cr = self.env.cr
        uid = self.env.uid

        cr.execute("""
            SELECT id, parent_id, code, name, sequence, depth, path,
                   is_leaf, specialty, color, notes, analytic_account_id
            FROM construction_boq_section
            WHERE boq_id = %s
            ORDER BY path
        """, (src_boq_id,))
        sections = cr.dictfetchall()

        old_to_new = {}

        for s in sections:
            new_parent = old_to_new.get(s['parent_id'])
            cr.execute("""
                INSERT INTO construction_boq_section
                    (boq_id, parent_id, code, name, sequence, depth, path,
                     is_leaf, specialty, color, notes, analytic_account_id,
                     create_uid, write_uid, create_date, write_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, NOW(), NOW())
                RETURNING id
            """, (dst_boq_id, new_parent, s['code'], s['name'], s['sequence'],
                  s['depth'], s['path'], s['is_leaf'], s['specialty'],
                  s['color'], s['notes'], s['analytic_account_id'],
                  uid, uid))
            old_to_new[s['id']] = cr.fetchone()[0]

        if old_to_new:
            for old_sec_id, new_sec_id in old_to_new.items():
                cr.execute("""
                    INSERT INTO construction_boq_artigo
                        (boq_id, section_id, code, name,
                         product_id, uom_id, qty_contract, price_unit,
                         obs, sequence, active, show_in_stock,
                         create_uid, write_uid, create_date, write_date)
                    SELECT %s, %s, code, name,
                           product_id, uom_id, qty_contract, price_unit,
                           obs, sequence, active, show_in_stock,
                           %s, %s, NOW(), NOW()
                    FROM construction_boq_artigo
                    WHERE section_id = %s
                    ORDER BY sequence
                """, (dst_boq_id, new_sec_id, uid, uid, old_sec_id))

    # ── SQL: load tree for OWL editor ─────────────────────────────────────────
    def sql_load_boq_tree(self):
        self.ensure_one()
        cr = self.env.cr
        cr.execute("""
            SELECT
                s.id, s.parent_id, s.code, s.name, s.sequence,
                s.depth, s.path, s.is_leaf,
                s.specialty, s.color, s.notes,
                COALESCE(SUM(a.qty_contract * a.price_unit)
                         FILTER (WHERE a.active), 0)    AS direct_total,
                COUNT(a.id) FILTER (WHERE a.active)     AS artigo_count
            FROM construction_boq_section s
            LEFT JOIN construction_boq_artigo a ON a.section_id = s.id
            WHERE s.boq_id = %s
            GROUP BY s.id
            ORDER BY s.path
        """, (self.id,))
        sections = cr.dictfetchall()

        # Build subtree totals bottom-up (leaves → roots)
        total_map = {s['id']: float(s['direct_total']) for s in sections}
        for s in reversed(sections):
            if s['parent_id'] and s['parent_id'] in total_map:
                total_map[s['parent_id']] += total_map[s['id']]

        for s in sections:
            s['total'] = total_map[s['id']]
            s['direct_total'] = float(s['direct_total'])

        return {
            'boq_id':         self.id,
            'readonly':       self.state in ('shared', 'archived'),
            'state':          self.state,
            'revision_label': self.revision_label,
            'boq_name':       self.name,
            'project_name':   self.obra_id.name,
            'sections':       sections,
        }

    # ── SQL: load articles ────────────────────────────────────────────────────
    def sql_load_artigos(self, section_id, search=None, offset=0, limit=150):
        self.ensure_one()
        cr = self.env.cr
        params = [self.id, int(section_id)]
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
                   a.section_id
            FROM construction_boq_artigo a
            LEFT JOIN uom_uom u           ON u.id  = a.uom_id
            LEFT JOIN product_product pp  ON pp.id = a.product_id
            LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE a.boq_id = %s AND a.section_id = %s AND a.active = TRUE
            {extra}
            ORDER BY a.sequence, a.id
            LIMIT %s OFFSET %s
        """, params + [int(limit), int(offset)])
        artigos = cr.dictfetchall()
        for a in artigos:
            a['qty_contract'] = float(a['qty_contract'] or 0)
            a['price_unit']   = float(a['price_unit'] or 0)
            a['total']        = float(a['total'] or 0)
        count_params = [self.id, int(section_id)]
        count_extra = ''
        if search:
            count_extra = ' AND (a.code ILIKE %s OR a.name ILIKE %s)'
            count_params += [f'%{search}%', f'%{search}%']
        cr.execute(f"""
            SELECT COUNT(*) FROM construction_boq_artigo a
            WHERE a.boq_id = %s AND a.section_id = %s AND a.active = TRUE {count_extra}
        """, count_params)
        return {'artigos': artigos, 'total': cr.fetchone()[0]}

    # ── SQL: save article ─────────────────────────────────────────────────────
    def sql_save_artigo(self, artigo_data):
        self.ensure_one()
        if self.state in ('shared', 'archived'):
            raise AccessError(_('BOQ is locked — articles cannot be edited.'))
        cr  = self.env.cr
        uid = self.env.uid
        art_id  = artigo_data.get('id')
        sec_id  = int(artigo_data.get('section_id', 0))
        code    = artigo_data.get('code') or ''
        name    = artigo_data.get('name') or 'New article'
        uom_id  = artigo_data.get('uom_id') or None
        prod_id = artigo_data.get('product_id') or None
        qty     = float(artigo_data.get('qty_contract') or 0)
        pu      = float(artigo_data.get('price_unit') or 0)
        obs     = artigo_data.get('obs') or ''
        stock   = bool(artigo_data.get('show_in_stock'))

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
            cr.execute("""
                INSERT INTO construction_boq_artigo
                    (boq_id, section_id, code, name,
                     uom_id, product_id, qty_contract, price_unit, obs,
                     show_in_stock, sequence, active,
                     create_uid, write_uid, create_date, write_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    (SELECT COALESCE(MAX(sequence),0)+10
                     FROM construction_boq_artigo WHERE section_id=%s),
                    TRUE,%s,%s,NOW(),NOW())
                RETURNING id
            """, (self.id, sec_id, code, name, uom_id, prod_id,
                  qty, pu, obs, stock, sec_id, uid, uid))
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

    def sql_add_section(self, data):
        """
        Add a section at any depth. data must contain:
          code, name, parent_id (int or None), specialty, color, notes
        """
        self.ensure_one()
        if self.state in ('shared', 'archived'):
            raise AccessError(_('BOQ is locked.'))
        cr  = self.env.cr
        uid = self.env.uid
        parent_id = data.get('parent_id') or None

        if parent_id:
            cr.execute("SELECT depth, path FROM construction_boq_section WHERE id=%s",
                       (parent_id,))
            row = cr.fetchone()
            depth       = (row[0] if row else 0) + 1
            parent_path = row[1] if row else ''
        else:
            depth       = 0
            parent_path = ''

        cr.execute("""
            SELECT COALESCE(MAX(sequence), 0) + 10 FROM construction_boq_section
            WHERE boq_id = %s AND (parent_id = %s OR (parent_id IS NULL AND %s IS NULL))
        """, (self.id, parent_id, parent_id))
        seq = cr.fetchone()[0]

        seg  = str(seq).zfill(4)
        path = f"{parent_path}.{seg}" if parent_path else seg

        cr.execute("""
            INSERT INTO construction_boq_section
                (boq_id, parent_id, code, name, sequence, depth, path,
                 is_leaf, specialty, color, notes,
                 create_uid, write_uid, create_date, write_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s,%s,%s,NOW(),NOW())
            RETURNING id
        """, (self.id, parent_id, data.get('code', ''), data.get('name', ''),
              seq, depth, path,
              data.get('specialty', 'General'),
              data.get('color', '#1E3A5F'),
              data.get('notes', ''),
              uid, uid))
        new_id = cr.fetchone()[0]

        if parent_id:
            cr.execute("""
                UPDATE construction_boq_section
                SET is_leaf=FALSE, write_uid=%s, write_date=NOW()
                WHERE id=%s
            """, (uid, parent_id))

        return {
            'id': new_id, 'depth': depth, 'path': path, 'sequence': seq
        }

    # ── AI context builder ────────────────────────────────────────────────────
    def build_ai_context(self):
        self.ensure_one()
        cr = self.env.cr
        cr.execute("""
            SELECT s.id, s.code, s.name, s.specialty, s.depth, s.path,
                   COUNT(a.id) FILTER (WHERE a.active) AS art_count,
                   COALESCE(SUM(a.qty_contract * a.price_unit)
                            FILTER (WHERE a.active), 0) AS total
            FROM construction_boq_section s
            LEFT JOIN construction_boq_artigo a ON a.section_id = s.id
            WHERE s.boq_id = %s
            GROUP BY s.id
            ORDER BY s.path
        """, (self.id,))
        sections = cr.dictfetchall()

        cr.execute("""
            SELECT COALESCE(SUM(qty_contract * price_unit), 0) AS grand_total,
                   COUNT(*) FILTER (WHERE active) AS total_articles
            FROM construction_boq_artigo WHERE boq_id = %s
        """, (self.id,))
        row = cr.fetchone()
        grand_total    = float(row[0])
        total_articles = row[1]

        root_sections = [s for s in sections if s['depth'] == 0]
        lines = [
            f"PROJECT: {self.obra_id.name}",
            f"BOQ: {self.name} {self.revision_label} | Status: {self.state}",
            f"Grand Total: €{grand_total:,.2f} | Total Articles: {total_articles}",
            f"Root Chapters: {len(root_sections)}", "",
        ]
        for s in root_sections:
            pct = float(s['total']) / grand_total * 100 if grand_total else 0
            lines.append(
                f"[{s['code']}] {s['name']} ({s['specialty']}) — "
                f"{s['art_count']} articles — €{float(s['total']):,.2f} ({pct:.1f}%)"
            )
        return "\n".join(lines), grand_total, total_articles, sections
