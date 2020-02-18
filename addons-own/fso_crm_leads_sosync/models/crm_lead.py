# -*- coding: utf-8 -*-

from openerp import models, fields


class CrmLead(models.Model):
    _inherit = ['crm.lead', 'base.sosync']

    active = fields.Boolean(sosync="True")
    city = fields.Char(sosync="True")
    color = fields.Integer(sosync="True")
    company_id = fields.Many2one(sosync="True")
    contact_anrede_individuell = fields.Char(sosync="True")
    contact_birthdate_web = fields.Date(sosync="True")
    contact_lastname = fields.Char(sosync="True")
    contact_name = fields.Char(sosync="True")
    contact_newsletter_web = fields.Boolean(sosync="True")
    contact_street_number_web = fields.Char(sosync="True")
    contact_title_web = fields.Char(sosync="True")
    country_id = fields.Many2one(sosync="True")
    date_action = fields.Date(sosync="True")
    date_action_last = fields.Datetime(sosync="True")
    date_action_next = fields.Datetime(sosync="True")
    date_assign = fields.Date(sosync="True")
    date_closed = fields.Datetime(sosync="True")
    date_deadline = fields.Date(sosync="True")
    date_last_stage_update = fields.Datetime(sosync="True")
    date_open = fields.Datetime(sosync="True")
    day_close = fields.Float(sosync="True")
    day_open = fields.Float(sosync="True")
    description = fields.Text(sosync="True")
    display_name = fields.Char(sosync="True")
    email_cc = fields.Text(sosync="True")
    email_from = fields.Char(sosync="True")
    fax = fields.Char(sosync="True")
    function = fields.Char(sosync="True")
    meeting_count = fields.Integer(sosync="True")
    message_bounce = fields.Integer(sosync="True")
    message_is_follower = fields.Boolean(sosync="True")
    message_last_post = fields.Datetime(sosync="True")
    message_summary = fields.Text(sosync="True")
    message_unread = fields.Boolean(sosync="True")
    mobile = fields.Char(sosync="True")
    name = fields.Char(sosync="True")
    opt_out = fields.Boolean(sosync="True")
    partner_address_email = fields.Char(sosync="True")
    partner_address_name = fields.Char(sosync="True")
    partner_id = fields.Many2one(sosync="True")
    partner_latitude = fields.Float(sosync="True")
    partner_longitude = fields.Float(sosync="True")
    partner_name = fields.Char(sosync="True")
    payment_mode = fields.Many2one(sosync="True")
    phone = fields.Char(sosync="True")
    planned_cost = fields.Float(sosync="True")
    planned_revenue = fields.Float(sosync="True")
    priority = fields.Selection(sosync="True")
    probability = fields.Float(sosync="True")
    referred = fields.Char(sosync="True")
    state_id = fields.Many2one(sosync="True")
    street = fields.Char(sosync="True")
    street2 = fields.Char(sosync="True")
    title = fields.Many2one(sosync="True")
    title_action = fields.Char(sosync="True")
    type = fields.Selection(sosync="True")
    zip = fields.Char(sosync="True")
