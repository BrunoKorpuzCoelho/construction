# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ConstructionBOQArticle(models.Model):
    _name = 'construction.boq.artigo'
    _description = 'BOQ Article'
    _order = 'boq_id, sequence, id'

    # ── Structure ─────────────────────────────────────────────────────────────
    boq_id = fields.Many2one('construction.boq', 'BOQ', required=True,
                              ondelete='cascade', index=True)
    capitulo_id = fields.Many2one('construction.boq.capitulo', 'Chapter',
                                   required=True, ondelete='cascade', index=True)
    subcapitulo_id = fields.Many2one('construction.boq.subcapitulo', 'Sub-Chapter',
                                      required=True, ondelete='cascade', index=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    code = fields.Char('Code', index=True)
    name = fields.Char('Description', required=True)
    sequence = fields.Integer('Sequence', default=10, index=True)
    active = fields.Boolean('Active', default=True, index=True)

    # ── Odoo Product integration ──────────────────────────────────────────────
    product_id = fields.Many2one(
        'product.product', 'Odoo Product',
        domain=[('type', 'in', ['consu', 'service', 'storable'])],
        index=True,
    )
    # Category comes from product — stored for filtering
    product_categ_id = fields.Many2one(
        'product.category', 'Product Category',
        related='product_id.categ_id', store=True, readonly=True,
    )
    # UoM — plain Many2one, no related/domain tricks
    uom_id = fields.Many2one('uom.uom', 'Unit of Measure')

    # ── Quantities & Pricing ──────────────────────────────────────────────────
    qty_contract = fields.Float('Contract Qty', digits=(16, 3), default=0.0)
    price_unit = fields.Float('Unit Price', digits=(16, 4), default=0.0)
    obs = fields.Char('Notes')

    # ── Stock (optional column) ───────────────────────────────────────────────
    show_in_stock = fields.Boolean('Show in Stock View', default=False)
    qty_on_hand = fields.Float(
        'On-Hand Qty', compute='_compute_stock', digits=(16, 3), store=False)

    # ── Computed totals ───────────────────────────────────────────────────────
    currency_id = fields.Many2one(related='boq_id.currency_id', store=True)
    total_contract = fields.Monetary(
        'Contract Total', currency_field='currency_id',
        compute='_compute_total', store=True,
    )

    @api.depends('qty_contract', 'price_unit')
    def _compute_total(self):
        for r in self:
            r.total_contract = r.qty_contract * r.price_unit

    def _compute_stock(self):
        prod_ids = [r.product_id.id for r in self if r.product_id]
        stock_map = {}
        if prod_ids:
            self.env.cr.execute("""
                SELECT sq.product_id, SUM(sq.quantity) AS qty
                FROM stock_quant sq
                JOIN stock_location sl ON sl.id = sq.location_id
                WHERE sl.usage = 'internal' AND sq.product_id = ANY(%s)
                GROUP BY sq.product_id
            """, (prod_ids,))
            stock_map = {r['product_id']: float(r['qty'])
                         for r in self.env.cr.dictfetchall()}
        for rec in self:
            rec.qty_on_hand = stock_map.get(rec.product_id.id, 0.0) if rec.product_id else 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.uom_id:
                self.uom_id = self.product_id.uom_id
            if not self.name or self.name == 'New article':
                self.name = self.product_id.name
            if self.price_unit == 0.0:
                self.price_unit = self.product_id.lst_price
