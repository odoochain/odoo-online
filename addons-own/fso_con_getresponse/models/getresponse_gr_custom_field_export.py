# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
import logging
import json

from openerp.addons.connector.unit.mapper import ExportMapper, mapping, only_create
from openerp.addons.connector.queue.job import job
from openerp.addons.connector.exception import IDMissingInBackend, RetryableJobError

from .helper_connector import get_environment
from .backend import getresponse
from .unit_export import BatchExporter, GetResponseExporter
from .unit_export_delete import GetResponseDeleteExporter

_logger = logging.getLogger(__name__)


# -----------------------
# CONNECTOR EXPORT MAPPER
# -----------------------
@getresponse
class CustomFieldExportMapper(ExportMapper):
    """ Map all the fields of the odoo record to the GetResponse API field names.

    ATTENTION: !!! FOR THE EXPORT WE MUST USE THE FIELD NAMES OF THE GET RESPONSE API !!!

               When we import data the client lib will return a campaign object. The data of campaign is stored
               in the objects attributes. The pitfall is that the object attributes will follow python conventions so
               the GetResponse 'languageCode' is the attribute campaign.language_code if we read objects from GR.

               BUT for the export to GetResponse (update or write) we need the prepare the "raw data" for the
               request!
    """
    _model_name = 'getresponse.gr.custom_field'

    def _map_children(self, record, attr, model):
        pass

    # ATTENTION: !!! FOR THE EXPORT WE MUST USE THE RAW FIELD NAMES OF THE GET RESPONSE API !!!

    # Create a modifier for the direct mapping fields
    def json_to_python(field):
        """ ``field`` is the name of the source field.

        Naming the arg: ``field`` is required for the conversion!
        """
        def modifier(self, record, to_attr):
            """ self is the current Mapper, record is the current odoo record to map, to_attr is the target field"""
            data_string = record[field]
            if data_string:
                assert isinstance(data_string, basestring), "Field %s (%s) must be a string" % (field, record._name)
                data = json.loads(data_string, encoding='utf-8')
                return data
            else:
                return []
        return modifier

    # Direct mappings
    # ('odoo source', 'getresponse api target')
    direct = [('gr_hidden', 'hidden'),
              (json_to_python('gr_values'), 'values'),
              ]

    @only_create
    @mapping
    def name(self, record):
        return {'name': record.name}

    @only_create
    @mapping
    def gr_type(self, record):
        return {'type': record.gr_type}

    @only_create
    @mapping
    def gr_format(self, record):
        if record.gr_format:
            return {'format': record.gr_format}


# ---------------------------------------------------------------------------------------------------------------------
# EXPORT SYNCHRONIZER(S)
# ---------------------------------------------------------------------------------------------------------------------

# --------------
# BATCH EXPORTER
# --------------
@getresponse
class CustomFieldBatchExporter(BatchExporter):
    _model_name = ['getresponse.gr.custom_field']


@job(default_channel='root.getresponse')
def custom_field_export_batch(session, model_name, backend_id, domain=None, fields=None, delay=False, **kwargs):
    """ Prepare the batch export of custom field definitions to GetResponse """
    connector_env = get_environment(session, model_name, backend_id)

    # Get the exporter connector unit
    batch_exporter = connector_env.get_connector_unit(CustomFieldBatchExporter)

    # Start the batch export
    batch_exporter.batch_run(domain=domain, fields=fields, delay=delay, **kwargs)


# ----------------------
# SINGLE RECORD EXPORTER
# ----------------------
# In this class we could alter the generic GetResponse export sync flow for 'getresponse.frst.zgruppedetail'
# HINT: We could overwrite all the methods from the shared GetResponseExporter here if needed!
@getresponse
class CustomFieldExporter(GetResponseExporter):
    _model_name = ['getresponse.gr.custom_field']

    _base_mapper = CustomFieldExportMapper

    def run(self, binding_id, *args, **kwargs):

        # RECORD REMOVED IN GETRESPONSE HANDLING
        try:
            return super(CustomFieldExporter, self).run(binding_id, *args, **kwargs)
        except IDMissingInBackend as e:
            # Try to unlink the tag definition in odoo
            if self.binding_record and self.binding_record.getresponse_id:
                custom_field = self.binder.unwrap_binding(self.binding_record, browse=True)
                if len(custom_field) == 1:
                    msg = ('CUSTOM FIELD DEFINITION %s NOT FOUND IN GETRESPONSE! UNLINKING CUSTOM FIELD %s IN ODOO!'
                           '' % (self.binding_record.getresponse_id, custom_field.id))
                    _logger.warning(msg)
                    custom_field.with_context(connector_no_export=True).unlink()
                    return msg

            # Raise the exception if we could not unlink the tag definition in odoo
            raise e

        # Raise all other exceptions
        except Exception as e:
            raise e


# -----------------------------
# SINGLE RECORD DELETE EXPORTER
# -----------------------------
@getresponse
class CustomFieldDeleteExporter(GetResponseDeleteExporter):
    _model_name = ['getresponse.gr.custom_field']

