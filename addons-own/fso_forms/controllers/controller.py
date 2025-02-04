# -*- coding: utf-8 -*-
##############################################################################
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
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

from openerp import http
from openerp.http import request
from openerp import tools
from openerp.tools.translate import _
from openerp.exceptions import AccessError

# import locale
# import urllib2
import base64
import datetime
from collections import namedtuple
from copy import deepcopy
import ast

import logging
_logger = logging.getLogger(__name__)

# E-Mail rendering without a record for email_only forms
try:
    from openerp.addons.email_template.email_template import mako_template_env
    from openerp.addons.email_template.email_template import format_tz
except ImportError:
    _logger.warning("Could not import 'mako_template_env' or 'format_tz'! "
                    "E-mail rendering without a record will not work!")

# Token login Form
from openerp.addons.website_login_fs_ptoken.controllers.controller import AuthPartnerForm


class FsoForms(http.Controller):

    # Allowed and necessary keys for a fso_form in request.session
    _valid_form_sdata_keys = ('form_id', 'form_uid', 'form_record_id', 'form_model_id',
                              'clear_session_data')

    def get_fso_form_session_key(self, form_id):
        assert form_id and int(form_id), "FSO Form ID must be a valid integer!"
        return 'fso_form_' + str(form_id)

    # ATTENTION: !!! request.session information will be copied between multiple request but
    #                NOT DEEP copied! Therefore never use nested data structures in request.session!
    def set_fso_form_session_data(self, form_id, form_uid, form_record_id, form_model_id,
                                  clear_session_data=False):
        form_id = str(form_id)
        form_key = self.get_fso_form_session_key(form_id)

        # Store / Overwrite the form information in the current session
        request.session[form_key] = {
            'form_id': form_id,
            'form_uid': form_uid,
            'form_record_id': form_record_id,
            'form_model_id': form_model_id,
            'clear_session_data': clear_session_data,
        }

    def get_fso_form_session_data(self, form, check_clear_session_data=True):
        """
        Returns the session data of the form if the data still matches the current form data and request user

        :param form_id:
        :param check_clear_session_data:
        :return: dict with session data or empty
        """
        form_id = str(form.id)
        form_key = self.get_fso_form_session_key(form_id)

        # Get form session data
        form_sdata = request.session.get(form_key, False)

        # Return an empty dict if there is no session data at all
        if not form_sdata:
            _logger.info("No fso form session data found for form_id %s" % form_id)
            return dict()

        # Check the structure of the form session data
        form_sdata_keys = form_sdata.keys()
        if not isinstance(form_sdata, dict) or set(form_sdata_keys) != set(self._valid_form_sdata_keys):
            _logger.error('Remove fso_form %s session data because of unexpected or missing keys in %s!'
                          '' % (form_id, str(form_sdata_keys)))
            self.remove_fso_form_session_data(form_id)
            return dict()

        # Check if the user changed (e.g. after an login or logout)
        if request.uid != form_sdata['form_uid']:
            self.remove_fso_form_session_data(form_id)
            return dict()

        # Check if the form model changed
        if form.model_id.id != form_sdata['form_model_id']:
            self.remove_fso_form_session_data(form_id)
            return dict()

        # Check if we need to clear the form session data anyway
        if check_clear_session_data:
            if form_sdata['clear_session_data']:
                self.remove_fso_form_session_data(form_id)
                return dict()

        # Return the form session data
        return form_sdata

    def remove_fso_form_session_data(self, form_id):
        form_id = str(form_id)
        form_key = self.get_fso_form_session_key(form_id)
        # Remove the form session data
        request.session.pop(form_key, False)

    def get_fso_form_records_by_user(self, form=None, user=None):
        """
        Return all records of the form model (form.model_id.model) where the login-marked-field of the form model
        matches the given user or it's related partner!

        Inherit this method if you need to choose a specific record out of the found records. (e.g. status=approved or
        list_id=x)

        :param form: The fso form record
        :param user: The logged in user record
        :return: recordset of the form model
        """
        form_model_name = form.model_id.model

        # TODO: Replace sudo with the logged in user or by users set in the form to write the record
        form_model_obj = request.env[form_model_name]

        if form_model_name == 'res.user':
            return user
        if form_model_name == 'res.partner':
            return user.partner_id

        # Try to find a 'login' field in the current form
        login_field = form.field_ids.filtered(lambda r: r.login)
        if not login_field or len(login_field) != 1 or login_field.field_id.relation not in ['res.user', 'res.partner']:
            return form_model_obj

        # Search for all records in the form-model where the login field matches the currently logged in user or
        # its related partner
        search_id = user.id if login_field.field_id.relation == 'res.user' else user.partner_id.id
        records = form_model_obj.search([(login_field.field_id.name, '=', search_id)])
        if not records:
            return form_model_obj

        return records

    def get_fso_form_record(self, form):
        """
        Search
        :param form: The form recordset.ensureone()
        :return: recordset of the form model (one record or empty recordset!)
        """
        form_model_name = form.model_id.model

        # Get the form model and an empty record set
        form_model_obj = request.env[form_model_name]
        record = request.env[form_model_name]

        # Return an empty recordset it this is an email only form!
        if form.email_only:
            return form_model_obj

        # TRY TO FIND THE RECORD BASED ON THE CURRENT SESSION
        # ---------------------------------------------------
        form_sdata = self.get_fso_form_session_data(form)
        if form_sdata:
            session_record = form_model_obj.browse([form_sdata['form_record_id']])
            # Check if we have at least read access to the record
            # HINT: Could not use session_record.check_access_rights('read', raise_exception=False) because it will
            #       simply not work correctly for the default public/website user (uid 3)
            try:
                session_record[session_record._fields.keys()[0]]
                record = session_record
            except AccessError:
                _logger.error("No read access for the current fso_forms session record! %s" % session_record)
                pass

        # TRY TO FIND A FORM-RELATED-RECORD BASED ON THE LOGGED IN USER AND THE LOGIN-MARKED-FIELD
        # ----------------------------------------------------------------------------------------
        # Get the request user if the current user is not the website public user
        logged_in_user = False
        if request.website.user_id.id != request.uid:
            logged_in_user = request.env['res.users'].sudo().browse([request.uid])

        # HINT: Only if 'edit_existing_record_if_logged_in' is set in the form!
        if logged_in_user and form.edit_existing_record_if_logged_in:

            # If the logged in user just created a record we simply return the record from the session!
            if form_sdata and str(form_sdata['form_uid']) == str(logged_in_user.id) and record and len(record) == 1:
                pass

            # Try to find the record based on the logged in user
            else:
                # HINT: You may inherit get_fso_form_records_by_user() to select or filter for a different record!
                form_records_by_user = self.get_fso_form_records_by_user(form=form, user=logged_in_user)

                # Return a record only if exactly ONE record was found else we return an empty recordset
                if form_records_by_user and len(form_records_by_user) == 1:
                    user_record = form_records_by_user
                    # Check if we have at least read access to the record
                    # HINT: Could not use user_record.check_access_rights('read', raise_exception=False) because it
                    #       will simply not work correctly for the default public/website user (uid 3)
                    try:
                        user_record[user_record._fields.keys()[0]]
                        record = user_record
                    except AccessError:
                        _logger.error("No read access for the current fso_forms user_record! %s" % user_record)
                        pass
                else:
                    record = request.env[form_model_name]

            # Set/Update the session data based on the found record but without clear session data since
            # 'edit_existing_record_if_logged_in' is set!
            if len(record) == 1:
                self.set_fso_form_session_data(form_id=form.id,
                                               form_uid=logged_in_user.id,
                                               form_record_id=record.id,
                                               form_model_id=form.model_id.id,
                                               clear_session_data=False)

        # RETURN THE RECORD
        # -----------------
        # Clear Session Data if the record was not found or too many records are found an return an empty recordset
        if len(record) != 1:
            _logger.warning('Record for current fso_form not found! Clearing fso_form data from request.session!')
            self.remove_fso_form_session_data(form.id)
            return form_model_obj
        else:
            # Record found
            return record

    def validate_fields(self, form, field_data):
        field_errors = dict()

        # SPAM detection by honeypot fields
        honey_pot_fields = (f for f in form.field_ids if f.type == 'honeypot')
        honey_pot_test = any(field_data.get(f.name, None) for f in honey_pot_fields)
        if honey_pot_test:
            return {'honey_pot_test': True}

        # Validate regular (model) fields
        for f in form.field_ids:
            if not f.show:
                continue

            if f.type == 'model':

                # ATTENTION: Skipp readonly fields if a user is logged in
                if f.readonly and request.website.user_id.id != request.uid:
                    continue

                f_name = f.name
                f_display_name = f.label if f.label else f_name
                f_type = f.field_id.ttype
                f_style = f.style

                # Get the value of the field
                if f_type == 'boolean':
                    if f_style == 'radio':
                        f_value = True if field_data.get(f_name, None) == 'True' else False
                    else:
                        f_value = True if field_data.get(f_name, None) else False
                else:
                    if f_style in ['radio', 'radio_selectnone']:
                        f_value = field_data.get(f_name, False)
                    else:
                        f_value = field_data[f_name]

                # Selection forced
                if f.force_selection and f_name not in field_data:
                    field_errors[f_name] = _("No value selected for field %s" % f_display_name)
                    continue

                # Mandatory
                if f.mandatory and not f_value:
                    field_errors[f_name] = _("No value for mandatory field %s" % f_display_name)
                    continue

                # Date format
                # TODO: Localization !!!
                if f.field_id.ttype == 'date' and f_value:
                    try:
                        datetime.datetime.strptime(f_value.strip(), '%d.%m.%Y')
                    except Exception as e:
                        _logger.warning('Date conversion failed for string %s' % f_value)
                        field_errors[f_name] = _("Please enter a valid date for field %s" % f_display_name)
                        continue

                # Integers
                if f.field_id.ttype == 'integer' and f_value:
                    try:
                        int(f_value)
                    except Exception as e:
                        _logger.warning('Integer conversion failed for string %s' % f_value)
                        field_errors[f_name] = _("Please enter a valid number for field %s" % f_display_name)
                        continue

                # Floats
                # TODO: Localization - !!! Right now we always expect DE values e.g.: 22.000,12 !!!
                if f.field_id.ttype == 'float' and f_value:
                    try:
                        # Clean up and convert DE Float-Strings
                        assert len(f_value.rsplit(',')[-1]) <= len(f_value.rsplit('.')[-1]), 'Wrong float format?!?'
                        float(f_value.replace(',', ':').replace('.', '').replace(':', '.'))
                    except Exception as e:
                        _logger.warning('Float conversion failed for string %s' % f_value)
                        field_errors[f_name] = _("Please enter a valid float for field %s" % f_display_name)
                        continue

                # TODO: validate binary (mime type)

        return field_errors

    def _prepare_field_data(self, form=None, form_field_data=None, record=None):
        form_field_data = form_field_data or {}

        # Values dict with transformed field data
        values = {}

        # Loop through all the fields in the form
        for f in form.field_ids:
            if not f.show:
                continue

            # Get the name of the field in the form
            f_name = f.name

            # Regular Model Field
            # -------------------
            if f.type == 'model':
                # ATTENTION: Skipp readonly fields if a user is logged in and a record was found
                if f.readonly and request.website.user_id.id != request.uid and record:
                    continue

                f_type = f.field_id.ttype
                f_style = f.style

                # Get the value of the field
                if f_type == 'boolean':
                    if f_style == 'radio':
                        f_value = True if form_field_data.get(f_name, None) == 'True' else False
                    else:
                        f_value = True if form_field_data.get(f_name, None) else False
                else:
                    if f_style in ['radio', 'radio_selectnone']:
                        f_value = form_field_data.get(f_name, False)
                    else:
                        f_value = form_field_data[f_name]

                # SKIPP NODATA FIELDS IF EMPTY OR FALSE AND CONTINUE TO NEXT FIELD
                # HINT: Fields with no pre-filled data (nodata) can only be included if there is a value in field_data
                #       Otherwise we may clear the existing value by accident!
                if f.nodata and not f_value:
                    continue

                # Add BOOLEAN
                if f_type == 'boolean':
                    values[f_name] = True if f_value else False
                    continue

                # Add DATE
                if f_type == 'date':
                    if f_value:
                        # TODO: Localization !!!
                        f_value = datetime.datetime.strptime(f_value.strip(), '%d.%m.%Y')
                    values[f_name] = f_value or False
                    continue

                # Add BINARY
                if f_type == 'binary':
                    if f_value:
                        values[f_name] = base64.encodestring(f_value.read()) or False
                        if f.binary_name_field_id:
                            values[f.binary_name_field_id.name] = f_value.filename if values[f_name] else False
                    continue
                    # ATTENTION: We do no longer empty binary fields by default.
                    #            (The same effect as nodata was set to True)
                    #else:
                        # values[f_name] = False
                        # if f.binary_name_field_id:
                        #     values[f.binary_name_field_id.name] = False
                        # continue

                # Add FLOAT
                # TODO: Localization - !!! Right now we expect DE values from the forms !!!
                if f_type == 'float':
                    if f_value:
                        values[f_name] = f_value.replace(',', ':').replace('.', '').replace(':', '.')
                    continue

                # Add MANY2ONE
                if f_type == 'many2one':
                    if f_value:
                        values[f_name] = int(f_value)
                    continue

                # ALL OTHER FIELD TYPES
                values[f_name] = f_value or False

        return values

    def _prepare_kwargs_for_form(self, form, record=None, **kwargs):

        if kwargs:
            for f in form.field_ids:

                f_name = f.name


                # Regular model fields
                if f.type == 'model':

                    # Remove binary fields (e.g. images) from kwargs before rendering the form
                    if f.field_id.ttype == 'binary':
                        if f_name in kwargs:
                            kwargs.pop(f_name)

                    # Convert german date strings '%d.%m.%Y' to the default odoo datetime string format %Y-%m-%d
                    # because the are expected like this in the template 'form_fields'
                    # TODO: Localization - !!! Right now we expect DE values from the forms !!!
                    if f.field_id.ttype == 'date':
                        date_string = kwargs.get(f.name, '')
                        if date_string:
                            try:
                                date = datetime.datetime.strptime(date_string, '%d.%m.%Y')
                                date_odoo_format = datetime.datetime.strftime(date, '%Y-%m-%d')
                                kwargs[f_name] = date_odoo_format
                            except Exception as e:
                                _logger.error("Could not convert german date string to odoo format! %s" % date_string)
                                pass

        return kwargs

    def _prepare_kwargs_for_mail(self, form, **kwargs):

        # Result
        form_values = dict()

        if not kwargs:
            return form_values

        for f in form.field_ids:
            f_name = f.name

            if f_name in kwargs:

                # Comment (Mail-Message-Field)
                if f.type == 'mail_message':
                    form_values[f_name] = kwargs[f_name]

                # Regular (model) fields
                elif f.type == 'model':

                    # binary: Ignore binary fields
                    if f.field_id.ttype == 'binary':
                        continue

                    # selection: Replace selection value with the selection name
                    elif f.field_id.ttype == 'selection':
                        item_id = kwargs[f_name]
                        try:
                            item_name = dict(request.env[form.model_id.model].fields_get([f_name])[f_name]['selection']
                                             )[item_id]
                            form_values[f_name] = item_name
                        except:
                            form_values[f_name] = kwargs[f_name]

                    # many2one: Replace the id with the name of the record
                    elif f.field_id.ttype == 'many2one':
                        try:
                            item_name = request.env[f.field_id.relation].search([('id', '=', kwargs[f_name])]).name
                            form_values[f_name] = item_name
                        except:
                            form_values[f_name] = kwargs[f_name]

                    # Include all other fields
                    else:
                        form_values[f_name] = kwargs[f_name]

        return form_values

    def _get_session_information(self):
        environ = request.httprequest.headers.environ
        return {
            'remote_addr': environ.get("REMOTE_ADDR"),
            'http_user_agent': environ.get("HTTP_USER_AGENT"),
            'http_accept_language': environ.get("HTTP_ACCEPT_LANGUAGE"),
            'http_referer': environ.get("HTTP_REFERER"),
        }

    # Custom email template rendering without a record
    def render_mako_template_string(self, template_string, template_values=None, user=None):
        template_string = template_string if template_string else u''
        template_values = template_values if template_values else dict()
        assert isinstance(template_values, dict), "values must be a dictionary!"

        # Load the mako template environment
        # ----------------------------------
        try:
            template = mako_template_env.from_string(tools.ustr(template_string))
        except Exception as e:
            _logger.error("Could not render e-mail template! Initialization of mako template failed!\n%s" % repr(e))
            return u''

        # Prepare the template_vars
        # -------------------------
        req = request
        pool, cr, uid, ctx = req.env['email.template'].pool, req.cr, req.uid, req.context
        # HINT: This 1.) creates a named tuple object with all attributes from the dict and then
        #            2.) assigns the values of the dict to the named_tuple arguments
        #                *values.values() means we unpack the dict (e.g.: {'key1': '3'} will be key1='3')
        # ATTENTION: A NamedTuple will genereate an ._fields just like a regular odoo record!
        #            therefore you could use this in the mako template if you want to show all fields of the record!
        tvalues_object = namedtuple("TemplateValueObject", template_values.keys())(*template_values.values())
        # HINT: These variables should be available to all templates (specified in the addon email_template)
        template_vars = {
            'format_tz': lambda dt, tz=False, format=False, context=ctx: format_tz(pool, cr, uid, dt, tz, format,
                                                                                   context),
            'user': user if user else req.env.user,
            'ctx': ctx,
            'object': tvalues_object
        }

        # Render the mako template
        # ------------------------
        try:
            output = template.render(template_vars)
            output = u'' if (not output or output == u'False') else output
        except Exception as e:
            _logger.error('Could not render email template!\n%s' % repr(e))
            return u''

        return output

    def send_mail(self, template=None, record=None, template_values=None, email_to=None, partner_receipient_ids=None):
        # HINT: template_values is for e-mail only forms and not used if a record is given!
        assert not (template_values and record), "Use a record or template_values to send the email but not both!"
        assert template.subject, "Subject is missing in email template %s (ID: %s)" % (template.name, template.id)

        # Prepare common email values
        email_from = template.email_from if template.email_from else request.website.user_id.company_id.email
        reply_to = template.reply_to if template.reply_to else False
        recipient_ids = [(6, 0, partner_receipient_ids)] if partner_receipient_ids else False

        # Send the email by the email composer wizard found in the addon mail
        if record:
            composer_context = {
                'default_composition_mode': 'mass_mail',
                'default_use_template': True,
                'default_template_id': template.id,
                'default_model': record._name,
                'default_res_id': record.id,
            }
            composer_values = {
                'email_from': email_from,
                'reply_to': reply_to,
                'email_to': email_to,
                'partner_ids': recipient_ids,
                'subject': template.subject,
                'body': template.body_html,
            }
            composer_obj = request.env['mail.compose.message'].sudo()
            composer_record = composer_obj.with_context(composer_context).create(composer_values)
            composer_record.send_mail()

        # Create the email manually
        else:
            body_html = self.render_mako_template_string(template_string=template.body_html,
                                                         template_values=template_values)
            subject = self.render_mako_template_string(template_string=template.subject,
                                                       template_values=template_values)
            email_values = {
                'email_from': email_from,
                'reply_to': reply_to,
                'email_to': email_to,
                'recipient_ids': recipient_ids,
                'subject': subject,
                'body': '',
                'body_html': body_html,
                'auto_delete': template.auto_delete,
            }
            request.env['mail.mail'].sudo().create(email_values)

    def send_form_emails(self, form, form_values=None, record=None):
        assert not (form_values and record), "Use a record or the form_values to render the email but not both!"
        if not (form.confirmation_email_template or form.information_email_template):
            _logger.warning("No email template selected!")
            return False
        if form.email_only and record:
            _logger.error("E-Mail only selected but record is given!")
            return False
        if not form.email_only and not record:
            _logger.error("No record given!")
            return False

        # Add session information to template_values if no record is given
        # HINT: template_values is for e-mail only forms and not used if a record is given!
        template_values = dict(form_values, **self._get_session_information()) if form_values else None

        # Internal information e-mail
        if form.information_email_template:
            self.send_mail(template=form.information_email_template, record=record, template_values=template_values,
                           partner_receipient_ids=form.information_email_receipients.ids)

        # Confirmation e-mail for the form user
        if form.confirmation_email_template:
            email_field = [f for f in form.field_ids if f.confirmation_email][0]
            email_field_name = email_field.field_id.name
            email_to = record[email_field_name] if record else template_values.get(email_field_name)
            self.send_mail(template=form.confirmation_email_template, record=record, template_values=template_values,
                           email_to=email_to)

    def post_messages(self, form, form_field_data, record):
        for f in form.field_ids:
            if f.type == 'mail_message':
                f_name = f.name
                comment = form_field_data.get(f_name, None)
                if comment:
                    # HINT: get_external_id() will return a dict like {id: xml-id-name}
                    subtype_xml_id_name = f.mail_message_subtype.get_external_id().get(f.mail_message_subtype.id)
                    user = request.env.user
                    message_txt = ("%s\n"
                                   "\n"
                                   "---\n"
                                   "%s, user: %s, login: %s,\n"
                                   "%s, form-%s, field-%s, label: %s\n" % (
                                       comment,
                                       user.partner_id.name, user.id, user.login,
                                       f.mail_message_subtype.name, form.id, f.id, f.label))
                    record.sudo().with_context(mail_post_autofollow=False).message_post(
                        body=message_txt,
                        type='comment',
                        subtype=subtype_xml_id_name,
                        content_subtype="plaintext")

    def is_logged_in(self):
        # The default website user does not count as a logged in user
        default_website_user = request.env.ref('base.public_user', raise_if_not_found=True)
        if not request.env.user or (default_website_user and default_website_user.id == request.env.user.id):
            return False
        return True

    def _redirect_after_form_submit(self, form, record, forced_redirect_url='', forced_redirect_target=''):
        redirect_target = ''

        # Compute the redirect url
        if forced_redirect_url:
            redirect_url = forced_redirect_url
            redirect_target = forced_redirect_target
        else:
            # Thank you page
            redirect_url = "/fso/form/thanks/" + str(form.id)

            # Logged in
            if form.redirect_url_if_logged_in and request.website.user_id.id != request.uid:
                redirect_url = form.redirect_url_if_logged_in
                redirect_target = form.redirect_url_if_logged_in_target or ""

            # Not logged in
            elif form.redirect_url:
                redirect_url = form.redirect_url
                redirect_target = form.redirect_url_target or ""

        # redirect_target
        # HINT: If redirect_target is set we need to redirect by java script therefore we render a page with js in it
        if redirect_target in ['_parent', '_blank']:
            return http.request.render('fso_forms.thank_you_redirect',
                                       {'redirect_url': redirect_url,
                                        'redirect_target': redirect_target})
        # Regular redirect
        else:
            return request.redirect(redirect_url)

    @http.route(['/fso/form/<int:form_id>'], methods=['POST', 'GET'], type='http', auth="public", website=True)
    def fso_form(self, form_id=None, render_form_only=False, lazy=True, **kwargs):
        form_id = int(form_id)
        form = request.env['fson.form'].sudo().browse([form_id])
        if len(form) != 1:
            _logger.error('Form with id %s not found! Redirecting to startpage!' % str(form_id))
            return request.redirect("/")

        # Initialize the frontend message lists
        errors = list()
        warnings = list()
        messages = list()
        form_field_errors = dict()

        # UGLY HACK TO AVOID POST SUBMITS OF A FORM AFTER AN ODOO SERVICE RESTART WITHOUT AN ENV USER
        # HINT: I guess this should be done globally by odoo and not just for fso_forms?!?
        if request and hasattr(request, 'env') and hasattr(request, 'uid') and (request.uid and not request.env.uid):
            if hasattr(request, 'httprequest') and request.httprequest.url:
                redirect_url = request.httprequest.url
            else:
                redirect_url = '/fso/form/%s' % form.id
            _logger.error("NO USER IN request.env.uid! REDIRECTING TO: %s" % redirect_url)
            return request.redirect(redirect_url)

        # Login handling
        # --------------
        # TODO: This seems to be a bad solution because it may loose all kwargs for the fso_form
        #       Check that the kwargs are already "stored" by url attribs in request.httprequest.url
        if form.login_required and not self.is_logged_in():
            _logger.info("FSO_Form %s render token login form!" % form.id)
            if form.show_token_login_form:
                tlf_kwargs = deepcopy(kwargs)
                tlf_kwargs.pop('token_data_submission_url', None)
                redirect_url = tlf_kwargs.pop('redirect_url_after_token_login', request.httprequest.url)
                assert redirect_url.startswith(request.httprequest.host_url), 'Only local redirects allowed!'
                tlf_kwargs.pop('tlf_record', None)
                token_login_form = AuthPartnerForm().web_login_fs_ptoken(
                    token_data_submission_url=request.httprequest.url,
                    redirect_url_after_token_login=redirect_url,
                    tlf_record=form,
                    # tlf_top_snippets=form.tlf_top_snippets,
                    # tlf_headline=form.tlf_headline,
                    # tlf_label=form.tlf_label,
                    # tlf_submit_button=form.tlf_submit_button,
                    # tlf_logout_button=form.tlf_logout_button,
                    # tlf_bottom_snippets=form.tlf_bottom_snippets,
                    **tlf_kwargs
                )
                return token_login_form
            else:
                # TODO: Change template to render just this message in the errors box but with full website template
                return "Login required!"

        # Get the form and session related record
        # ---------------------------------------
        # HINT: This will either return a single record or an empty recordset (= form.model_id.model object)
        record = self.get_fso_form_record(form)
        if record:
            _logger.info("Record %s,%s was found for form %s for request.uid %s and request.env.uid %s"
                         "" % (record._name, record.id, form.id, request.uid, request.env.uid if request.env else ''))
            if not record._uid:
                _logger.error('RECORD WAS FOUND FOR FORM %s BUT HAS NO USER IN THE ENV! record._uid: %s'
                              '' % (form.id, record._uid))

        # ----------------------
        # HANDLE FORM SUBMISSION
        # ----------------------
        if kwargs and request.httprequest.method == 'POST':
            logging.info("FSO FORM SUBMIT: %s" % kwargs)

            # Validate Fields before we create or update a record
            form_field_errors = self.validate_fields(form, field_data=kwargs)
            # Honey Pot Test returned True = SPAM submission
            if form_field_errors.get('honey_pot_test', None):
                _logger.warning("FSO FORM SUBMIT: SPAM submission detected by honeypot field! Form input was dismissed!"
                                " form_id %s, kwargs: %s" % (form_id, kwargs))
                return request.redirect("/fso/form/thanks/" + str(form.id))
            warnings += ['"%s": %s' % (kwargs.get(f, f), msg) for f, msg in form_field_errors.iteritems()]

            if not warnings and not errors:
                # Only send e-mails
                # -----------------------
                if form.email_only:
                    try:
                        form_values = self._prepare_kwargs_for_mail(form=form, **kwargs)
                        self.send_form_emails(form=form, form_values=form_values)
                    except Exception as e:
                        errors.append(_('Submission failed!\n\n%s' % repr(e)))
                        pass

                # Create or update a record
                # -------------------------
                else:
                    # HINT: User rights are handled by get_fso_form_record()
                    values = self._prepare_field_data(form=form, form_field_data=kwargs, record=record)
                    if values:
                        try:
                            # Create record
                            # -------------
                            if not record:
                                if form.create_as_user:
                                    record = record.sudo(form.create_as_user.id).create(values)
                                elif form.create_as_user_nologin and not self.is_logged_in():
                                    record = record.sudo(form.create_as_user_nologin.id).create(values)
                                else:
                                    # TODO: Check why we can't create that record as the public user with mail_thread
                                    #       enabled for the record model!!!
                                    record = record.create(values)
                                messages.append(_('Data was successfully submitted!'))

                            # Update record
                            # -------------
                            else:
                                if form.update_as_user:
                                    record.sudo(form.update_as_user.id).write(values)
                                elif form.update_as_user_nologin and not self.is_logged_in():
                                    record.sudo(form.update_as_user_nologin.id).write(values)
                                else:
                                    record.write(values)
                                messages.append(_('Data was successfully updated!'))
                            # Update the session data
                            # HINT: If clear_session_data_after_submit is set the form will be empty at the next
                            #       hit/load! This has no effect if a user is logged in and
                            #       'edit_existing_record_if_logged_in' is also set! In that case get_fso_form_record()
                            #       will overwrite the session data set here and set 'clear_session_data' to False
                            #       in the method get_fso_form_record() !
                            self.set_fso_form_session_data(form_id=form.id,
                                                           form_uid=request.uid,
                                                           form_record_id=record.id,
                                                           form_model_id=form.model_id.id,
                                                           clear_session_data=form.clear_session_data_after_submit)
                        except Exception as e:
                            errors.append(_('Submission failed!\n\n%s' % repr(e)))

                            # Rollback cursor of record with exception!
                            # ATTENTION: This is really important or unwanted records and side effects may be created!
                            # HINT: Since we catch the Exception that would lead to an rollback and a backend gui
                            #       message and never raise it we have to do this by our own!
                            # TODO: Check if this leaves open cursors behind or if odoo cleans them up after the
                            #       rollback!
                            record.env.cr.rollback()

                            _logger.error("FsoForms Exception: %s" % repr(e))
                            pass

                        # ADDITIONAL TASKS
                        # ----------------
                        if record and not errors:

                            # Send emails
                            # -----------
                            # WARNING: If the the e-mail(s) could not be send we continue without raising the exception!
                            try:
                                self.send_form_emails(form=form, record=record)
                            except Exception as e:
                                _logger.error("fso_forms: Could not send e-mail(s)!\n%s" % repr(e))
                                pass

                            # Post comments (chatter)
                            # -----------------------
                            # WARNING: If the comments can not be created we continue without raising the exception!
                            try:
                                self.post_messages(form=form, form_field_data=kwargs, record=record)
                            except Exception as e:
                                _logger.error("fso_forms: Could not post messages!\n%s" % repr(e))
                                pass

                # Redirect to Thank you Page if set by the form or to the url selected
                # HINT: The Thank You Page the only page where you could edit the data again if not logged in
                #       by pressing the edit button
                if form.redirect_after_submit and not warnings and not errors:
                    return self._redirect_after_form_submit(form, record)

        # FINALLY RENDER THE FORM
        # -----------------------
        template_kwargs = {'kwargs': self._prepare_kwargs_for_form(form, record=record, **kwargs),
                           'render_form_only': render_form_only,
                           # Form record
                           'form': form,
                           # Set error css-classes to the field-form-groups
                           'form_field_errors': form_field_errors,
                           # Record created by the form
                           'record': record,
                           # Messages
                           'errors': errors,
                           'warnings': warnings,
                           'messages': messages,
                           # To export the ast lib
                           'ast': ast,
                           }
        return http.request.render('fso_forms.form', template_kwargs, lazy=lazy)

    @http.route(['/fso/form/thanks/<int:form_id>'], methods=['POST', 'GET'], type='http', auth="public", website=True)
    def fso_form_thanks(self, form_id=False, **kwargs):
        form_id = int(form_id)

        # Get Form
        # ATTENTION: Always use a list for browse()
        form = request.env['fson.form'].browse([form_id])
        if not form:
            _logger.error('Form with id %s not found! Redirecting to startpage!' % str(form_id))
            return request.redirect("/")

        # FORM SUBMIT FOR EDIT BUTTON
        # TODO: Right now this is a simple get request from an <a></a>
        #       Maybe we should add a UUID im the session data and submit a form by the edit button with a hidden input
        #       field containing the guid - it may be safer than just depend on the form data in the session - but im
        #       not sure about that since an attacker that will call /fso/form/[n]?edit_form_data=True would still have
        #       no form data in the memory on the server for its session.
        if kwargs.get('edit_form_data', False):
            # Set 'clear_session_data' to False before we redirect to the form again
            form_sdata = self.get_fso_form_session_data(form, check_clear_session_data=False)
            if form_sdata:
                self.set_fso_form_session_data(form.id,
                                               form_sdata['form_uid'],
                                               form_sdata['form_record_id'],
                                               form_sdata['form_model_id'],
                                               clear_session_data=False)
            redirect_url = "/fso/form/"+str(form.id)
            if not form.email_only and form.thank_you_page_edit_redirect:
                redirect_url = form.thank_you_page_edit_redirect
            return request.redirect(redirect_url)

        # Render the thanks template
        return http.request.render('fso_forms.thanks',
                                   {'kwargs': kwargs,
                                    # form
                                    'form': form})
