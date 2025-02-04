# -*- coding: utf-'8' "-*-"

from hashlib import sha1
import logging
from lxml import etree, objectify
from pprint import pformat
import time
from urllib import urlencode
import urllib2
import urlparse

from openerp.addons.payment.models.payment_acquirer import ValidationError
from openerp.addons.payment_ogonedadi.controllers.main import OgonedadiController
from openerp.addons.payment_ogonedadi.data import ogonedadi
from openerp.osv import osv, fields
from openerp.tools import float_round
from openerp.tools.float_utils import float_compare, float_repr
from openerp import api

_logger = logging.getLogger(__name__)


class PaymentAcquirerOgonedadi(osv.Model):
    _inherit = 'payment.acquirer'

    def _get_ogonedadi_urls(self, cr, uid, environment, context=None):
        """ Ogonedadi URLS:

         - standard order: POST address for form-based

        @TDETODO: complete me
        """
        return {
            'ogonedadi_standard_order_url': 'https://secure.ogone.com/ncol/%s/orderstandard_utf8.asp' % (environment,),
            'ogonedadi_direct_order_url': 'https://secure.ogone.com/ncol/%s/orderdirect_utf8.asp' % (environment,),
            'ogonedadi_direct_query_url': 'https://secure.ogone.com/ncol/%s/querydirect_utf8.asp' % (environment,),
            'ogonedadi_afu_agree_url': 'https://secure.ogone.com/ncol/%s/AFU_agree.asp' % (environment,),
        }

    def _get_providers(self, cr, uid, context=None):
        providers = super(PaymentAcquirerOgonedadi, self)._get_providers(cr, uid, context=context)
        providers.append(['ogonedadi', 'Ogonedadi'])
        return providers

    _columns = {
        'ogonedadi_pspid': fields.char('PSPID', required_if_provider='ogonedadi'),
        'ogonedadi_userid': fields.char('API User ID', required_if_provider='ogonedadi'),
        'ogonedadi_password': fields.char('API User Password', required_if_provider='ogonedadi'),
        'ogonedadi_shakey_in': fields.char('SHA Key IN', required_if_provider='ogonedadi'),
        'ogonedadi_shakey_out': fields.char('SHA Key OUT', required_if_provider='ogonedadi'),
        # By Mike:
        'ogonedadi_pm': fields.char('Payment Method e.g. Credit Card (PM)'),
        'ogonedadi_brand': fields.char('Payment Method Type e.g. VISA (BRAND)'),
        'ogonedadi_tp': fields.char('Payment Form Template URL (TP)')
    }

    @api.multi
    def name_get(self):
        return [
            (record.id, "%s (%s)" % (record.name, record.ogonedadi_pspid) if record.ogonedadi_pspid else record.name)
            for record in self
        ]

    def _ogonedadi_generate_shasign(self, acquirer, inout, values):
        """ Generate the shasign for incoming or outgoing communications.

        :param browse acquirer: the payment.acquirer browse record. It should
                                have a shakey in shaky out
        :param string inout: 'in' (openerp contacting ogone) or 'out' (ogone
                             contacting openerp). In this last case only some
                             fields should be contained (see e-Commerce basic)
        :param dict values: transaction values

        :return string: shasign
        """
        assert inout in ('in', 'out')
        assert acquirer.provider == 'ogonedadi'
        key = getattr(acquirer, 'ogonedadi_shakey_' + inout)

        def filter_key(key):
            if inout == 'in':
                return True
            else:
                # SHA-OUT keys
                # source https://viveum.v-psp.com/Ncol/Viveum_e-Com-BAS_EN.pdf
                keys = [
                    'AAVADDRESS',
                    'AAVCHECK',
                    'AAVMAIL',
                    'AAVNAME',
                    'AAVPHONE',
                    'AAVZIP',
                    'ACCEPTANCE',
                    'ALIAS',
                    'AMOUNT',
                    'BIC',
                    'BIN',
                    'BRAND',
                    'CARDNO',
                    'CCCTY',
                    'CN',
                    'COMPLUS',
                    'CREATION_STATUS',
                    'CURRENCY',
                    'CVCCHECK',
                    'DCC_COMMPERCENTAGE',
                    'DCC_CONVAMOUNT',
                    'DCC_CONVCCY',
                    'DCC_EXCHRATE',
                    'DCC_EXCHRATESOURCE',
                    'DCC_EXCHRATETS',
                    'DCC_INDICATOR',
                    'DCC_MARGINPERCENTAGE',
                    'DCC_VALIDHOURS',
                    'DIGESTCARDNO',
                    'ECI',
                    'ED',
                    'ENCCARDNO',
                    'FXAMOUNT',
                    'FXCURRENCY',
                    'IBAN',
                    'IP',
                    'IPCTY',
                    'NBREMAILUSAGE',
                    'NBRIPUSAGE',
                    'NBRIPUSAGE_ALLTX',
                    'NBRUSAGE',
                    'NCERROR',
                    'NCERRORCARDNO',
                    'NCERRORCN',
                    'NCERRORCVC',
                    'NCERRORED',
                    'ORDERID',
                    'PAYID',
                    'PM',
                    'PMTYPE',
                    'SCO_CATEGORY',
                    'SCORING',
                    'STATUS',
                    'SUBBRAND',
                    'SUBSCRIPTION_ID',
                    'TRXDATE',
                    'VC'
                ]
                return key.upper() in keys

        items = sorted((k.upper(), v) for k, v in values.items())
        sign = ''.join('%s=%s%s' % (k, v, key) for k, v in items if v and filter_key(k))
        sign = sign.encode("utf-8")
        shasign = sha1(sign).hexdigest()
        return shasign

    def ogonedadi_form_generate_values(self, cr, uid, id, partner_values, tx_values, context=None):
        base_url = self.pool['ir.config_parameter'].get_param(cr, uid, 'web.base.url')
        acquirer = self.browse(cr, uid, id, context=context)

        # Override base URL with acquirer base_url_for_form_feedback
        if acquirer.base_url_for_form_feedback:
            base_url = acquirer.base_url_for_form_feedback

        ogonedadi_tx_values = dict(tx_values)
        # AMOUNT calculation changed! see: https://github.com/odoo/odoo/commit/7c2521a79bc9443adab1bc63007e70661a8c22b7
        temp_ogonedadi_tx_values = {
            'PSPID': acquirer.ogonedadi_pspid,
            'ORDERID': tx_values['reference'],
            'AMOUNT': float_repr(float_round(tx_values['amount'], 2) * 100, 0),
            'CURRENCY': tx_values['currency'] and tx_values['currency'].name or '',
            'LANGUAGE': partner_values['lang'],
            'CN': partner_values['name'],
            'EMAIL': partner_values['email'],
            'OWNERZIP': partner_values['zip'],
            'OWNERADDRESS': partner_values['address'],
            'OWNERTOWN': partner_values['city'],
            'OWNERCTY': partner_values['country'] and partner_values['country'].code or '',
            'OWNERTELNO': partner_values['phone'],
            'ACCEPTURL': '%s' % urlparse.urljoin(base_url, OgonedadiController._accept_url),
            'DECLINEURL': '%s' % urlparse.urljoin(base_url, OgonedadiController._decline_url),
            'EXCEPTIONURL': '%s' % urlparse.urljoin(base_url, OgonedadiController._exception_url),
            'CANCELURL': '%s' % urlparse.urljoin(base_url, OgonedadiController._cancel_url),
        }
        if ogonedadi_tx_values.get('return_url'):
            temp_ogonedadi_tx_values['PARAMPLUS'] = 'return_url=%s' % ogonedadi_tx_values.pop('return_url')

        # By Mike: extra values to submit to ogone if set in payment.acquirer form
        if acquirer.ogonedadi_pm:
            temp_ogonedadi_tx_values['PM'] = acquirer.ogonedadi_pm
        if acquirer.ogonedadi_brand:
            temp_ogonedadi_tx_values['BRAND'] = acquirer.ogonedadi_brand
        if acquirer.ogonedadi_tp:
            temp_ogonedadi_tx_values['TP'] = acquirer.ogonedadi_tp

        shasign = self._ogonedadi_generate_shasign(acquirer, 'in', temp_ogonedadi_tx_values)
        temp_ogonedadi_tx_values['SHASIGN'] = shasign

        ogonedadi_tx_values.update(temp_ogonedadi_tx_values)
        _logger.warning("ogonedadi_form_generate_values(): ogonedadi_tx_values: %s" % ogonedadi_tx_values)
        return partner_values, ogonedadi_tx_values

    def ogonedadi_get_form_action_url(self, cr, uid, id, context=None):
        acquirer = self.browse(cr, uid, id, context=context)
        return self._get_ogonedadi_urls(cr, uid, acquirer.environment, context=context)['ogonedadi_standard_order_url']


class PaymentTxOgonedadi(osv.Model):
    _inherit = 'payment.transaction'
    # ogone status
    _ogonedadi_valid_tx_status = [5, 9]
    _ogonedadi_wait_tx_status = [41, 50, 51, 52, 55, 56, 91, 92, 99]
    _ogonedadi_pending_tx_status = [46]  # 3DS HTML response
    _ogonedadi_cancel_tx_status = [1, 2]

    _columns = {
        'ogonedadi_3ds': fields.boolean('3DS Activated'),
        'ogonedadi_3ds_html': fields.html('3DS HTML'),
        'ogonedadi_complus': fields.char('Complus'),
        'ogonedadi_payid': fields.char('PayID', help='Payment ID, generated by Ogone'),
        # by Mike
        'ogonedadi_orderid': fields.char('Order ID from odoo (orderID)'),
        'ogonedadi_eci': fields.char('Electronic Commerce Indicator (ECI)'),
        'ogonedadi_pm': fields.char('Payment Method (PM)'),
        'ogonedadi_brand': fields.char('Brand (BRAND)'),
        'ogonedadi_cardno': fields.char('Card Number (CARDNO)'),
        'ogonedadi_cn': fields.char('Common Name (CN)'),
        'ogonedadi_amount': fields.char('Amount (amount)'),
        'ogonedadi_currency': fields.char('Amount (currency)'),
        'ogonedadi_ed': fields.char('Expiry Date (ED)'),
        'ogonedadi_status': fields.char('Status (STATUS)'),
        'ogonedadi_trxdate': fields.char('Transaction Date (TRXDATE)'),
        'ogonedadi_ncerror': fields.char('Error Code (NCERROR)'),
        'ogonedadi_ncerrorplus': fields.char('Error Description (NCERRORPLUS)'),
        'ogonedadi_ip': fields.char('IP Address (IP)'),
        'ogonedadi_return_url': fields.char('Return URL (return_url)'),

    }

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    def _ogonedadi_form_get_tx_from_data(self, cr, uid, data, context=None):
        """ Given a data dict coming from ogone, verify it and find the related
        transaction record. """
        reference, pay_id, shasign = data.get('orderID'), data.get('PAYID'), data.get('SHASIGN')
        if not reference or not pay_id or not shasign:
            error_msg = 'Ogonedadi: received data with missing reference (%s) or pay_id (%s) or shashign (%s)' % (
                reference, pay_id, shasign)
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use paytid ?
        tx_ids = self.search(cr, uid, [('reference', '=', reference)], context=context)
        if not tx_ids or len(tx_ids) > 1:
            error_msg = 'Ogonedadi: received data for reference %s' % (reference)
            if not tx_ids:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        tx = self.pool['payment.transaction'].browse(cr, uid, tx_ids[0], context=context)

        # verify shasign
        shasign_check = self.pool['payment.acquirer']._ogonedadi_generate_shasign(tx.acquirer_id, 'out', data)
        if shasign_check.upper() != shasign.upper():
            error_msg = 'Ogonedadi: invalid shasign, received %s, computed %s, for data %s' % (shasign, shasign_check, data)
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        return tx

    def _ogonedadi_form_get_invalid_parameters(self, cr, uid, tx, data, context=None):
        invalid_parameters = []

        # TODO: txn_id: should be false at draft, set afterwards, and verified with txn details
        if tx.acquirer_reference and data.get('PAYID') != tx.acquirer_reference:
            invalid_parameters.append(('PAYID', data.get('PAYID'), tx.acquirer_reference))
        # check what is bought
        if float_compare(float(data.get('amount', '0.0')), tx.amount, 2) != 0:
            invalid_parameters.append(('amount', data.get('amount'), '%.2f' % tx.amount))
        if data.get('currency') != tx.currency_id.name:
            invalid_parameters.append(('currency', data.get('currency'), tx.currency_id.name))

        return invalid_parameters

    def _ogonedadi_form_validate(self, cr, uid, tx, data, context=None):
        # ToDo by Mike: Use a caseinsensitive Dict for keys e.g.: https://gist.github.com/babakness/3901174
        #               that is already set in class OgonedadiController(http.Controller) to pass the
        #               caseinsensitive dict to all methods. Not urgent but would be nice.
        # Simple Solution for now > Upper dict-keys:
        data_upper = dict((k.upper(), v) for k, v in data.iteritems())

        # By Mike: Check coming state from ogone and if state is the same than before do nothing
        if tx.ogonedadi_status == data_upper.get('STATUS'):
            _logger.warning('Ogonedadi Update of Payment Transaction %s not processed because state did not change!'
                            % tx.reference)
            return True

        # By Mike: Post the data as chatter message
        # (at this point in the process we know that we only post non duplicated valid update requests from ogone)
        ogonedadi_post_data = 'Received data from ogone: \n\n%s' % data
        self.message_post(cr, uid, tx.id, body=ogonedadi_post_data, content_subtype='plaintext', type='comment')

        # By Mike: read all keys with get and use datetime.now() for date_validate
        tx_write_data = {
            'acquirer_reference': data_upper.get('PAYID'),
            # 'date_validate': time.strptime(data_upper.get('TRXDATE'), "%m/%d/%y"),
            'date_validate': fields.datetime.now(),
            'ogonedadi_payid': data_upper.get('PAYID'),
            'ogonedadi_orderid': data_upper.get('ORDERID'),
            'ogonedadi_eci': data_upper.get('ECI'),
            'ogonedadi_pm': data_upper.get('PM'),
            'ogonedadi_brand': data_upper.get('BRAND'),
            'ogonedadi_cardno': data_upper.get('CARDNO'),
            'ogonedadi_cn': data_upper.get('CN'),
            'ogonedadi_amount': data_upper.get('AMOUNT'),
            'ogonedadi_currency': data_upper.get('CURRENCY'),
            'ogonedadi_ed': data_upper.get('ED'),
            'ogonedadi_status': data_upper.get('STATUS'),
            'ogonedadi_trxdate': data_upper.get('TRXDATE'),
            'ogonedadi_ncerror': data_upper.get('NCERROR'),
            'ogonedadi_ncerrorplus': data_upper.get('NCERRORPLUS'),
            'ogonedadi_ip': data_upper.get('IP'),
            'ogonedadi_return_url': data_upper.get('RETURN_URL')
        }

        # Update the Transaction
        status = int(data.get('STATUS', '0'))
        if status in self._ogonedadi_valid_tx_status:
            tx_write_data['state'] = 'done'
            res = tx.write(tx_write_data)
        elif status in self._ogonedadi_cancel_tx_status:
            tx_write_data['state'] = 'cancel'
            res = tx.write(tx_write_data)
        elif status in self._ogonedadi_pending_tx_status:
            tx_write_data['state'] = 'pending'
            res = tx.write(tx_write_data)
        else:
            error = 'Ogonedadi: feedback error: %(error_str)s\n\n%(error_code)s: %(error_msg)s' % {
                'error_str': data_upper.get('NCERROR'),
                'error_code': data_upper.get('NCERRORPLUS'),
                'error_msg': data_upper.OGONE_ERROR_MAP.get(data.get('NCERRORPLUS')),
            }
            _logger.info(error)
            tx_write_data['state'] = 'error'
            tx_write_data['state_message'] = error
            res = tx.write(tx_write_data)

        # ATTENTION: Link the last payment transaction where we got an answer to the sales order field 'payment_tx_id'
        #            This is needed because sometimes we get concurrent writes when the pay now button is pressed
        #            multiple times which leads to multiply payment transaction for the same sale order in no
        #            particular order.
        if tx and tx.sale_order_id and tx.sale_order_id.payment_tx_id:
            if tx.id != tx.sale_order_id.payment_tx_id.id:
                _logger.error("Payment transaction (ID %s) with feedback-from-payment-provider is not currently "
                              "linked to the sales order field 'payment_tx_id' on linked sale order with id %s! "
                              "Try to change sale_order.payment_tx_id.id from %s to %s!"
                              "" % (tx.id, tx.sale_order_id.id, tx.sale_order_id.payment_tx_id.id, tx.id))
                try:
                    tx.sale_order_id.write({'payment_tx_id': tx.id})
                except Exception as e:
                    _logger.error("Could not change the payment_tx_id to %s for sale order with id %s!\n%s"
                                  "" % (tx.id, tx.sale_order_id.id, repr(e)))
                    pass

        return res

    # --------------------------------------------------
    # S2S RELATED METHODS
    # --------------------------------------------------

    def ogonedadi_s2s_create_alias(self, cr, uid, id, values, context=None):
        """ Create an alias at Ogone via batch.

         .. versionadded:: pre-v8 saas-3
         .. warning::

            Experimental code. You should not use it before OpenERP v8 official
            release.
        """
        tx = self.browse(cr, uid, id, context=context)
        assert tx.type == 'server2server', 'Calling s2s dedicated method for a %s acquirer' % tx.type
        alias = 'OPENERP-%d-%d' % (tx.partner_id.id, tx.id)

        expiry_date = '%s%s' % (values['expiry_date_mm'], values['expiry_date_yy'][2:])
        line = 'ADDALIAS;%(alias)s;%(holder_name)s;%(number)s;%(expiry_date)s;%(brand)s;%(pspid)s'
        line = line % dict(values, alias=alias, expiry_date=expiry_date, pspid=tx.acquirer_id.ogonedadi_pspid)

        tx_data = {
            'FILE_REFERENCE': 'OPENERP-NEW-ALIAS-%s' % time.time(),  # something unique,
            'TRANSACTION_CODE': 'ATR',
            'OPERATION': 'SAL',
            'NB_PAYMENTS': 1,  # even if we do not actually have any payment, ogone want it to not be 0
            'FILE': line,
            'REPLY_TYPE': 'XML',
            'PSPID': tx.acquirer_id.ogonedadi_pspid,
            'USERID': tx.acquirer_id.ogonedadi_userid,
            'PSWD': tx.acquirer_id.ogonedadi_password,
            'PROCESS_MODE': 'CHECKANDPROCESS',
        }

        # TODO: fix URL computation
        request = urllib2.Request(tx.acquirer_id.ogonedadi_afu_agree_url, urlencode(tx_data))
        result = urllib2.urlopen(request).read()

        try:
            tree = objectify.fromstring(result)
        except etree.XMLSyntaxError:
            _logger.exception('Invalid xml response from ogone')
            return None

        error_code = error_str = None
        if hasattr(tree, 'PARAMS_ERROR'):
            error_code = tree.NCERROR.text
            error_str = 'PARAMS ERROR: %s' % (tree.PARAMS_ERROR.text or '',)
        else:
            node = tree.FORMAT_CHECK
            error_node = getattr(node, 'FORMAT_CHECK_ERROR', None)
            if error_node is not None:
                error_code = error_node.NCERROR.text
                error_str = 'CHECK ERROR: %s' % (error_node.ERROR.text or '',)

        if error_code:
            error_msg = ogonedadi.OGONE_ERROR_MAP.get(error_code)
            error = '%s\n\n%s: %s' % (error_str, error_code, error_msg)
            _logger.error(error)
            raise Exception(error)  # TODO specific exception

        tx.write({'partner_reference': alias})
        return True

    def ogonedadi_s2s_generate_values(self, cr, uid, id, custom_values, context=None):
        """ Generate valid Ogone values for a s2s tx.

         .. versionadded:: pre-v8 saas-3
         .. warning::

            Experimental code. You should not use it before OpenERP v8 official
            release.
        """
        tx = self.browse(cr, uid, id, context=context)
        tx_data = {
            'PSPID': tx.acquirer_id.ogonedadi_pspid,
            'USERID': tx.acquirer_id.ogonedadi_userid,
            'PSWD': tx.acquirer_id.ogonedadi_password,
            'OrderID': tx.reference,
            'amount': '%d' % int(float_round(tx.amount, 2) * 100),  # tde check amount or str * 100 ?
            'CURRENCY': tx.currency_id.name,
            'LANGUAGE': tx.partner_lang,
            'OPERATION': 'SAL',
            'ECI': 2,  # Recurring (from MOTO)
            'ALIAS': tx.partner_reference,
            'RTIMEOUT': 30,
        }
        if custom_values.get('ogonedadi_cvc'):
            tx_data['CVC'] = custom_values.get('ogonedadi_cvc')
        if custom_values.pop('ogonedadi_3ds', None):
            tx_data.update({
                'FLAG3D': 'Y',  # YEAH!!
            })
            if custom_values.get('ogonedadi_complus'):
                tx_data['COMPLUS'] = custom_values.get('ogonedadi_complus')
            if custom_values.get('ogonedadi_accept_url'):
                pass

        shasign = self.pool['payment.acquirer']._ogonedadi_generate_shasign(tx.acquirer_id, 'in', tx_data)
        tx_data['SHASIGN'] = shasign
        return tx_data

    def ogonedadi_s2s_feedback(self, cr, uid, data, context=None):
        """
         .. versionadded:: pre-v8 saas-3
         .. warning::

            Experimental code. You should not use it before OpenERP v8 official
            release.
        """
        pass

    def ogonedadi_s2s_execute(self, cr, uid, id, values, context=None):
        """
         .. versionadded:: pre-v8 saas-3
         .. warning::

            Experimental code. You should not use it before OpenERP v8 official
            release.
        """
        tx = self.browse(cr, uid, id, context=context)

        tx_data = self.ogonedadi_s2s_generate_values(cr, uid, id, values, context=context)
        _logger.info('Generated Ogone s2s data %s', pformat(tx_data))  # debug

        request = urllib2.Request(tx.acquirer_id.ogonedadi_direct_order_url, urlencode(tx_data))
        result = urllib2.urlopen(request).read()
        _logger.info('Contacted Ogone direct order; result %s', result)  # debug

        tree = objectify.fromstring(result)
        payid = tree.get('PAYID')

        query_direct_data = dict(
            PSPID=tx.acquirer_id.ogonedadi_pspid,
            USERID=tx.acquirer_id.ogonedadi_userid,
            PSWD=tx.acquirer_id.ogonedadi_password,
            ID=payid,
        )
        query_direct_url = 'https://secure.ogone.com/ncol/%s/querydirect.asp' % (tx.acquirer_id.environment,)

        tries = 2
        tx_done = False
        tx_status = False
        while not tx_done or tries > 0:
            try:
                tree = objectify.fromstring(result)
            except etree.XMLSyntaxError:
                # invalid response from ogone
                _logger.exception('Invalid xml response from ogone')
                raise

            # see https://secure.ogone.com/ncol/paymentinfos1.asp
            VALID_TX = [5, 9]
            WAIT_TX = [41, 50, 51, 52, 55, 56, 91, 92, 99]
            PENDING_TX = [46]  # 3DS HTML response
            # other status are errors...

            status = tree.get('STATUS')
            if status == '':
                status = None
            else:
                status = int(status)

            if status in VALID_TX:
                tx_status = True
                tx_done = True

            elif status in PENDING_TX:
                html = str(tree.HTML_ANSWER)
                tx_data.update(ogonedadi_3ds_html=html.decode('base64'))
                tx_status = False
                tx_done = True

            elif status in WAIT_TX:
                time.sleep(1500)

                request = urllib2.Request(query_direct_url, urlencode(query_direct_data))
                result = urllib2.urlopen(request).read()
                _logger.debug('Contacted Ogone query direct; result %s', result)

            else:
                error_code = tree.get('NCERROR')
                if not ogonedadi.retryable(error_code):
                    error_str = tree.get('NCERRORPLUS')
                    error_msg = ogonedadi.OGONE_ERROR_MAP.get(error_code)
                    error = 'ERROR: %s\n\n%s: %s' % (error_str, error_code, error_msg)
                    _logger.info(error)
                    raise Exception(error)

            tries = tries - 1

        if not tx_done and tries == 0:
            raise Exception('Cannot get transaction status...')

        return tx_status
