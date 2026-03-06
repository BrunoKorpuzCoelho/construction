# -*- coding: utf-8 -*-
from odoo import models, fields


class ConstructionBOQChapter(models.Model):
    _name = 'construction.boq.capitulo'
    _description = 'BOQ Chapter'
    _order = 'boq_id, sequence'

    boq_id = fields.Many2one('construction.boq', 'BOQ', required=True,
                              ondelete='cascade', index=True)
    code = fields.Char('Code', required=True)
    name = fields.Char('Name', required=True)
    sequence = fields.Integer('Sequence', default=10)
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
    analytic_account_id = fields.Many2one('account.analytic.account', 'Cost Centre')
    subcapitulo_ids = fields.One2many(
        'construction.boq.subcapitulo', 'capitulo_id', 'Sub-Chapters')


class ConstructionBOQSubChapter(models.Model):
    _name = 'construction.boq.subcapitulo'
    _description = 'BOQ Sub-Chapter'
    _order = 'capitulo_id, sequence'

    boq_id = fields.Many2one('construction.boq', 'BOQ', required=True,
                              ondelete='cascade', index=True)
    capitulo_id = fields.Many2one('construction.boq.capitulo', 'Chapter',
                                   required=True, ondelete='cascade', index=True)
    code = fields.Char('Code', required=True)
    name = fields.Char('Name', required=True)
    sequence = fields.Integer('Sequence', default=10)
    notes = fields.Text('Notes')
    artigo_ids = fields.One2many('construction.boq.artigo', 'subcapitulo_id', 'Articles')
