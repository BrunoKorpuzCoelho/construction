# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ConstructionObra(models.Model):
    _name = 'construction.obra'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Construction Project'
    _order = 'date_start desc, name'

    # ── Identity ─────────────────────────────────────────────────────────────
    name = fields.Char('Project Name', required=True, tracking=True)
    ref_interna = fields.Char(
        'Internal Ref', copy=False, tracking=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('construction.obra'),
    )
    ref_concurso = fields.Char('Tender Reference', tracking=True)

    # ── Partners ──────────────────────────────────────────────────────────────
    partner_id = fields.Many2one('res.partner', 'Client', required=True,
                                  tracking=True, index=True)
    partner_fiscalizacao_id = fields.Many2one('res.partner', 'Supervision / Engineer')
    user_id = fields.Many2one('res.users', 'Project Manager',
                               default=lambda self: self.env.user, tracking=True)
    company_id = fields.Many2one('res.company', 'Company', required=True,
                                  default=lambda self: self.env.company)

    # ── Classification ────────────────────────────────────────────────────────
    tipo_empreitada = fields.Selection([
        ('direct', 'Direct Award'),
        ('public_tender', 'Public Tender'),
        ('consultation', 'Market Consultation'),
        ('public_works', 'Public Works Contract'),
    ], 'Contract Type', required=True, default='direct', tracking=True)

    tipo_obra = fields.Selection([
        ('new_build', 'New Build'),
        ('rehabilitation', 'Rehabilitation / Renovation'),
        ('hvac', 'HVAC / Climatisation'),
        ('bms', 'BMS / Building Automation'),
        ('electrical', 'Electrical / Telecom'),
        ('hydraulic', 'Hydraulic / Sanitation'),
        ('infrastructure', 'Infrastructure'),
        ('industrial', 'Industrial'),
        ('maintenance', 'Maintenance'),
        ('mixed', 'Mixed / Multi-specialty'),
    ], 'Project Type', required=True, default='new_build', tracking=True)

    state = fields.Selection([
        ('prospect', 'Prospect'),
        ('proposal', 'Proposal'),
        ('awarded', 'Awarded'),
        ('in_progress', 'In Progress'),
        ('suspended', 'Suspended'),
        ('completed', 'Completed'),
        ('warranty', 'In Warranty'),
        ('closed', 'Closed'),
    ], 'Status', required=True, default='prospect', tracking=True)

    # ── Dates ────────────────────────────────────────────────────────────────
    date_start = fields.Date('Contractual Start Date', tracking=True)
    date_end_contract = fields.Date('Contractual End Date', tracking=True)
    date_end_forecast = fields.Date('Forecast End Date', tracking=True)
    date_awarded = fields.Date('Award Date')

    # ── Financials ────────────────────────────────────────────────────────────
    currency_id = fields.Many2one('res.currency', 'Currency',
                                   default=lambda self: self.env.company.currency_id)
    valor_contrato = fields.Monetary('Contract Value (ex. VAT)', tracking=True)
    retencao_pct = fields.Float('Retention %', default=5.0)
    analytic_account_id = fields.Many2one('account.analytic.account', 'Cost Centre',
                                           tracking=True)

    # ── BOQs ──────────────────────────────────────────────────────────────────
    boq_ids = fields.One2many('construction.boq', 'obra_id', 'Bills of Quantities')
    boq_count = fields.Integer(compute='_compute_boq_count', store=True)
    boq_active_id = fields.Many2one('construction.boq', 'Active BOQ',
                                     compute='_compute_boq_active', store=True)

    # ── Location ──────────────────────────────────────────────────────────────
    street = fields.Char('Address')
    city = fields.Char('City')
    zip = fields.Char('Postcode')
    country_id = fields.Many2one(
        'res.country', 'Country',
        default=lambda self: self.env.ref('base.pt', raise_if_not_found=False),
    )

    # ── Autodesk ACC ──────────────────────────────────────────────────────────
    acc_project_id = fields.Char('Autodesk ACC Project ID')
    acc_project_url = fields.Char('Autodesk ACC URL')

    # ── Computed ──────────────────────────────────────────────────────────────
    @api.depends('boq_ids')
    def _compute_boq_count(self):
        for r in self:
            r.boq_count = len(r.boq_ids)

    @api.depends('boq_ids', 'boq_ids.state', 'boq_ids.is_active_revision')
    def _compute_boq_active(self):
        for r in self:
            active = r.boq_ids.filtered(
                lambda b: b.is_active_revision and b.state == 'shared')
            if not active:
                active = r.boq_ids.filtered(lambda b: b.state == 'draft')
            r.boq_active_id = active[:1]

    def action_open_boq_list(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bills of Quantities — %s') % self.name,
            'res_model': 'construction.boq',
            'view_mode': 'list,form',
            'domain': [('obra_id', '=', self.id)],
            'context': {'default_obra_id': self.id},
        }
