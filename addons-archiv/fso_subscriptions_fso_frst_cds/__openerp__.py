# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#    Copyright (C) 2010-2012 OpenERP s.a. (<http://openerp.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': "FS-Online fso_subscription_fso_frst_cds",
    'summary': """FS-Online Subscription tied into Fundraising Studio Campaigns""",
    'description': """

    Extends mail.mass_mailing.list with
    - frst_zverzeichnis_id   

    """,
    'author': "Datadialog - Martin Kaip",
    'website': "http://www.datadialog.net/",
    'category': 'Uncategorized',
    'version': '0.1',
    'installable': True,
    'application': True,
    'auto_install': False,
    'depends': [
        'fso_subscriptions',
        #'fso_frst_cds',    # No need to add here because fso_subscriptions -> fso_forms -> fso_base_website -> fso_base -> fso_frst_groups_frst_cds -> fso_frst_cds
    ],
    'data': [
        'views/mail_mass_mailing_list.xml'
    ],
}
