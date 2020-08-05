# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from openerp import models, fields, api
from openerp.exceptions import ValidationError
from openerp.tools.translate import _

from openerp.addons.connector.unit.mapper import ImportMapper, ExportMapper, mapping, only_create
from openerp.addons.connector.queue.job import job

from .connector import get_environment
from .backend import getresponse

from .unit_adapter import GetResponseCRUDAdapter
from .unit_synchronizer_import import GetResponseImporter, DelayedBatchImporter, DirectBatchImporter


# ------------------------------------------
# CONNECTOR BINDING MODEL AND ORIGINAL MODEL
# ------------------------------------------
# WARNING: When using delegation inheritance, methods are not inherited, only fields!
class GetResponseCampaign(models.Model):
    _name = 'getresponse.frst.zgruppedetail'
    _inherits = {'frst.zgruppedetail': 'odoo_id'}
    _description = 'GetResponse Campaign (List)'

    backend_id = fields.Many2one(
        comodel_name='getresponse.backend',
        string='GetResponse Connector Backend',
        required=True,
        readonly=True,
        ondelete='restrict'
    )
    odoo_id = fields.Many2one(
        comodel_name='frst.zgruppedetail',
        string='Fundraising Studio Group',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    getresponse_id = fields.Char(
        string='GetResponse Campaing ID',
        readonly=True
    )
    sync_date = fields.Datetime(
        string='Last synchronization date',
        readonly=True)

    # ATTENTION: This will be filled/set by the binder bind() method!
    sync_data = fields.Char(
        string='Last synchronization data',
        readonly=True)

    _sql_constraints = [
        ('getresponse_uniq', 'unique(backend_id, getresponse_id)',
         'A binding already exists with the same GetResponse ID for this GetResponse backend (Account).'),
    ]


class GetResponseFrstZgruppedetail(models.Model):
    _inherit = 'frst.zgruppedetail'

    getresponse_bind_ids = fields.One2many(
        comodel_name='getresponse.frst.zgruppedetail',
        inverse_name='odoo_id',
    )

    sync_with_getresponse = fields.Boolean(string="Sync with GetResponse",
                                           help="If set the contacts/subscribers of this group/campaign will be"
                                                "synced with GetResponse")

    gr_language_code = fields.Char(string="GetResponse Language Code", readonly=True)
    gr_optin_email = fields.Selection(string="GetResponse OptIn Email", readonly=True,
                                      selection=[('single', 'single'), ('double', 'double')])
    gr_optin_api = fields.Selection(string="GetResponse OptIn API", readonly=True,
                                    selection=[('single', 'single'), ('double', 'double')])
    gr_optin_import = fields.Selection(string="GetResponse OptIn Import", readonly=True,
                                       selection=[('single', 'single')])
    gr_optin_webform = fields.Selection(string="GetResponse OptIn Webform", readonly=True,
                                        selection=[('single', 'single'), ('double', 'double')])

    @api.constrains('sync_with_getresponse', 'zgruppe_id')
    def constrain_sync_with_getresponse(self):
        for r in self:
            if r.sync_with_getresponse:
                # Only E-Mail groups can be enabled to sync with GetResponse
                if not r.zgruppe_id.tabellentyp_id == '100110':
                    raise ValidationError(_("Only groups of type e-mail can be synced with GetResponse!"))
                # TODO: Do not allow to unset 'sync_with_getresponse' as long as PersonEmailGruppe bindings to
                #       GetResponse contacts exists (= as long as synced subscriber exist)

# ----------------
# CONNECTOR BINDER
# ----------------
# Nothing to do here since no modifications to the generic binder implementation are needed
# Just make sure to add all binding models to the '_model_name' list of the GetResponseModelBinder class
# HINT: Check unit_binder.py > GetResponseModelBinder()


# -----------------
# CONNECTOR ADAPTER
# -----------------
# The Adapter is a subclass of an ConnectorUnit class. The ConnectorUnit Object holds information about the
# connector_env, the backend, the backend_record and about the connector session
@getresponse
class ZgruppedetailAdapter(GetResponseCRUDAdapter):
    _model_name = 'getresponse.frst.zgruppedetail'
    _getresponse_model = 'campaign'

    def search(self, filters=None):
        """ Returns a list of GetResponse campaign ids """
        assert not filters or isinstance(filters, dict), "filters must be a dict!"
        campaigns = self.getresponse.get_campaigns(filters)
        return [campaign.id for campaign in campaigns]

    def read(self, id, attributes=None):
        """ Returns the information of a record  """
        campaign = self.getresponse.get_campaign(id, params=attributes)
        # WARNING: A dict() is expected! Right now 'campaign' is a campaign object!
        return campaign.__dict__

    def search_read(self, filters=None):
        """ Search records based on 'filters' and return their information"""
        campaigns = self.getresponse.get_campaigns(filters)
        # WARNING: A dict() is expected! Right now 'campaign' is a campaign object!
        return campaigns.__dict__

    def create(self, data):
        campaign = getresponse.create_campaign(data)
        # WARNING: A dict() is expected! Right now 'campaign' is a campaign object!
        return campaign.__dict__

    def write(self, id, data):
        campaign = self.getresponse.update_campaign(id, body=data)
        # WARNING: A dict() is expected! Right now 'campaign' is a campaign object!
        return campaign.__dict__

    def delete(self, id):
        raise NotImplementedError


# -----------------------
# CONNECTOR IMPORT MAPPER
# -----------------------
# Transform the data from GetResponse campaign objects to odoo records and vice versa
@getresponse
class ZgruppedetailImportMapper(ImportMapper):
    """ Map all the fields of the the GetResponse API library campaign object to the odoo record fields.
    You can find all all available fields here: ..../getresponse-python/getresponse/campaign.py

    ATTENTION: The field names of the  GetResponse API library (getresponse-python) may not match the field names
               found in the getresponse API documentation e.g. Campaign.language_code is 'languageCode' in the api.
               The final transformation to the correct API names is done by the getresponse-python lib. Check
               _create() from getresponse-python > campaign.py to see the final transformations
    """
    _model_name = 'getresponse.frst.zgruppedetail'

    # TODO: Check if this method may be the correct one for PersonEmail and Partner for PersonEmailGruppe"
    def _map_children(self, record, attr, model):
        pass

    # (getresponse_field_name, odoo_field_name)
    direct = [
        ('name', 'gruppe_lang'),
        ('name', 'gruppe_kurz'),
        ('language_code', 'gr_language_code')
    ]

    @mapping
    def backend_id(self, record):
        return {'backend_id': self.backend_record.id}

    @mapping
    def getresponse_id(self, record):
        return {'getresponse_id': record['id']}

    @only_create
    @mapping
    def geltungsbereich(self, record):
        return {'geltungsbereich': 'local'}

    @only_create
    @mapping
    def zgruppe_id(self, record):
        # get 'default_zgruppe_id' from the getresponse backend
        return {'zgruppe_id': self.backend_record.default_zgruppe_id.id}

    # OptIn
    @mapping
    def gr_optin_email(self, record):
        return {'gr_optin_email': record['opting_types']['email']}

    @mapping
    def gr_optin_api(self, record):
        return {'gr_optin_api': record['opting_types']['api']}

    @mapping
    def gr_optin_import(self, record):
        return {'gr_optin_import': record['opting_types']['import']}

    @mapping
    def gr_optin_webform(self, record):
        return {'gr_optin_webform': record['opting_types']['webform']}


# ---------------------------------
# CONNECTOR IMPORTER (SYNCHRONIZER)
# ---------------------------------

# SEARCH FOR THE GETRESPONSE RECORDS AND START THE IMPORT FOR EACH RECORD DELAYED OR DIRECT
# -----------------------------------------------------------------------------------------
# HINT: These classes and methods are responsible for the search of GetResponse records
#       You could also decide if you want the records to do the batch imported directly or delayed
#       In the end those classes will start ZgruppedetailImporter() > run() for each of the found records
@getresponse
class ZgruppedetailDirectBatchImporter(DirectBatchImporter):
    _model_name = ['getresponse.frst.zgruppedetail']


@getresponse
class ZgruppedetailDelayedBatchImporter(DelayedBatchImporter):
    _model_name = ['getresponse.frst.zgruppedetail']


@job(default_channel='root.getresponse')
def zgruppedetail_import_batch_delay(session, model_name, backend_id, filters=None):
    """ Prepare the batch import of all GetResponse campaigns """
    if filters is None:
        filters = {}
    env = get_environment(session, model_name, backend_id)
    # ZgruppedetailDelayedBatchImporter > DelayedBatchImporter._import_record > import_record.delay() which will start:
    #     env.get_connector_unit(GetResponseImporter).run()
    importer = env.get_connector_unit(ZgruppedetailDelayedBatchImporter)
    importer.run(filters=filters)


@job(default_channel='root.getresponse')
def zgruppedetail_import_batch_direct(session, model_name, backend_id, filters=None):
    """ Prepare the batch import of all GetResponse campaigns """
    if filters is None:
        filters = {}
    env = get_environment(session, model_name, backend_id)
    # ZgruppedetailDirectBatchImporter > DirectBatchImporter._import_record > import_record() which will start:
    #     env.get_connector_unit(GetResponseImporter).run()
    importer = env.get_connector_unit(ZgruppedetailDirectBatchImporter)
    importer.run(filters=filters)
# -----------------------------------------------------------------------------------------


# IMPORT EACH FOUND RECORD (SYNC FLOW)
# ------------------------------------
# In this class we could alter the generic GetResponse import sync flow for 'getresponse.frst.zgruppedetail'
# HINT: We could overwrite all the methods from GetResponseImporter here if needed!
@getresponse
class ZgruppedetailImporter(GetResponseImporter):
    _model_name = ['getresponse.frst.zgruppedetail']

    _base_mapper = ZgruppedetailImportMapper

    def __init__(self, connector_env):
        """
        :param connector_env: current environment (backend, session, ...)
        :type connector_env: :class:`connector.connector.ConnectorEnvironment`
        """
        super(ZgruppedetailImporter, self).__init__(connector_env)
# ------------------------------------


# -----------------------
# TODO: CONNECTOR EXPORT MAPPER
# -----------------------
@getresponse
class ZgruppedetailExportMapper(ExportMapper):
    """ Map all the fields of the odoo record to the GetResponse API library campaign object.
    You can find all all available fields here: ..../getresponse-python/getresponse/campaign.py

    ATTENTION: The field names of the  GetResponse API library (getresponse-python) may not match the field names
               found in the getresponse API documentation e.g. Campaign.language_code is 'languageCode' in the api.
               The final transformation to the correct API names is done by the getresponse-python lib. Check
               _create() from getresponse-python > campaign.py to see the final transformations

    ATTENTION: We do NOT map fields that should be set in getresponse only! So OptIn Types or gr_language_code can be
               changed in getresponse only. The only exception from this rule is if we create campaigns from odoo
               zGruppeDetail records where we need to set the defaults on creation time.
    """

    def _map_children(self, record, attr, model):
        pass

    _model_name = 'getresponse.frst.zgruppedetail'

    @mapping
    def name(self, record):
        return {'name': record.gruppe_lang or record.gruppe_kurz}

    @only_create
    @mapping
    def language_code(self, record):
        return {'language_code': 'DE'}

    # OptIn
    # ATTENTION: We can only export or import contacts (subscribers / PersonEmailGruppe) that are approved. Or in
    #            other words only subscribers where the optin is already done! This is more or less a getresponse
    #            constrain since non approved subscribers are treated like 'deleted' from getresponse and will not be
    #            returned by regular searches!
    #            Therefore do not sync any PersonEmailGruppe in an state other than 'approved' or 'subscribed'
    #            Because of this  all subscribers created by the api through FSON are subscribed already and we set
    #            'api' to 'single'.
    @only_create
    @mapping
    def opting_types(self, record):
        return {'opting_types': {
            'api': 'single',
            }
        }

# ---------------------------------
# TODO: CONNECTOR EXPORTER (SYNCHRONIZER)
# ---------------------------------

