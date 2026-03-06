# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ConstructionBOQSection(models.Model):
    _name = 'construction.boq.section'
    _description = 'BOQ Section'
    _order = 'path, sequence'

    boq_id = fields.Many2one(
        'construction.boq', 'BOQ', required=True,
        ondelete='cascade', index=True)
    parent_id = fields.Many2one(
        'construction.boq.section', 'Parent Section',
        ondelete='cascade', index=True,
        domain="[('boq_id','=',boq_id),('is_leaf','=',False)]")
    child_ids = fields.One2many(
        'construction.boq.section', 'parent_id', 'Children')

    code = fields.Char('Code', required=True)
    name = fields.Char('Name', required=True)
    sequence = fields.Integer('Sequence', default=10, index=True)

    depth = fields.Integer('Depth', default=0, readonly=True,
                           compute='_compute_depth', store=True)
    path = fields.Char('Sort Path', index=True, readonly=True,
                       compute='_compute_path', store=True)
    is_leaf = fields.Boolean('Is Leaf Node', default=True, index=True)

    specialty = fields.Selection([
        ('General', 'General'),
        ('Structure', 'Structure'),
        ('HVAC', 'HVAC'),
        ('BMS', 'BMS / Automation'),
        ('Electrical', 'Electrical'),
        ('Hydraulic', 'Hydraulic / Plumbing'),
        ('Fire', 'Fire Protection'),
        ('External', 'External Works'),
        ('Foundations', 'Foundations'),
        ('Architecture', 'Architecture / Finishes'),
        ('Maintenance', 'Maintenance'),
    ], 'Specialty', default='General')
    color = fields.Char('Colour', default='#1E3A5F')
    notes = fields.Text('Notes')
    analytic_account_id = fields.Many2one(
        'account.analytic.account', 'Cost Centre')

    @api.depends('parent_id')
    def _compute_depth(self):
        for rec in self:
            rec.depth = 0 if not rec.parent_id else rec.parent_id.depth + 1

    @api.depends('sequence', 'parent_id', 'parent_id.path')
    def _compute_path(self):
        for rec in self:
            seg = str(rec.sequence).zfill(4)
            if rec.parent_id and rec.parent_id.path:
                rec.path = f"{rec.parent_id.path}.{seg}"
            else:
                rec.path = seg

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.parent_id:
                rec.parent_id.is_leaf = False
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'parent_id' in vals and vals.get('parent_id'):
            parent = self.env['construction.boq.section'].browse(vals['parent_id'])
            parent.is_leaf = False
        return result

    def unlink(self):
        parents = self.mapped('parent_id')
        result = super().unlink()
        for parent in parents:
            if parent.exists() and not parent.child_ids:
                parent.is_leaf = True
        return result
