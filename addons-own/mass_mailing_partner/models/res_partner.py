# -*- coding: utf-8 -*-
# © 2015 Pedro M. Baeza <pedro.baeza@serviciosbaeza.com>
# © 2015 Antonio Espinosa <antonioea@antiun.com>
# © 2015 Javier Iniesta <javieria@antiun.com>
# © 2016 Antonio Espinosa - <antonio.espinosa@tecnativa.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openerp import models, fields, api, _
from openerp.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # TODO: Make it a computed field non stored and with search
    mass_mailing_contact_ids = fields.One2many(
        string="Mailing lists",
        oldname="mass_mailing_contacts",
        comodel_name='mail.mass_mailing.contact', store=False,
        compute="_compute_mass_mailing_contact_ids",
        search="_search_mass_mailing_contact_ids"
    )

    mass_mailing_stats = fields.One2many(
        string="Mass mailing stats",
        comodel_name='mail.mail.statistics', inverse_name='partner_id')

    # TODO !!!
    @api.multi
    def _compute_mass_mailing_contact_ids(self):
        for r in self:
            r.mass_mailing_contact_ids = r.frst_personemail_ids.mass_mailing_contact_ids

    # TODO !!!
    def _search_mass_mailing_contact_ids(self, operator, value):
        return [('frst_personemail_ids.mass_mailing_contact_ids', operator, value)]

    @api.constrains('email')
    def _check_email_mass_mailing_contacts(self):
        for r in self:
            if r.mass_mailing_contact_ids and not r.email:
                raise ValidationError(
                    _("This partner '%s' is subscribed to one or more "
                      "mailing lists. Email must be assigned." % r.name))

    @api.multi
    def write(self, vals):
        res = super(ResPartner, self).write(vals)

        # TODO: Set Approval state of mass mailing contacts to "approval_pending_mailchange" on main email change
        #       if the new email is not yet yet in state approved!

        return res
