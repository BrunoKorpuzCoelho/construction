# -*- coding: utf-8 -*-
import io
import logging
from odoo import http
from odoo.http import request, content_disposition

_logger = logging.getLogger(__name__)


class BOQDownloadController(http.Controller):

    @http.route('/construction_boq/export/<int:boq_id>', type='http', auth='user')
    def export_internal(self, boq_id, **kw):
        return self._do_export(boq_id, 'internal')

    @http.route('/construction_boq/export_client/<int:boq_id>', type='http', auth='user')
    def export_client(self, boq_id, **kw):
        return self._do_export(boq_id, 'client')

    def _do_export(self, boq_id, export_type):
        boq = request.env['construction.boq'].browse(int(boq_id))
        if not boq.exists():
            return request.not_found()
        wizard = request.env['construction.boq.export.wizard'].create({
            'boq_id': boq_id,
            'export_type': export_type,
            'include_obs': True,
        })
        try:
            wb = wizard._build_workbook()
        except Exception as e:
            _logger.error("Excel export error: %s", e, exc_info=True)
            return request.make_response(
                f"Export error: {e}",
                headers=[('Content-Type', 'text/plain')],
            )
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        fname = f'{boq.obra_id.ref_interna or "BOQ"}_{boq.revision_label}_{export_type}.xlsx'
        return request.make_response(
            buf.read(),
            headers=[
                ('Content-Type',
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(fname)),
            ],
        )
