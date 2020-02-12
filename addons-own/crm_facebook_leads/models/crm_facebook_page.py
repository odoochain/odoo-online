# -*- coding: utf-8 -*-

from openerp import api, models, fields
from facebook_graph_api import facebook_graph_api_url
import requests


class CrmFacebookPage(models.Model):
    _name = 'crm.facebook.page'

    name = fields.Char(required=True, string="Facebook Page Name")
    page_id = fields.Char(required=True, string="Facebook Page ID")
    page_access_token = fields.Char(required=True, string='Page Access Token')
    form_ids = fields.One2many('crm.facebook.form', 'page_id', string='Lead Forms')

    @api.multi
    def get_forms(self):
        r = requests.get(facebook_graph_api_url + self.page_id + "/leadgen_forms",
                         params={'access_token': self.page_access_token}).json()

        crm_facebook_form_obj = self.env['crm.facebook.form'].sudo()

        for fb_form in r['data']:
            # Search inactive forms too, so archived forms are not created over and over again
            crm_form_rec = crm_facebook_form_obj.search([('facebook_form_id', '=', fb_form['id']),
                                                     '|', ('active', '=', True), ('active', '=', False)])
            if not crm_form_rec:
                self.env['crm.facebook.form'].create({
                    'name': fb_form['name'],
                    'facebook_form_id': fb_form['id'],
                    'page_id': self.id,
                    'state': 'to_review'
                }).get_fields()
            else:
                if fb_form['status'].lower() != 'active':
                    crm_form_rec.write({'active': False})
