# Copyright 2017 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def write(self, vals):
        """Allow to write values in mass mailing contact."""
        # Rebinding `self` is the usual Odoo spelling, but the 20.0 skeleton's
        # ruff flags it (PLW0642). Same recordset, same context, named.
        syncing = self.with_context(syncing=True)
        return super(ResPartner, syncing).write(vals)
