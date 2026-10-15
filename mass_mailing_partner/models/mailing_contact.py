# Copyright 2015 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# Copyright 2015 Antonio Espinosa <antonio.espinosa@tecnativa.com>
# Copyright 2015 Javier Iniesta <javieria@antiun.com>
# Copyright 2017 David Vidal <david.vidal@tecnativa.com>
# Copyright 2020 Tecnativa - Manuel Calero
# Copyright 2020 Hibou Corp.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class MailingContact(models.Model):
    _inherit = "mailing.contact"

    # partner_id is core's in 20.0 (mass_mailing/models/mailing_contact.py), on
    # the same model with the same comodel and therefore the same column, so
    # re-declaring it here would only fight core over the string and the
    # domain. Everything below keeps working against core's field.
    #
    # One deliberate loss: ours carried domain=[("email", "!=", False)] and
    # core's carries none, so the form no longer filters partners without an
    # address out of the dropdown. The _check_email_mass_mailing_contacts
    # constraint on res.partner still refuses to clear the address of a linked
    # partner, so the invariant that mattered is still enforced -- it is now
    # enforced on save rather than hidden from the picker.
    tag_ids = fields.Many2many(compute="_compute_tag_ids", store=True)

    @api.depends("partner_id", "partner_id.category_id")
    def _compute_tag_ids(self):
        for rec in self:
            tags = rec.tag_ids
            if rec.partner_id.category_id:
                tags = rec.partner_id.category_id
            rec.tag_ids = tags

    @api.onchange("partner_id")
    def _onchange_partner_mass_mailing_partner(self):
        if self.partner_id:
            self.name = self.partner_id.name
            self.email = self.partner_id.email
            # commercial_company_name, not company_name: 20.0 removed the
            # free-text res.partner.company_name and core's replacement is
            # related to commercial_partner_id.name ("will act in place of
            # company_name", per the comment on it). mailing.contact keeps its
            # own company_name, so only the partner side moves.
            self.company_name = (
                self.partner_id.company_id.name
                or self.partner_id.commercial_company_name
            )
            self.country_id = self.partner_id.country_id

    def _overwrite_partner(self, vals, creating=False):
        self.ensure_one()
        if self.env.context.get("mass_mailing_partner_writing"):
            return
        _self = self.with_context(mass_mailing_partner_writing=True)
        prev_partner = _self.partner_id
        if "partner_id" not in vals:
            _self._set_partner()
        if creating or prev_partner != _self.partner_id:
            _self._onchange_partner_mass_mailing_partner()

    @api.model_create_multi
    def create(self, vals_list):
        result = super().create(vals_list)
        for contact, vals in zip(result, vals_list, strict=False):
            contact._overwrite_partner(vals, True)
        return result

    def write(self, vals):
        # If partner_id is changing, sync dependent fields from partner
        # to ensure consistency
        if vals.get("partner_id"):
            partner = self.env["res.partner"].browse(vals["partner_id"])
            vals["name"] = partner.name
            vals["email"] = partner.email
            vals["company_name"] = (
                partner.company_id.name or partner.commercial_company_name
            )
            vals["country_id"] = partner.country_id.id
        result = super().write(vals)
        for contact in self:
            contact._overwrite_partner(vals)
        return result

    def _get_categories(self):
        ca_ids = (
            self.tag_ids.ids
            + self.list_ids.mapped("partner_category.id")
            + self.subscription_ids.mapped("list_id.partner_category.id")
        )
        return [[6, 0, ca_ids]]

    def _prepare_partner(self):
        return {
            "name": self.name or self.email,
            "email": self.email,
            "country_id": self.country_id.id,
            # No "company_name". 20.0 removed it from res.partner, and the
            # replacement (commercial_company_name) is related to
            # commercial_partner_id.name, so it cannot be written as free text
            # -- there is nowhere on a 20.0 partner to put a company name that
            # is not an actual partner record. The contact keeps its own
            # company_name either way; only the partner created from it loses
            # the echo.
            "company_id": False,
            "category_id": self._get_categories(),
        }

    def _set_partner(self):
        self.ensure_one()
        if not self.email or self.partner_id:
            return
        m_partner = self.env["res.partner"]
        # Look for a partner with that email
        email = self.email.strip()
        partner = m_partner.search([("email", "=ilike", email)], limit=1)
        if partner:
            if partner == self.partner_id:
                return
            # Partner found
            self.partner_id = partner
        else:
            lts = self.subscription_ids.mapped("list_id") | self.list_ids
            if lts.filtered("partner_mandatory"):
                # Create partner
                partner_vals = self._prepare_partner()
                self.partner_id = m_partner.sudo().create(partner_vals)
