# Copyright 2015 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# Copyright 2015 Antonio Espinosa <antonio.espinosa@tecnativa.com>
# Copyright 2015 Javier Iniesta <javieria@antiun.com>
# Copyright 2017 David Vidal <david.vidal@tecnativa.com>
# Copyright 2020 Tecnativa - Manuel Calero
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    # No mass_mailing_contact_ids / mass_mailing_contacts_count here any more.
    #
    # 20.0 core absorbed them: res.partner.mailing_contact_ids is the same
    # One2many over the same inverse (mailing.contact.partner_id), and core
    # ships its own stat button on the partner form at the same anchor with the
    # same group. Keeping ours would put two identical relations and a second
    # button on every partner. Core has no count field -- its button tests
    # `mailing_contact_ids` directly -- so the count goes with it.
    #
    # Nothing migrates: the One2many has no column of its own, so dropping the
    # declaration just hands the relation to core.
    #
    # mailing.trace.partner_id is a different story -- core still has no such
    # field in 20.0, so the stats pair below stays ours.
    mass_mailing_stats_ids = fields.One2many(
        string="Mass mailing stats",
        comodel_name="mailing.trace",
        inverse_name="partner_id",
    )
    mass_mailing_stats_count = fields.Integer(
        string="Mass mailing stats number",
        compute="_compute_mass_mailing_stats_count",
        store=True,
    )

    @api.constrains("email")
    def _check_email_mass_mailing_contacts(self):
        for partner in self:
            if not partner.email and partner.sudo().mailing_contact_ids:
                raise ValidationError(
                    self.env._(
                        "This partner '%(name)s' is linked to one or more mass "
                        "mailing contact. Email must be assigned.",
                        name=partner.name,
                    )
                )

    @api.depends("mass_mailing_stats_ids")
    def _compute_mass_mailing_stats_count(self):
        contact_data = self.env["mailing.trace"]._read_group(
            [("partner_id", "in", self.ids)], ["partner_id"], ["__count"]
        )
        mapped_data = {partner.id: count for partner, count in contact_data if partner}
        for partner in self:
            partner.mass_mailing_stats_count = mapped_data.get(partner.id, 0)

    def write(self, vals):
        res = super().write(vals)
        mm_vals = self._prepare_mass_mailing_values(vals)
        if mm_vals:
            # Using sudo because ACLs shouldn't produce data inconsistency
            self.env["mailing.contact"].sudo().search(
                [("partner_id", "in", self.ids)]
            ).write(mm_vals)
        return res

    @api.model
    def _prepare_mass_mailing_values(self, vals):
        mm_vals = {}
        if "name" in vals:
            mm_vals["name"] = vals["name"]
        if "email" in vals:
            mm_vals["email"] = vals["email"]
        if "company_id" in vals:
            company = self.env["res.company"].browse(vals["company_id"])
            mm_vals["company_name"] = company.name
        if "country_id" in vals:
            mm_vals["country_id"] = vals["country_id"]
        return mm_vals
