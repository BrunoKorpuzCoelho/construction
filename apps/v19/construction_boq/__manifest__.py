# -*- coding: utf-8 -*-
{
    'name': 'Construction BOQ Manager',
    'version': '19.0.1.0.0',
    'summary': 'Bill of Quantities management for Construction Projects',
    'description': """
        Full BOQ lifecycle management for Odoo 19:
        - Hierarchical Bill of Quantities with chapters, sub-chapters, articles
        - Revision system with share/lock (draft → shared → archived)
        - OWL split-panel Excel-like editor with inline editing
        - Odoo 19 AI assistant integrated directly in BOQ editor
        - Odoo Product, UoM and Stock integration
        - Excel Import / Export (internal + client-facing format)
        - PDF report generation
    """,
    'author': 'Construction BOQ',
    'category': 'Construction',
    'application': True,
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'product',
        'uom',
        'purchase',
        'sale_management',
        'account',
        'analytic',
        'stock',
        'contacts',
        'web',
    ],
    'data': [
        # Security — must be first
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        # Data
        'data/sequence_data.xml',
        # Views — overview action must be before menus
        'views/construction_obra_views.xml',
        'views/construction_boq_views.xml',
        'views/construction_boq_artigo_views.xml',
        'views/construction_overview.xml',
        # Menus — after all actions
        'views/menus.xml',
        # Wizards
        'wizard/boq_wizard_views.xml',
        # Reports
        'report/boq_report_templates.xml',
        'report/boq_report_actions.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'construction_boq/static/src/scss/boq_editor.scss',
            'construction_boq/static/src/components/boq_editor/boq_editor.js',
            'construction_boq/static/src/components/boq_editor/boq_editor.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
}
