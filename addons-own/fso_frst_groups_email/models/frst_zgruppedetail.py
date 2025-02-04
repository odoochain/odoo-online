# -*- coding: utf-8 -*-
from openerp import models, fields, api
from openerp.tools.translate import _
from openerp.tools import SUPERUSER_ID

import logging
logger = logging.getLogger(__name__)


# Fundraising Studio groups
class FRSTzGruppeDetailApprovalMail(models.Model):
    _inherit = "frst.zgruppedetail"

    subscription_email = fields.Many2one(string="Subscription E-Mail",
                                         comodel_name='email.template',
                                         inverse_name="frst_groups_subscription_email",
                                         index=True,
                                         domain="[('fso_email_template', '=', True)]",
                                         help="E-Mail will be send for every newly created subscription in the state "
                                              "'subscribed.', 'approval_pending' or 'approved'. Leave this empty "
                                              "if you do not want an E-Mail for every new subscription or if you want "
                                              "the approval E-Mail only!")

    bestaetigung_email = fields.Many2one(string="DOI Approval E-Mail Template",
                                         comodel_name='email.template',
                                         inverse_name="frst_groups_bestaetigung_emails",
                                         domain="[('fso_email_template', '=', True)]",
                                         help="Double Opt In E-Mail")

    bestaetigung_success_email = fields.Many2one(string="DOI Success E-Mail Template",
                                                 comodel_name='email.template',
                                                 inverse_name="frst_groups_bestaetigung_success_email",
                                                 index=True,
                                                 domain="[('fso_email_template', '=', True)]",
                                                 help="E-Mail will be send after successful Double-Opt-In approval of "
                                                      "the subscription")

    bestaetigung_text = fields.Char(string="Approval-Link Print Field Text", help="""
This text will be used for the print field %GruppenBestaetigungsText%. Leave empty if you dont need any text 
there!
\n\n
EXAMPLE:\n
<a href="/frst/group/approve?group_approve_fson_zgruppedetail_id=%GruppenBestaetigungFsonzGruppeDetailID%">
   Please click here to confirm your %GruppenBestaetigungsText% subscription!
</a>\n
\n
IMPORTANT: The confirmation of the subscription (PersonEmailGruppe) will be done by a generic Fundraising 
Studio Workflow based on the multimail link tracking. The workflow will track the link if the URL parameter
'group_approve_fson_zgruppedetail_id=...' is in it.\n 
Therefore it is NOT necessary to use '/frst/group/approve' as the target of the Link. You could use ANY URL you like! 
Just make sure 'group_approve_fson_zgruppedetail_id=%GruppenBestaetigungFsonzGruppeDetailID%' is added!
        """)
    bestaetigung_thanks = fields.Html(string="Approval Thank You Page HTML",
                                      help="""
If set this will be the html on the thank you page after a click on the 
'approval link' if the approval link points to the FS-Online Thank You 
Page. Leave empty if you do not use the FS-Online Subscription Thank You Page!
        """)

    @api.constrains('bestaetigung_erforderlich', 'bestaetigung_typ', 'bestaetigung_email')
    def constraint_bestaetigung_erforderlich(self):
        for r in self:
            if r.bestaetigung_erforderlich and r.bestaetigung_typ == 'doubleoptin':
                assert r.bestaetigung_email, _("'bestaetigung_erforderlich' is set and 'bestaetigung_typ' is "
                                               "'doubleoptin' but 'bestaetigung_email' is empty!")
            if r.bestaetigung_email:
                assert r.bestaetigung_email.fso_email_template, _("Approval Email Template must be a "
                                                                  "fso_email_template!")
                assert r.bestaetigung_email.fso_email_html_parsed and \
                       'GruppenBestaetigungFsonzGruppeDetailID' in r.bestaetigung_email.fso_email_html_parsed and \
                       'group_approve_fson_zgruppedetail_id' in r.bestaetigung_email.fso_email_html_parsed, _('''
URL parameter 'group_approve_fson_zgruppedetail_id=...' or print field %GruppenBestaetigungFsonzGruppeDetailID% 
missing in the selected DOI E-Mail template!\n
Without this URL parameter and print field appended to the DOI Link (href) the generic DOI workflow in 
Fundraising Studio will not work! Please add the URL parameter and print field in your e-mail template! \n
\n
EXAMPLE LINK:\n
<a href="/frst/group/approve?group_approve_fson_zgruppedetail_id=%GruppenBestaetigungFsonzGruppeDetailID%">
    Please click here to confirm your %GruppenBestaetigungsText% subscription!
</a>\n
\n
IMPORTANT: The confirmation of the subscription (PersonEmailGruppe) will be done by a generic Fundraising 
Studio Workflow based on the multimail link tracking. The workflow will track the link if the URL parameter
'group_approve_fson_zgruppedetail_id=...' is in it. Therefore it is NOT necessary to use '/frst/group/approve'
as the target of the Link. You could use ANY URL you like! Just make sure 
'group_approve_fson_zgruppedetail_id=%GruppenBestaetigungFsonzGruppeDetailID%' is added as an URL parameter!       
                    ''')

