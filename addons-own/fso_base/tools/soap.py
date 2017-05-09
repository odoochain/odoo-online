# -*- coding: utf-8 -*-
from openerp.addons.fso_base.tools.validate import is_valid_url
from openerp.tools.translate import _
from jinja2 import Template, Environment, FileSystemLoader
import requests
from requests import Session
import os
import ntpath
import logging
# https://pypi.python.org/pypi/timeout-decorator
import timeout_decorator

logger = logging.getLogger(__name__)


# Avoid exceptions on nested dict variables
# http://stackoverflow.com/questions/21692387/jinja2-exception-handling
# http://jinja.pocoo.org/docs/2.9/api/#writing-filters
def empty_if_exception_filter(value):
    try:
        return value
    except:
        return ""


class GenericTimeoutError(Exception):
    def __init__(self):
        Exception.__init__(self, "Execution stopped because of global timeout and not the request.Session() timeout!"
                                 "There may be a passphrase in your private key.")


# Multithreaded enabled timeout strategy
@timeout_decorator.timeout(14, use_signals=False, timeout_exception=GenericTimeoutError)
def soap_request(url="", template="", http_header={}, crt_pem="", prvkey_pem="", **template_args):
    # Validate the input
    assert all((url, template)), _("Parameters missing! Required are url and template.")
    is_valid_url(url=url)
    if crt_pem or prvkey_pem:
        assert all((crt_pem, prvkey_pem)), _("Certificate- and Private-Key-File needed if one of them is given!")
        assert len(crt_pem) <= 255 and len(prvkey_pem) <= 255, _("Path to cert- or key-file is longer than 255 chars!")
        assert os.path.exists(crt_pem), _("Certificate file not found at %s") % crt_pem
        assert os.path.exists(prvkey_pem), _("Private key file not found at %s") & prvkey_pem

    # Set the http header of the request (not the soap header)
    http_header = http_header or {
        'content-type': 'text/xml; charset=utf-8',
        'SOAPAction': ''
    }

    # Render the soap request data
    # Try to detect if the template is a file or directly the jinja data to render
    if os.path.exists(template):
        j2_env = Environment(loader=FileSystemLoader(os.path.abspath(os.path.dirname(template))))
        j2_env.filters['empty_if_exception_filter'] = empty_if_exception_filter
        soap_request_template = j2_env.get_template(ntpath.basename(template))
        request_data = soap_request_template.render(**template_args)
    else:
        jinja2_template = Template(template)
        request_data = jinja2_template.render(**template_args)

    # Create a Session Object (just like a regular UA e.g. Firefox or Chrome)
    session = Session()
    session.verify = True
    if crt_pem and prvkey_pem:
        session.cert = (crt_pem, prvkey_pem)

    # Send the request (POST)
    # http://docs.python-requests.org/en/master/user/advanced/
    request_data = request_data.encode('utf-8')
    response = session.post(url, data=request_data, headers=http_header, timeout=15)

    # Check for response errors
    # DISABLED: Because in most cases one would still want to process the response content to check error in
    #           Soap XML Answer
    # if response.status_code != requests.codes.ok:
    #     logger.error(_('Soap request returned the http error code %s') % response.status_code)
    #     logger.error(_('Soap request response content:\n%s\n') % response.content)
    #     response.raise_for_status()

    # Return the Response
    # HINT: There could still be an error in the response.content: Not all are nice and raise an http error
    return response
