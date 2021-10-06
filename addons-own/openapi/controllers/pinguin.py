# -*- coding: utf-8 -*-
# Copyright 2018, XOE Solutions
# Copyright 2018-2019 Rafis Bikbov <https://it-projects.info/team/bikbov>
# Copyright 2019 Yan Chirino <https://xoe.solutions/>
# Copyright 2019 Anvar Kildebekov <https://it-projects.info/team/fedoranvar>
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).
# pylint: disable=redefined-builtin

"""Pinguin module for Odoo REST Api.

This module implements plumbing code to the REST interface interface concerning
authentication, validation, ORM access and error codes.

It also implements a ORP API worker in the future (maybe).

Todo:
    * Implement API worker
    * You have to also use ``sphinx.ext.todo`` extension

.. _Google Python Style Guide:
   https://google.github.io/styleguide/pyguide.html
"""
import base64
import collections
import functools
import traceback

import openerp
import six
import werkzeug.wrappers
from openerp.addons.report.controllers.main import ReportController
from openerp.http import request
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

from .apijsonrequest import api_route

try:
    import simplejson as json
except ImportError:
    import json


####################################
# Definition of global error codes #
####################################

# 2xx Success
CODE__success = 200
CODE__created = 201
CODE__accepted = 202
CODE__ok_no_content = 204
# 4xx Client Errors
CODE__server_rejects = (400, "Server rejected", "Welcome to macondo!")
CODE__no_user_auth = (401, "Authentication", "Your token could not be authenticated.")
CODE__user_no_perm = (401, "Permissions", "%s")
CODE__method_blocked = (
    403,
    "Blocked Method",
    "This method is not whitelisted on this model.",
)
CODE__db_not_found = (404, "Db not found", "Welcome to macondo!")
CODE__canned_ctx_not_found = (
    404,
    "Canned context not found",
    "The requested canned context is not configured on this model",
)
CODE__obj_not_found = (
    404,
    "Object not found",
    "This object is not available on this instance.",
)
CODE__res_not_found = (404, "Resource not found", "There is no resource with this id.")
CODE__act_not_executed = (
    409,
    "Action not executed",
    "The requested action was not executed.",
)
# 5xx Server errors
CODE__invalid_method = (501, "Invalid Method", "This method is not implemented.")
CODE__invalid_spec = (
    501,
    "Invalid Field Spec",
    "The field spec supplied is not valid.",
)
# If API Workers are enforced, but non is available (switched off)
CODE__no_api_worker = (
    503,
    "API worker sleeping",
    "The API worker is currently not at work.",
)


def successful_response(status, data=None):
    """Successful responses wrapper.

    :param int status: The success code.
    :param data: (optional). The data that can be converted to a JSON.

    :returns: The werkzeug `response object`_.
    :rtype: werkzeug.wrappers.Response

    .. _response object:
        http://werkzeug.pocoo.org/docs/0.14/wrappers/#module-werkzeug.wrappers

    """
    try:
        response = json.dumps(data.ids)
    except AttributeError:
        response = json.dumps(data) if data else None

    return werkzeug.wrappers.Response(
        status=status,
        content_type="application/json; charset=utf-8",
        response=response,
    )


def error_response(status, error, error_descrip):
    """Error responses wrapper.

    :param int status: The error code.
    :param str error: The error summary.
    :param str error_descrip: The error description.

    :returns: The werkzeug `response object`_.
    :rtype: werkzeug.wrappers.Response

    .. _response object:
        http://werkzeug.pocoo.org/docs/0.14/wrappers/#module-werkzeug.wrappers

    """
    return werkzeug.wrappers.Response(
        status=status,
        content_type="application/json; charset=utf-8",
        response=json.dumps({"error": error, "error_descrip": error_descrip}),
    )


##########################
# Pinguin Authentication #
##########################


# User token auth (db-scoped)
def authenticate_token_for_user(token):
    """Authenticate against the database and setup user session corresponding to the token.

    :param str token: The raw access token.

    :returns: User if token is authorized for the requested user.
    :rtype openerp.models.Model

    :raise: werkzeug.exceptions.HTTPException if user not found.
    """
    user = request.env["res.users"].sudo().search([("openapi_token", "=", token)])
    if user.exists():
        # copy-pasted from openerp.http.py:OpenERPSession.authenticate()

        db = request.session._db
        uid = user.id
        password = token
        # request.session.authenticate(db, user.login, password)

        # security.check(db, uid, password)
        request.session.uid = uid
        request.session.login = user.login
        request.session.password = password
        request.uid = uid
        request.disable_db = False
        request.session.get_context()
        # recompute lazy property
        delattr(request,  'env')

        return user
    raise werkzeug.exceptions.HTTPException(
        response=error_response(*CODE__no_user_auth)
    )


def get_auth_header(headers, raise_exception=False):
    """check and get basic authentication header from headers

    :param werkzeug.datastructures.Headers headers: All headers in request.
    :param bool raise_exception: raise exception.

    :returns: Found raw authentication header.
    :rtype: str or None

    :raise: werkzeug.exceptions.HTTPException if raise_exception is **True**
                                              and auth header is not in headers
                                              or it is not Basic type.
    """
    auth_header = headers.get("Authorization") or headers.get("authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        if raise_exception:
            raise werkzeug.exceptions.HTTPException(
                response=error_response(*CODE__no_user_auth)
            )
    return auth_header


def get_data_from_auth_header(header):
    """decode basic auth header and get data

    :param str header: The raw auth header.

    :returns: a tuple of database name and user token
    :rtype: tuple
    :raise: werkzeug.exceptions.HTTPException if basic header is invalid base64
                                              string or if the basic header is
                                              in the wrong format
    """
    normalized_token = header.replace("Basic ", "").replace("\\n", "").encode("utf-8")
    try:
        decoded_token_parts = base64.decodestring(normalized_token).split(":")
    except TypeError:
        raise werkzeug.exceptions.HTTPException(
            response=error_response(
                500, "Invalid header", "Basic auth header must be valid base64 string"
            )
        )

    if len(decoded_token_parts) == 1:
        db_name, user_token = None, decoded_token_parts[0]
    elif len(decoded_token_parts) == 2:
        db_name, user_token = decoded_token_parts
    else:
        err_descrip = (
            'Basic auth header payload must be of the form "<%s>" (encoded to base64)'
            % "user_token"
            if openerp.tools.config["dbfilter"]
            else "db_name:user_token"
        )
        raise werkzeug.exceptions.HTTPException(
            response=error_response(500, "Invalid header", err_descrip)
        )

    return db_name, user_token


def setup_db(httprequest, db_name):
    """check and setup db in session by db name

    :param httprequest: a wrapped werkzeug Request object
    :type httprequest: :class:`werkzeug.wrappers.BaseRequest`
    :param str db_name: Database name.

    :raise: werkzeug.exceptions.HTTPException if the database not found.
    """
    # import wdb
    # wdb.set_trace()
    if httprequest.session.db:
        return
    if db_name not in openerp.service.db.exp_list():
        raise werkzeug.exceptions.HTTPException(
            response=error_response(*CODE__db_not_found)
        )

    httprequest.session.db = db_name


###################
# Pinguin Routing #
###################


# Try to get namespace from user allowed namespaces
def get_namespace_by_name_from_users_namespaces(
    user, namespace_name, raise_exception=False
):
    """check and get namespace from users namespaces by name

    :param ..models.res_users.ResUsers user: The user record.
    :param str namespace_name: The name of namespace.
    :param bool raise_exception: raise exception if namespace does not exist.

    :returns: Found 'openapi.namespace' record.
    :rtype: ..models.openapi_namespace.Namespace

    :raise: werkzeug.exceptions.HTTPException if the namespace is not contained
                                              in allowed user namespaces.
    """
    namespace = request.env["openapi.namespace"].sudo().search([("name", "=", namespace_name)])

    if not namespace.exists() and raise_exception:
        raise werkzeug.exceptions.HTTPException(
            response=error_response(*CODE__obj_not_found)
        )

    if namespace not in user.namespace_ids and raise_exception:
        err = list(CODE__user_no_perm)
        err[2] = "The requested namespace (integration) is not authorized."
        raise werkzeug.exceptions.HTTPException(response=error_response(*err))

    return namespace


# Create openapi.log record
def create_log_record(**kwargs):
    test_mode = request.registry.test_cr
    # don't create log in test mode as it's impossible in case of error in sql
    # request (we cannot use second cursor and we cannot use aborted
    # transaction)
    if not test_mode:
        with openerp.registry(request.session.db).cursor() as cr:
            # use new to save data even in case of an error in the old cursor
            env = openerp.api.Environment(cr, request.session.uid, {})
            _create_log_record(env, **kwargs)


def _create_log_record(
    env,
    namespace_id=None,
    namespace=None,
    model=None,
    namespace_log_request=None,
    namespace_log_response=None,
    user_id=None,
    user_request=None,
    user_response=None,
):
    """create log for request

    :param int namespace_id: Requested namespace id.
    :param string namespace_log_request: Request save option.
    :param string namespace_log_response: Response save option.
    :param int user_id: User id which requests.
    :param user_request: a wrapped werkzeug Request object from user.
    :type user_request: :class:`werkzeug.wrappers.BaseRequest`
    :param user_response: a wrapped werkzeug Response object to user.
    :type user_response: :class:`werkzeug.wrappers.Response`

    :returns: New 'openapi.log' record.
    :rtype: ..models.openapi_log.Log
    """
    if True:  # just to keep original indent
        log_data = {
            "namespace_id": namespace_id,
            "request": "%s | %s | %d"
            % (user_request.url, user_request.method, user_response.status_code),
            "request_data": None,
            "response_data": None,
        }
        if namespace_log_request == "debug":
            log_data["request_data"] = user_request.__dict__
        elif namespace_log_request == "info":
            log_data["request_data"] = user_request.__dict__
            for k in ["form", "files"]:
                del log_data["request_data"][k]

        if namespace_log_response == "debug":
            log_data["response_data"] = user_response.__dict__
        elif namespace_log_response == "error" and user_response.status_code > 400:
            log_data["response_data"] = user_response.__dict__

        return env["openapi.log"].create(log_data)


# Patched http route
def route(*args, **kwargs):
    """Set up the environment for rout handlers.

    Patches the framework and additionally authenticates
    the API token and infers database through a different mechanism.

    :param list args: Positional arguments. Transparent pass through to the patched method.
    :param dict kwargs: Keyword arguments. Transparent pass through to the patched method.

    :returns: wrapped method
    """

    def decorator(controller_method):
        @api_route(*args, **kwargs)
        @functools.wraps(controller_method)
        def controller_method_wrapper(*iargs, **ikwargs):

            auth_header = get_auth_header(
                request.httprequest.headers, raise_exception=True
            )
            db_name, user_token = get_data_from_auth_header(auth_header)
            setup_db(request.httprequest, db_name)
            authenticated_user = authenticate_token_for_user(user_token)
            namespace = get_namespace_by_name_from_users_namespaces(
                authenticated_user, ikwargs["endpoint_namespace"], raise_exception=True
            )
            data_for_log = {
                "namespace_id": namespace.id,
                "namespace": namespace.name,
                "model": ikwargs["endpoint_model"],
                "namespace_log_request": namespace.log_request,
                "namespace_log_response": namespace.log_response,
                "user_id": authenticated_user.id,
                "user_request": None,
                "user_response": None,
            }

            try:
                response = controller_method(*iargs, **ikwargs)
            except werkzeug.exceptions.HTTPException as e:
                response = e.response
            except Exception as e:
                traceback.print_exc()
                if hasattr(e, "error") and isinstance(e.error, Exception):
                    e = e.error
                response = error_response(
                    status=500,
                    error=type(e).__name__,
                    error_descrip=e.name if hasattr(e, "name") else str(e),
                )

            data_for_log.update(
                {"user_request": request.httprequest, "user_response": response}
            )
            create_log_record(**data_for_log)

            return response

        return controller_method_wrapper

    return decorator


############################
# Pinguin Metadata Helpers #
############################


# TODO: cache per model and database
# Get the specific context(openapi.access)
def get_create_context(namespace, model, canned_context):
    """Get the requested preconfigured context of the model specification.

    The canned context is used to preconfigure default values or context flags.
    That are used in a repetitive way in namespace for specific model.

    As this should, for performance reasons, not repeatedly result in calls to the persistence
    layer, this method is cached in memory.

    :param str namespace: The namespace to also validate against.
    :param str model: The model, for which we retrieve the configuration.
    :param str canned_context: The preconfigured context, which we request.

    :returns: A dictionary containing the requested context.
    :rtype: dict
    :raise: werkzeug.exceptions.HTTPException TODO: add description in which case
    """
    cr, uid = request.cr, request.session.uid

    # Singleton by construction (_sql_constraints)
    openapi_access = request.env(cr, uid)["openapi.access"].search(
        [("model_id", "=", model), ("namespace_id.name", "=", namespace)]
    )

    assert (
        len(openapi_access) == 1
    ), "'openapi_access' is not a singleton, bad construction."
    # Singleton by construction (_sql_constraints)
    context = openapi_access.create_context_ids.filtered(
        lambda r: r["name"] == canned_context
    )
    assert len(context) == 1, "'context' is not a singleton, bad construction."

    if not context:
        raise werkzeug.exceptions.HTTPException(
            response=error_response(*CODE__canned_ctx_not_found)
        )

    return context


# TODO: cache per model and database
# Get model configuration (openapi.access)
def get_model_openapi_access(namespace, model):
    """Get the model configuration and validate the requested namespace against the session.

    The namespace is a lightweight ACL + default implementation to integrate
    with various integration consumer, such as webstore, provisioning platform, etc.

    We validate the namespace at this latter stage, because it forms part of the http route.
    The token has been related to a namespace already previously

    This is a double purpose method.

    As this should, for performance reasons, not repeatedly result in calls to the persistence
    layer, this method is cached in memory.

    :param str namespace: The namespace to also validate against.
    :param str model: The model, for which we retrieve the configuration.

    :returns: The error response object if namespace validation failed.
        A dictionary containing the model API configuration for this namespace.
            The layout of the dict is as follows:
            ```python
            {'context':                 (Dict)      openerp context (default values through context),
            'out_fields_read_multi':    (Tuple)     field spec,
            'out_fields_read_one':      (Tuple)     field spec,
            'out_fields_create_one':    (Tuple)     field spec,
            'method' : {
                'public' : {
                     'mode':            (String)    one of 'all', 'none', 'custom',
                     'whitelist':       (List)      of method strings,
                 },
                'private' : {
                     'mode':            (String)    one of 'none', 'custom',
                     'whitelist':       (List)      of method strings,
                 },
                'main' : {
                     'mode':            (String)    one of 'none', 'custom',
                     'whitelist':       (List)      of method strings,
                 },
            }
            ```
    :rtype: dict
    :raise: werkzeug.exceptions.HTTPException if the namespace has no accesses.
    """
    # TODO: this method has code duplicates with openapi specification code (e.g. get_OAS_definitions_part)
    cr, uid = request.cr, request.session.uid
    # Singleton by construction (_sql_constraints)
    openapi_access = (
        request.env(cr, uid)["openapi.access"]
        .sudo()
        .search([("model_id", "=", model), ("namespace_id.name", "=", namespace)])
    )
    if not openapi_access.exists():
        raise werkzeug.exceptions.HTTPException(
            response=error_response(*CODE__canned_ctx_not_found)
        )

    res = {
        "context": {},  # Take ot here FIXME: make sure it is for create_context
        "out_fields_read_multi": (),
        "out_fields_read_one": (),
        "out_fields_create_one": (),  # FIXME: for what?
        # By mike start
        "in_fields_api_create_blacklist": (),
        "in_fields_api_update_blacklist": (),
        # By mike end
        "method": {
            "public": {"mode": "", "whitelist": []},
            "private": {"mode": "", "whitelist": []},
            "main": {"mode": "", "whitelist": []},
        },
    }
    # Infer public method mode
    if openapi_access.api_public_methods and openapi_access.public_methods:
        res["method"]["public"]["mode"] = "custom"
        res["method"]["public"]["whitelist"] = openapi_access.public_methods.split()
    elif openapi_access.api_public_methods:
        res["method"]["public"]["mode"] = "all"
    else:
        res["method"]["public"]["mode"] = "none"

    # Infer private method mode
    if openapi_access.private_methods:
        res["method"]["private"]["mode"] = "custom"
        res["method"]["private"]["whitelist"] = openapi_access.private_methods.split()
    else:
        res["method"]["private"]["mode"] = "none"

    for c in openapi_access.create_context_ids.mapped("context"):
        res["context"].update(json.loads(c))

    res["out_fields_read_multi"] = openapi_access.read_many_id.export_fields.mapped(
        "name"
    ) or ("id",)
    res["out_fields_read_one"] = openapi_access.read_one_id.export_fields.mapped(
        "name"
    ) or ("id",)

    # By mike: Blacklisted fields for create or write
    res["in_fields_api_create_blacklist"] = openapi_access.readonly_fields_id.export_fields.mapped("name") or tuple()
    res["in_fields_api_update_blacklist"] = res["in_fields_api_create_blacklist"]

    if openapi_access.public_methods:
        res["method"]["public"]["whitelist"] = openapi_access.public_methods.split()
    if openapi_access.private_methods:
        res["method"]["private"]["whitelist"] = openapi_access.private_methods.split()

    main_methods = ["api_create", "api_read", "api_update", "api_delete"]
    for method in main_methods:
        if openapi_access[method]:
            res["method"]["main"]["whitelist"].append(method)

    if len(res["method"]["main"]["whitelist"]) == len(main_methods):
        res["method"]["main"]["mode"] = "all"
    elif not res["method"]["main"]["whitelist"]:
        res["method"]["main"]["mode"] = "none"
    else:
        res["method"]["main"]["mode"] = "custom"

    return res


def validate_extra_field(field):
    """Validates extra fields on the fly.

    :param str field: The name of the field.

    :returns: None, if validated, otherwise raises.
    :rtype: None
    :raise: werkzeug.exceptions.HTTPException if field is invalid.
    """
    if not isinstance(field, basestring):
        return werkzeug.exceptions.HTTPException(
            response=error_response(*CODE__invalid_spec)
        )


def validate_spec(model, spec):
    """Validates a spec for a given model.

    :param object model: (:obj:`Model`) The model against which to validate.
    :param list spec: The spec to validate.

    :returns: None, if validated, otherwise raises.
    :rtype: None
    :raise: Exception:
                    * if the tuple representing the field does not have length 2.
                    * if the second part of the tuple representing the field is not a list or tuple.
                    * if if a tuple representing a field consists of two parts, but the first part is not a relative field.
                    * if if the second part of the tuple representing the field is of type tuple, but the field is the ratio 2many.
                    * if if the field is neither a string nor a tuple.
    """
    self = model
    for field in spec:
        if isinstance(field, tuple):
            # Syntax checks
            if len(field) != 2:
                raise Exception(
                    "Tuples representing fields must have length 2. (%r)" % field
                )
            if not isinstance(field[1], (tuple, list)):
                raise Exception(
                    """Tuples representing fields must have a tuple wrapped in
                    a list or a bare tuple as it's second item. (%r)"""
                    % field
                )
            # Validity checks
            fld = self._fields[field[0]]
            if not fld.relational:
                raise Exception(
                    "Tuples representing fields can only specify relational fields. (%r)"
                    % field
                )
            if isinstance(field[1], tuple) and fld.type in ["one2many", "many2many"]:
                raise Exception(
                    "Specification of a 2many record cannot be a bare tuple. (%r)"
                    % field
                )
        elif not isinstance(field, six.string_types):
            raise Exception(
                "Fields are represented by either a strings or tuples. Found: %r"
                % type(field)
            )


def update(d, u):
    """Update value of a nested dictionary of varying depth.

    :param dict d: Dictionary to update.
    :param dict u: Dictionary with updates.

    :returns: Merged dictionary.
    :rtype: dict
    """
    for k, v in u.items():
        if isinstance(v, collections.Mapping):
            d[k] = update(d.get(k, collections.OrderedDict([])), v)
        else:
            d[k] = v
    return d


# Transform string fields to dictionary
def transform_strfields_to_dict(fields_list):
    """Transform string fields to dictionary.
    Example:
    for ['name', 'email', 'bank_ids/bank_id/id', 'bank_ids/bank_name', 'bank_ids/id']
    the result will be the next dictionary
    {
        'name': None,
        'email': None
        'bank_ids': {
            'bank_name': None,
            'bank_id': {
                'id': None
            }
        },
    }

    :param list fields_list: The list of string fields.

    :returns: The dict of transformed fields.
    :rtype: dict
    """
    dct = {}
    for field in fields_list:
        parts = field.split("/")
        data = None
        for part in parts[::-1]:
            if part == ".id":
                part = "id"
            data = {part: data}
        update(dct, data)
    return dct


def transform_dictfields_to_list_of_tuples(record, dct):
    """Transform fields dictionary to list.
    for {
        'name': None,
        'email': None
        'bank_ids': {
            'bank_name': None,
            'bank_id': {
                'id': None
            }
        },
    }
    the result will be
    ['name', 'email', ('bank_ids', ['bank_name', ('bank_id', ('id',))])]

    :param openerp.models.Model record: The model object.
    :param dict dct: The dictionary.

    :returns: The list of transformed fields.
    :rtype: list
    """
    fields_with_meta = {
        k: meta for k, meta in record.fields_get().items() if k in dct.keys()
    }
    result = {}
    for key, value in dct.items():
        if isinstance(value, dict):
            model_obj = get_model_for_read(fields_with_meta[key]["relation"])
            inner_result = transform_dictfields_to_list_of_tuples(model_obj, value)
            is_2many = fields_with_meta[key]["type"].endswith("2many")
            result[key] = list(inner_result) if is_2many else tuple(inner_result)
        else:
            result[key] = value
    return [(key, value) if value else key for key, value in result.items()]


##################
# Pinguin Worker #
##################


def wrap__resource__create_one(modelname, context, data, success_code, out_fields):
    """Function to create one record.

    :param str modelname: The name of the model.
    :param dict context: TODO
    :param dict data: Data received from the user.
    :param int success_code: The success code.
    :param tuple out_fields: Canned fields.

    :returns: successful response if the create operation is performed
              otherwise error response
    :rtype: werkzeug.wrappers.Response
    """
    model_obj = get_model_for_read(modelname)
    try:
        created_obj = model_obj.with_context(context).create(data)
        test_mode = request.registry.test_cr
        if not test_mode:
            # Somehow don't making a commit here may lead to error
            # "Record does not exist or has been deleted"
            # Probably, Openerp (10.0 at least) uses different cursors
            # to create and to read fields from database
            request.env.cr.commit()
    except Exception as e:
        return error_response(400, type(e).__name__, str(e))

    out_data = get_dict_from_record(created_obj, out_fields, (), ())
    return successful_response(success_code, out_data)


def wrap__resource__read_all(modelname, success_code, out_fields):
    """function to read all records.

    :param str modelname: The name of the model.
    :param int success_code: The success code.
    :param tuple out_fields: Canned fields.

    :returns: successful response with records data
    :rtype: werkzeug.wrappers.Response
    """
    data = get_dictlist_from_model(modelname, out_fields)
    return successful_response(success_code, data)


def wrap__resource__read_one(modelname, id, success_code, out_fields):
    """Function to read one record.

    :param str modelname: The name of the model.
    :param int id: The record id of which we want to read.
    :param int success_code: The success code.
    :param tuple out_fields: Canned fields.

    :returns: successful response with the data of one record
    :rtype: werkzeug.wrappers.Response
    """
    out_data = get_dict_from_model(modelname, out_fields, id)
    return successful_response(success_code, out_data)


def wrap__resource__update_one(modelname, id, success_code, data):
    """Function to update one record.

    :param str modelname: The name of the model.
    :param int id: The record id of which we want to update.
    :param int success_code: The success code.
    :param dict data: The data for update.

    :returns: successful response if the update operation is performed
              otherwise error response
    :rtype: werkzeug.wrappers.Response
    """
    cr, uid = request.cr, request.session.uid
    record = request.env(cr, uid)[modelname].browse(id)
    if not record.exists():
        return error_response(*CODE__obj_not_found)
    try:
        record.write(data)
    except Exception as e:
        return error_response(400, type(e).__name__, str(e))
    return successful_response(success_code)


def wrap__resource__unlink_one(modelname, id, success_code):
    """Function to delete one record.

    :param str modelname: The name of the model.
    :param int id: The record id of which we want to delete.
    :param int success_code: The success code.

    :returns: successful response if the delete operation is performed
              otherwise error response
    :rtype: werkzeug.wrappers.Response
    """
    cr, uid = request.cr, request.session.uid
    record = request.env(cr, uid)[modelname].browse([id])
    if not record.exists():
        return error_response(*CODE__obj_not_found)
    record.unlink()
    return successful_response(success_code)


def wrap__resource__call_method(modelname, ids, method, method_params, success_code):
    """Function to call the model method for records by IDs.

    :param str modelname: The name of the model.
    :param list ids: The record ids of which we want to call method.
    :param str method: The name of the method.
    :param int success_code: The success code.

    :returns: successful response if the method execution did not cause an error
              otherwise error response
    :rtype: werkzeug.wrappers.Response
    """
    model_obj = get_model_for_read(modelname)

    if not hasattr(model_obj, method):
        return error_response(*CODE__invalid_method)

    records = model_obj.browse(ids).exists()
    results = []
    args = method_params.get("args", [])
    kwargs = method_params.get("kwargs", {})
    for record in records or [model_obj]:
        result = getattr(record, method)(*args, **kwargs)
        results.append(result)

    if len(ids) <= 1 and len(results):
        results = results[0]
    return successful_response(success_code, data=results)


def wrap__resource__get_report(
    namespace, report_external_id, docids, converter, success_code
):
    """Return html or pdf report response.

    :param namespace: id/ids/browserecord of the records to print (if not used, pass an empty list)
    :param docids: id/ids/browserecord of the records to print (if not used, pass an empty list)
    :param docids: id/ids/browserecord of the records to print (if not used, pass an empty list)
    :param report_name: Name of the template to generate an action for
    """
    report = request.env.ref(report_external_id)

    if isinstance(report, type(request.env["ir.ui.view"])):
        report = request.env["report"]._get_report_from_name(report_external_id)

    model = report.model
    report_name = report.report_name

    get_model_openapi_access(namespace, model)

    response = ReportController().report_routes(report_name, docids, converter)
    response.status_code = success_code
    return response


#######################
# Pinguin ORM Wrapper #
#######################


# Dict from model
def get_dict_from_model(model, spec, id, **kwargs):
    """Fetch dictionary from one record according to spec.

    :param str model: The model against which to validate.
    :param tuple spec: The spec to validate.
    :param int id: The id of the record.
    :param dict kwargs: Keyword arguments.
    :param tuple kwargs['include_fields']: The extra fields.
        This parameter is not implemented on higher level code in order
        to serve as a soft ACL implementation on top of the framework's
        own ACL.
    :param tuple kwargs['exclude_fields']: The excluded fields.

    :returns: The python dictionary of the requested values.
    :rtype: dict
    :raise: werkzeug.exceptions.HTTPException if the record does not exist.
    """
    include_fields = kwargs.get(
        "include_fields", ()
    )  # Not actually implemented on higher level (ACL!)
    exclude_fields = kwargs.get("exclude_fields", ())

    model_obj = get_model_for_read(model)

    record = model_obj.browse([id])
    if not record.exists():
        raise werkzeug.exceptions.HTTPException(
            response=error_response(*CODE__res_not_found)
        )
    return get_dict_from_record(record, spec, include_fields, exclude_fields)


# List of dicts from model
def get_dictlist_from_model(model, spec, **kwargs):
    """Fetch dictionary from one record according to spec.

    :param str model: The model against which to validate.
    :param tuple spec: The spec to validate.
    :param dict kwargs: Keyword arguments.
    :param list kwargs['domain']: (optional). The domain to filter on.
    :param int kwargs['offset']: (optional). The offset of the queried records.
    :param int kwargs['limit']: (optional). The limit to query.
    :param str kwargs['order']: (optional). The postgres order string.
    :param tuple kwargs['include_fields']: (optional). The extra fields.
        This parameter is not implemented on higher level code in order
        to serve as a soft ACL implementation on top of the framework's
        own ACL.
    :param tuple kwargs['exclude_fields']: (optional). The excluded fields.

    :returns: The list of python dictionaries of the requested values.
    :rtype: list
    """
    domain = kwargs.get("domain", [])
    offset = kwargs.get("offset", 0)
    limit = kwargs.get("limit")
    order = kwargs.get("order")
    include_fields = kwargs.get(
        "include_fields", ()
    )  # Not actually implemented on higher level (ACL!)
    exclude_fields = kwargs.get("exclude_fields", ())

    model_obj = get_model_for_read(model)

    records = model_obj.sudo().search(domain, offset=offset, limit=limit, order=order)

    # Do some optimization for subfields
    _prefetch = {}
    for field in spec:
        if isinstance(field, basestring):
            continue
        _fld = records._fields[field[0]]
        if _fld.relational:
            _prefetch[_fld.comodel] = records.mapped(field[0]).ids

    for mod, ids in _prefetch.iteritems():
        get_model_for_read(mod).browse(ids).read()

    result = []
    for record in records:
        result += [get_dict_from_record(record, spec, include_fields, exclude_fields)]

    return result


# Get a model with special context
def get_model_for_read(model):
    """Fetch a model object from the environment optimized for read.

    Postgres serialization levels are changed to allow parallel read queries.
    To increase the overall efficiency, as it is unlikely this API will be used
    as a mass transactional interface. Rather we assume sequential and structured
    integration workflows.

    :param str model: The model to retrieve from the environment.

    :returns: the framework model if exist, otherwise raises.
    :rtype: openerp.models.Model
    :raise: werkzeug.exceptions.HTTPException if the model not found in env.
    """
    cr, uid = request.cr, request.session.uid
    test_mode = request.registry.test_cr
    if not test_mode:
        # Permit parallel query execution on read
        # Contrary to ISOLATION_LEVEL_SERIALIZABLE as per Openerp Standard
        cr._cnx.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)
    try:
        return request.env(cr, uid)[model]
    except KeyError:
        err = list(CODE__obj_not_found)
        err[2] = 'The "%s" model is not available on this instance.' % model
        raise werkzeug.exceptions.HTTPException(response=error_response(*err))


# Python > 3.5
# def get_dict_from_record(record, spec: tuple, include_fields: tuple, exclude_fields: tuple):

# Extract nested values from a record
def get_dict_from_record(record, spec, include_fields, exclude_fields):
    """Generates nested python dict representing one record.

    Going down to the record level, as the framework does not support nested
    data queries natively as they are typical for a REST API.

    :param openerp.models.Model record: The singleton record to load.
    :param tuple spec: The field spec to load.
    :param tuple include_fields: The extra fields.
    :param tuple exclude_fields: The excluded fields.

    :returns: The python dictionary representing the record according to the field spec.
    :rtype collections.OrderedDict
    """
    map(validate_extra_field, include_fields + exclude_fields)
    result = collections.OrderedDict([])
    _spec = [fld for fld in spec if fld not in exclude_fields] + list(include_fields)
    if filter(lambda x: isinstance(x, six.string_types) and "/" in x, _spec):
        _spec = transform_dictfields_to_list_of_tuples(
            record, transform_strfields_to_dict(_spec)
        )
    validate_spec(record, _spec)

    for field in _spec:

        if isinstance(field, tuple):
            # It's a 2many (or a 2one specified as a list)
            if isinstance(field[1], list):
                result[field[0]] = []
                for rec in record[field[0]]:
                    result[field[0]] += [get_dict_from_record(rec, field[1], (), ())]
            # It's a 2one
            if isinstance(field[1], tuple):
                result[field[0]] = get_dict_from_record(
                    record[field[0]], field[1], (), ()
                )
        # Normal field, or unspecified relational
        elif isinstance(field, six.string_types):
            if not hasattr(record, field):
                raise openerp.exceptions.ValidationError(
                    openerp._('The model "%s" has no such field: "%s".')
                    % (record._name, field)
                )

            # result[field] = getattr(record, field)
            value = record[field]
            result[field] = value
            fld = record._fields[field]
            if fld.relational:
                if fld.type.endswith("2one"):
                    result[field] = value.id
                elif fld.type.endswith("2many"):
                    result[field] = value.ids
            elif (value is False or value is None) and fld.type != "boolean":
                # string field cannot be false in response json
                result[field] = ""
    return result


# Check that the method is allowed
def method_is_allowed(method, methods_conf, main=False, raise_exception=False):
    """Check that the method is allowed for the specified settings.

    :param str method: The name of the method.
    :param dict methods_conf: The methods configuration dictionary.
        A dictionary containing the methods API configuration.
            The layout of the dict is as follows:
            ```python
            {
                'public' : {
                     'mode':            (String)    one of 'all', 'none', 'custom',
                     'whitelist':       (List)      of method strings,
                 },
                'private' : {
                     'mode':            (String)    one of 'none', 'custom',
                     'whitelist':       (List)      of method strings,
                 },
                'main' : {
                     'mode':            (String)    one of 'none', 'custom',
                     'whitelist':       (List)      of method strings,
                 },
            }
            ```
    :param bool main: The method is a one of access fields.
    :param bool raise_exception: raise exception instead of returning **False**.

    :returns: **True** if the method is allowed, otherwise **False**.
    :rtype: bool
    :raise: werkzeug.exceptions.HTTPException if the method is not allowed and
                                              raise_exception is **True**.
    """
    if main:
        method_type = "main"
    else:
        method_type = "private" if method.startswith("_") else "public"

    if methods_conf[method_type]["mode"] == "all":
        return True
    if (
        methods_conf[method_type]["mode"] == "custom"
        and method in methods_conf[method_type]["whitelist"]
    ):
        return True
    if raise_exception:
        raise werkzeug.exceptions.HTTPException(
            response=error_response(*CODE__method_blocked)
        )
    return False


# By Mike: Check that the fields are allowed
def fields_are_allowed(method, data, fields_blacklist):
    blocked = []
    for k in data.keys():
        if any(f.startswith(k) for f in fields_blacklist):
            blocked.append(k)
    if blocked:
        error_description = "Fields '%s' are not allowed for method '%s'" % (blocked, method)
        raise werkzeug.exceptions.HTTPException(
            response=error_response(401, "Field Permissions", error_description)
        )
    return True


###############
# Pinguin OAS #
###############

# Get definition name
def get_definition_name(modelname, prefix="", postfix="", splitter="-"):
    """Concatenation of the prefix, modelname, postfix.

    :param str modelname: The name of the model.
    :param str prefix: The prefix.
    :param str postfix: The postfix.
    :param str splitter: The splitter.

    :returns: Concatenation of the arguments
    :rtype: str
    """
    return splitter.join([s for s in [prefix, modelname, postfix] if s])


# Get OAS definitions part for model and nested models
def get_OAS_definitions_part(
    model_obj, export_fields_dict, definition_prefix="", definition_postfix="",
):
    """Recursively gets definition parts of the OAS for model by export fields.

    :param openerp.models.Model model_obj: The model object.
    :param dict export_fields_dict: The dictionary with export fields.
            Example of the dict is as follows:
            ```python
            {
                u'active': None,
                u'child_ids': {
                    u'user_ids': {
                        u'city': None,
                        u'login': None,
                        u'password': None,
                        u'id': None}, u'id': None
                    },
                    u'email': None,
                    u'name': None
                }
            ```

    :param str definition_prefix: The prefix for definition name.
    :param str definition_postfix: The postfix for definition name.

    :returns: Definitions for the model and relative models.
    :rtype: dict
    """
    definition_name = get_definition_name(
        model_obj._name, definition_prefix, definition_postfix
    )

    definitions = {
        definition_name: {"type": "object", "properties": {}, "required": []},
    }

    fields_meta = model_obj.fields_get(export_fields_dict.keys())

    for field, child_fields in export_fields_dict.items():
        meta = fields_meta[field]
        if child_fields:
            child_model = model_obj.env[meta["relation"]]
            child_definition = get_OAS_definitions_part(
                child_model, child_fields, definition_prefix=definition_name
            )

            if meta["type"].endswith("2one"):
                field_property = child_definition[
                    get_definition_name(child_model._name, prefix=definition_name)
                ]
            else:
                field_property = {
                    "type": "array",
                    "items": child_definition[
                        get_definition_name(child_model._name, prefix=definition_name)
                    ],
                }
        else:
            field_property = {}

            if meta["type"] == "integer":
                field_property.update(type="integer")
            elif meta["type"] == "float":
                field_property.update(type="number", format="float")
            elif meta["type"] == "char":
                field_property.update(type="string")
            elif meta["type"] == "text":
                field_property.update(type="string")
            elif meta["type"] == "binary":
                field_property.update(type="string", format="binary")
            elif meta["type"] == "boolean":
                field_property.update(type="boolean")
            elif meta["type"] == "date":
                field_property.update(type="string", format="date")
            elif meta["type"] == "datetime":
                field_property.update(type="string", format="date-time")
            elif meta["type"] == "many2one":
                field_property.update(type="integer")
            elif meta["type"] == "selection":
                field_property.update(
                    {
                        "type": "integer"
                        if isinstance(meta["selection"][0][0], int)
                        else "string",
                        "enum": [i[0] for i in meta["selection"]],
                    }
                )
            elif meta["type"] in ["one2many", "many2many"]:
                field_property.update({"type": "array", "items": {"type": "integer"}})

            # We cannot have both required and readOnly flags in field openapi
            # definition, for that reason we cannot blindly use openerp's
            # attributed readonly and required.
            #
            # 1) For openerp-required, but NOT openerp-related field, we do NOT use
            # openapi-readonly
            #
            # Example of such field can be found in sale module:
            #     partner_id = fields.Many2one('res.partner', readonly=True,
            #     states={'draft': [('readonly', False)], 'sent': [('readonly',
            #     False)]}, required=True, ...)
            #
            # 2) For openerp-required and openerp-related field, we DO use
            # openapi-readonly, but we don't use openapi-required
            if meta["readonly"] and (not meta["required"] or meta.get("related")):
                field_property.update(readOnly=True)

        definitions[definition_name]["properties"][field] = field_property

        if meta["required"] and not meta.get("related"):
            fld = model_obj._fields[field]
            # Mark as required only if field doesn't have defaul value
            # Boolean always has default value (False)
            if fld.default is None and fld.type != "boolean":
                definitions[definition_name]["required"].append(field)

    if not definitions[definition_name]["required"]:
        del definitions[definition_name]["required"]

    return definitions
