# -*- coding: utf-'8' "-*-"
from openerp import api, models, fields, SUPERUSER_ID
from openerp.exceptions import ValidationError
from openerp.tools.translate import _

import logging
logger = logging.getLogger(__name__)


class FSOConnectorSale(models.Model):
    """
    Connector for sale.order creation

    Additional Field Attributes:
    con = 'connector field group'   If set it means that this field can be set by the JSON controller (web route)
    con_update = True               If set the value of the field can be updated (in certain circumstances)
    """
    _name = "fson.connector.sale"

    # Disabled because this would need higher access rights for the fson_connector_sale user
    # _inherit = ['mail.thread']

    # HINT: Check get_fields_by_con_group()
    # ATTENTION: key 'all' holds a list with all fields!
    _fields_by_con_group = dict()

    # --------------------------
    # FIELDS
    # --------------------------

    # INTERNAL FIELDS
    # ---------------
    # Status and logs
    state = fields.Selection(selection=[('new', 'New'),
                                        ('update', 'Update'),
                                        ('done', 'Done'),
                                        ('error', 'Error')],
                             string="State", readonly=True, default='new')
    received_data_log = fields.Text(string="Received-Data Log",
                                    readonly=True)
    received_data_date = fields.Datetime(string="Data from controller at", readonly=True)
    error_details = fields.Text(string='Error Details', readonly=True)

    # Linking
    partner_id = fields.Many2one(comodel_name='res.partner', inverse_name="fson_connector_sale_partner_ids",
                                 readonly=True, index=True, ondelete='set null')
    employee_id = fields.Many2one(comodel_name='res.partner', inverse_name="fson_connector_sale_employee_ids",
                                  readonly=True, index=True, ondelete='set null')
    donee_id = fields.Many2one(comodel_name='res.partner', inverse_name="fson_connector_sale_donee_ids",
                               readonly=True, index=True, ondelete='set null')
    sale_order_id = fields.Many2one(comodel_name='sale.order', inverse_name="fson_connector_sale_ids",
                                    readonly=True, index=True, ondelete='set null')
    sale_order_line_id = fields.Many2one(comodel_name='sale.order.line', inverse_name="fson_connector_sale_ids",
                                         readonly=True, index=True, ondelete='set null')
    payment_transaction_id = fields.Many2one(comodel_name='payment.transaction', inverse_name="fson_connector_sale_ids",
                                             readonly=True, index=True, ondelete='set null')

    # PERSON / COMPANY TO INVOICE (res.partner)
    # -----------------------------------------
    # Contract-Participant: Private-Person or Legal-Company to Invoice
    # ATTENTION: The contract will be concluded with this Person or Company!
    firstname = fields.Char(string="Firstname", con='partner', help="Vorname (Can not be set if this is a company!)")
    lastname = fields.Char(string="Lastname", con='partner', required=True, help="Nachname")
    name_zwei = fields.Char(string="Name Zwei", con='partner', help="Name Zwei")
    phone = fields.Char(string="Phone", con='partner', help="Festnetznummer")
    mobile = fields.Char(string="Mobile Phone", con='partner', help="Mobilnummer")
    fax = fields.Char(string="Fax", con='partner', help="Fax")
    email = fields.Char(string="eMail", con='partner', help="E-Mail")
    street = fields.Char(string="Street", con='partner', help="Strasse")
    street_number_web = fields.Char(string="Street Number", con='partner', help="Hausnummer")
    city = fields.Char(string="City", con='partner', help="Ort")
    zip = fields.Char(string="ZIP", con='partner', help="Postleitzahl")
    country_code = fields.Char(string="Country Code", con='partner', help="Laendercode (z.B.: AT) ISO 3166 ALPHA-2")
    birthdate_web = fields.Date(string="Birthdate", con='partner', help="Geburtsdatum")
    newsletter_web = fields.Boolean(string="Newsletter", con='partner', help="Newsletter")
    is_company = fields.Boolean(string="Is a Company", con='partner', help="Ist eine Firma?")
    # TODO: Checkbox Spendenabsetzbarkeit OPT-OUT

    # EMPLOYEE / DOCUMENT RECEIVER: (OPTIONAL) (Zu Handen Adresse) (res.partner)
    # --------------------------------------------------------------------------
    # ATTENTION: Only allowed if is_company=True in the Invoice-Address above
    e_firstname = fields.Char(string="Firstname", con='employee', help="Vorname")
    e_lastname = fields.Char(string="Lastname", con='employee', help="Nachname")
    e_name_zwei = fields.Char(string="Name Zwei", con='employee', help="Name Zwei")
    e_phone = fields.Char(string="Phone", con='employee', help="Festnetznummer")
    e_mobile = fields.Char(string="Mobile Phone", con='employee', help="Mobilnummer")
    e_fax = fields.Char(string="Fax", con='employee', help="Fax")
    e_email = fields.Char(string="eMail", con='employee', help="E-Mail")
    e_street = fields.Char(string="Street", con='employee', help="Strasse")
    e_street_number_web = fields.Char(string="Street Number", con='employee', help="Hausnummer")
    e_city = fields.Char(string="City", con='employee', help="Ort")
    e_zip = fields.Char(string="ZIP", con='employee', help="Postleitzahl")
    e_country_code = fields.Char(string="Country Code", con='employee', help="Laendercode (z.B.: AT) ISO 3166 ALPHA-2")
    e_birthdate_web = fields.Date(string="Birthdate", con='employee', help="Geburtsdatum")
    e_newsletter_web = fields.Boolean(string="Newsletter", con='employee', help="Newsletter")
    # non res.partner fields
    e_send_to_this_address = fields.Boolean(string="Send Documents to this Address", con='employee',
                                            help="Zu Handen")

    # DONEE (OPTIONAL) (Beschenkter/Zuwendungsaempfenger) (res.partner)
    # -----------------------------------------------------------------
    d_firstname = fields.Char(string="Firstname", con='donee', help="Vorname")
    d_lastname = fields.Char(string="Lastname", con='donee', help="Nachname")
    d_name_zwei = fields.Char(string="Name Zwei", con='donee', help="Name Zwei")
    d_phone = fields.Char(string="Phone", con='donee', help="Festnetznummer")
    d_mobile = fields.Char(string="Mobile Phone", con='donee', help="Mobilnummer")
    d_fax = fields.Char(string="Fax", con='donee', help="Fax")
    d_email = fields.Char(string="eMail", con='donee', help="E-Mail")
    d_street = fields.Char(string="Street", con='donee', help="Strasse")
    d_street_number_web = fields.Char(string="Street Number", con='donee', help="Hausnummer")
    d_city = fields.Char(string="City", con='donee', help="Ort")
    d_zip = fields.Char(string="ZIP", con='donee', help="Postleitzahl")
    d_country_code = fields.Char(string="Country Code", con='donee', help="Laendercode (z.B.: AT) ISO 3166 ALPHA-2")
    d_birthdate_web = fields.Date(string="Birthdate", con='donee', help="Geburtsdatum")
    d_newsletter_web = fields.Boolean(string="Newsletter", con='donee', help="Newsletter")

    # ORDER: SALE ORDER (sale.order)
    # ------------------------------
    client_order_ref = fields.Char(string="Merchant Order ID", required=True, con='order',
                                   help="Unique identifier from the merchant for this sale order")
    # non sale.order fields
    followup_for_client_order_ref = fields.Char(string="Follow Up for Order with ID", con='order',
                                                help="'followup_for_client_order_ref' of the original order "
                                                     "that this is a followup for")
    currency = fields.Selection(string='Currency', required=True, con='order', selection=[('EUR', 'EUR')])

    # ORDERLINE: SALE ORDER LINE (sale.order.line)
    # --------------------------------------------
    # Check addons-own/website_sale_donate/models/website_sale_donate.py _cart_update() @line 235
    product_id = fields.Many2one(comodel_name='product.product', inverse_name="fson_connector_sale_ids",
                                 string="Product", required=True, con='orderline',
                                 index=True, ondelete='set null',
                                 help="ID (INTEGER) of the Product")
    price_donate = fields.Float(string="Donation per Unit", con='orderline',
                                help="Spendensumme pro Stueck")
    price_unit = fields.Float(string="Price per Unit", con='orderline',
                              help="Verkaufspreis pro Stueck")
    product_uom_qty = fields.Float(string="Quantity", con='orderline', required=True,
                                   help="Stueckzahl (Unit of Measure will be used as Unit of Sale also)")
    payment_interval_id = fields.Many2one(comodel_name='product.payment_interval',
                                          inverse_name="fson_connector_sale_ids",
                                          string="Payment Interval", con='orderline', required=True,
                                          index=True, ondelete='set null',
                                          help="ID (INTEGER) des Zahlungsintervals")
    # TODO: zgruppedetail_ids override ?!? oder nur vom produkt erlauben?

    # PAYMENT: PAYMENT TRANSACTION (payment.transaction)
    # --------------------------------------------------
    # Check odoo/addons/website_sale/controllers/main.py line 753
    #
    # Base Fields
    # -----------
    acquirer_id = fields.Many2one(comodel_name='payment.acquirer', inverse_name="fson_connector_sale_ids",
                                  string="Acquirer", con='tx', required=True, index=True, ondelete='set null')
    acquirer_reference = fields.Char(string="Acquirer Transaction Reference", con='tx, payment_consale')

    # Payment Method: payment_fsotransfer (Zahlschein)
    # ------------------------------------------------
    do_not_send_payment_forms = fields.Boolean(string="Do not send payment forms", con='tx, payment_fsotransfer')

    # Payment Method: payment_frst (Bankeinzug)
    # -----------------------------------------
    frst_iban = fields.Char(string="IBAN", con='tx, payment_frst')
    frst_bic = fields.Char(string="BIC (optional)", con='tx, payment_frst')

    # Payment Method: payment_consale (Webschnittstelle/Extern)
    # ---------------------------------------------------------------
    consale_state = fields.Selection(selection=[('draft', 'Draft'),
                                                ('pending', 'Pending'),
                                                ('done', 'Done'),
                                                ('error', 'Error'),
                                                ('cancel', 'Canceled')],
                                     string='State', con='tx, payment_consale')
    consale_transaction_date = fields.Date(string='Payment Transaction Date', con='tx, payment_consale')

    consale_provider_name = fields.Char(string='Payment Provider Name', con='tx, payment_consale',
                                        help='e.g.: Wirecard, Ogone, ApplePay, ...')
    consale_provider_status = fields.Char(string="Transaction Status Information", con='tx, payment_consale')

    consale_method = fields.Selection(selection=[('paypal', 'PayPal'),
                                                 ('directdebit', 'Direct Debit'),
                                                 ('applepay', 'Apple Pay'),
                                                 ('googlepay', 'Google Pay'),
                                                 ('banktransfer', 'Bank Transfer'),
                                                 ('creditcard', 'Credit Card'),
                                                 ('other', 'Other')],
                                      string='Payment Method', con='tx, payment_consale')
    consale_method_other = fields.Char(string='"Other" Payment Method Name', con='tx, payment_consale')
    consale_method_brand = fields.Char(string='Payment Method Brand', con='tx, payment_consale',
                                       help="e.g.: Visa, Mastercard, Apple, ...")

    consale_amount = fields.Float(string="Total Amount", con='tx, payment_consale')
    consale_currency = fields.Char(string='Currency', con='tx, payment_consale')

    consale_payid = fields.Char(string='PayID', con='tx, payment_consale')
    consale_eci = fields.Char(string='Electronic Commerce Indicatior', con='tx, payment_consale')
    consale_common_name = fields.Char(string='Common Name', con='tx, payment_consale')
    consale_error_code = fields.Char(string='Error Code', con='tx, payment_consale')
    consale_error_msg = fields.Char(string='Error Message', con='tx, payment_consale')
    consale_ip_address = fields.Char(string='Caller IP Address', con='tx, payment_consale')

    # ADDITIONAL INFORMATION
    # ----------------------
    origin = fields.Char(string="Origin", con='info', help="Herkunft/Quelle z.b.: Website, URL oder Kampagne")
    notes = fields.Text(string="Notes", con='info', help="Additional Information")

    # --------------------------
    # CONSTRAINTS AND VALIDATION
    # --------------------------
    # https://www.postgresql.org/docs/9.3/static/ddl-constraints.html
    _sql_constraints = [
        ('client_order_ref_unique', 'UNIQUE(client_order_ref)', "'client_order_ref' must be unique!"),
    ]

    # --------------
    # HELPER METHODS
    # --------------
    @api.model
    def get_fields_by_con_group(self, con_group=''):
        """
        Groups with all fields that can be updated by the web controller (externally)

        Special 'con_group' keys:
        'all': all fields that can be used by the web controller
        'update_allowed': all fields that can be updated after a record is already created/processed
        'update_denied': all fields that are not allowed

        :param con_group: Name of the con_group
        :return: returns a list of field names based on con_group
        """
        # HINT: use key 'all' to get all connector fields of all groups

        # Update class attribute if needed
        if not self._fields_by_con_group:
            cls = type(self)
            fbcg = dict()
            fbcg['all'] = list()
            fbcg['update_allowed'] = list()
            fbcg['update_denied'] = list()
            fbcg['all_provider_fields'] = list()
            for fname, field in self._fields.iteritems():
                if hasattr(field, "_attrs") and 'con' in field._attrs:

                    # 'all' Special key holding all connector fields
                    fbcg['all'].append(fname)

                    # 'update_allowed'
                    if hasattr(field, "_attrs") and field._attrs.get('con_update', False) is True:
                        fbcg['update_allowed'].append(fname)

                    # 'update_denied'
                    else:
                        fbcg['update_denied'].append(fname)

                    # 'con=' list of field-group-names separated by ','
                    con_group_names = tuple(n.strip() for n in field._attrs['con'].split(','))

                    # Append payment provider fields to con group 'all_provider_fields'
                    if 'tx' in con_group_names and len(con_group_names) >= 2:
                        if any(g.startswith('payment_') for g in con_group_names):
                            fbcg['all_provider_fields'].append(fname)

                    # Add field name to all field-groups in con_group_names
                    for con_group_name in con_group_names:
                        if con_group_name not in fbcg:
                            fbcg[con_group_name] = list()
                        fbcg[con_group_name].append(fname)

            # Store result in class attribute
            logger.info("Update class attribute '_fields_by_con_group': %s" % str(fbcg))
            cls._fields_by_con_group = fbcg

        # Return fields
        if not self._fields_by_con_group[con_group]:
            logger.warning('No fields found for con=%s' % con_group)
        return self._fields_by_con_group[con_group]

    @api.model
    def replace_country_code(self, vals):
        code = vals.pop('country_code', None)
        if code:
            country = self.env['res.country'].search([('code', '=', code)])
            assert len(country) == 1, "Country not found by code %s" % code
            vals['country_id'] = country.id
        return vals

    # ------------------
    # VALIDATION METHODS
    # ------------------
    @api.multi
    def validate_record(self):
        for r in self:
            logger.info("fson_connector_sale() Validate record %s" % r.id)

            # Validate Partner
            if r.is_company:
                if r.firstname or r.name_zwei or r.birthdate_web:
                    raise ValidationError("Fields 'firstname', 'name_zwei' and 'birthdate_web' are not allowed "
                                          "if 'is_company' is set!")

            # Validate Employee
            employee_fields = self.get_fields_by_con_group('employee')
            if any(r[fname] for fname in employee_fields):
                if not r.is_company:
                    raise ValidationError("Employee fields are only allowed if 'is_company' is set!"
                                          "These fields must be empty: %s" % employee_fields)
                if not r.e_lastname:
                    raise ValidationError("Field e_lastname must be set for the employee!")

            # Validate Donee
            donee_fields = self.get_fields_by_con_group('donee')
            if any(r[fname] for fname in donee_fields):
                if not r.d_lastname:
                    raise ValidationError("Field d_lastname must be set for the donee!")

            # Validate 'price_donate' and 'price_unit' are not used at the same time!
            if self.price_donate and self.price_unit:
                raise ValidationError(_("Field 'price_donate' and 'price_unit' is set! "
                                        "Use 'price_donate' for donations and 'price_unit' for regular products!"))

            # Validate Product
            if r.product_id:
                if not r.product_id.fson_connector_sale:
                    raise ValidationError("This product is not available for the connector!")
                if r.price_donate:
                    if not r.product_id.price_donate:
                        raise ValidationError("This product can not be used with 'price_donate'!")
                    if r.product_id.price_donate_min and r.price_donate < r.product_id.price_donate_min:
                        raise ValidationError("price_donate must be at least %s" % r.product_id.price_donate_min)
                if r.product_id.payment_interval_lines_ids:
                    interval_ids = tuple(l.payment_interval_id.id for l in r.product_id.payment_interval_lines_ids)
                    if r.payment_interval_id.id not in interval_ids:
                        raise ValidationError("This payment interval is not available for the product! "
                                              "Allowed payment interval ids for this product: %s" % str(interval_ids))

            # Validate payment transaction
            #       - if acquirer is enabled by 'fson_connector_sale'
            #       - if only correct fields are used (e.g. frst_iban)
            # TODO:
            #       - if all needed partner fields are set for this acquirer - maybe done by the _*_ methods form_feedb?
            #       - check if acquirer recurring-allowed-setting matches with payment interval
            if r.acquirer_id:
                # Check if provider is enabled
                if not r.acquirer_id.fson_connector_sale:
                    raise ValidationError("This acquirer (id %s) is not enabled for the connector!" % r.acquirer_id.id)
                # Check if the correct payment provider fields are used
                # ATTENTION: This will only work if all payment addons stick to the naming convention!
                all_provider_fields = self.get_fields_by_con_group('all_provider_fields')
                allowed_provider_fields = self.get_fields_by_con_group('payment_'+self.acquirer_id.provider)
                invalid_provider_fields = tuple(k for k in all_provider_fields
                                                if self[k] and k not in allowed_provider_fields)
                if invalid_provider_fields:
                    raise ValidationError('Fields are not valid for the current acquirer (ID %s): %s'
                                          '' % (r.acquirer_id.id, invalid_provider_fields))

    @api.multi
    def validate_update_data(self, vals=None):
        # Check for denied fields in vals
        # HINT: update_denied list all connector fields that can be set by the controller that are missing
        #       con_update = True
        update_denied = self.get_fields_by_con_group('update_denied')
        update_denied_in_vals = tuple(f for f in update_denied if f in vals)
        assert not update_denied_in_vals, "Update for fields %s is not allowed!" % update_denied_in_vals

        for r in self:
            logger.info("fson_connector_sale() Validate update values for record %s" % r.id)

            # TODO: Validate vals against current record data (mainly the state of the tx and so)

    # ------------------------------
    # CONVERSION AND LINKING METHODS
    # ------------------------------
    @api.multi
    def add_partner(self):
        assert self.ensure_one(), "Only one record allowed"
        logger.info("Create Partner/Company to invoice for %s" % self.id)

        # Get values
        partner_vals = {k: self[k] for k in self.get_fields_by_con_group('partner')}
        partner_vals = self.replace_country_code(partner_vals)

        # Create Partner
        partner = self.env['res.partner'].create(partner_vals)

        # Link Partner
        self.write({'partner_id': partner.id})

        return partner

    @api.multi
    def add_partner_employee(self):
        assert self.ensure_one(), "Only one record allowed"
        logger.info("Create Employee for %s" % self.id)

        # Get values
        employee_vals = {k.lstrip('e_'): self[k] for k in self.get_fields_by_con_group('employee') if self[k]}
        employee_vals = self.replace_country_code(employee_vals)
        employee_vals.pop('send_to_this_address', None)

        # Create Employee
        employee = False
        if employee_vals:
            assert self.partner_id.is_company, "Partner-to-invoice is missing or not a company!"
            assert employee_vals.get('lastname', False), "Field 'lastname' is missing for the employee"
            employee_vals['parent_id'] = self.partner_id
            employee = self.env['res.partner'].create(employee_vals)
        else:
            logger.info('No values for employee found. Skipping creating the employee.')

        # Link Employee
        if employee:
            self.write({'employee_id': employee.id})

        return employee

    @api.multi
    def add_partner_donee(self):
        assert self.ensure_one(), "Only one record allowed"
        logger.info("Create Donee for %s" % self.id)

        # Get values
        donee_vals = {k.lstrip('d_'): self[k] for k in self.get_fields_by_con_group('donee') if self[k]}
        donee_vals = self.replace_country_code(donee_vals)

        # Create Donee
        donee = False
        if donee_vals:
            assert self.partner_id, "Partner-to-invoice is missing!"
            assert donee_vals.get('lastname', False), "Field 'lastname' is missing for donee"
            donee = self.env['res.partner'].create(donee_vals)
        else:
            logger.info('No values for donee found. Skipping creating the donee.')

        # Link Donee
        if donee:
            self.write({'donee_id': donee.id})

        return donee

    @api.multi
    def add_sale_order(self):
        assert self.ensure_one(), "Only one record allowed"
        logger.info("Create Sale Order for %s" % self.id)

        # Make sure partner already exists
        assert self.partner_id, "Partner is missing!"

        # Get the sale order values
        vals = {k: self[k] for k in self.get_fields_by_con_group('order') if self[k]}
        assert vals, "No values found for the sale order!"

        # TODO: Handle currency
        vals.pop('currency', None)
        
        # Handle followup payments (followup_for_client_order_ref)
        fup = vals.pop('followup_for_client_order_ref', None)
        if fup:
            original_order = self.search([('followup_for_client_order_ref', '=', fup)])
            assert len(original_order) == 1, _("Original sale order not found or multiple sale order found for "
                                               "client_order_ref %s!" % fup)
            assert original_order.state == 'done', _("Original sale order state is %s but must be 'done'!"
                                                     "" % original_order.state)

        # ADD document receiver address / person
        if self.employee_id and self.employee_id.e_send_to_this_address:
            vals['partner_id'] = self.employee_id.id
        else:
            vals['partner_id'] = self.partner_id.id

        # Add invoice address / person
        vals['partner_invoice_id'] = self.partner_id.id

        # Create sale order
        sale_order = self.env['sale.order'].create(vals)

        # Link sale order
        self.write({'sale_order_id': sale_order.id})

        return sale_order

    @api.multi
    def add_sale_order_line(self,):
        assert self.ensure_one(), "Only one record allowed"
        logger.info("Create Sale Order Line for %s" % self.id)

        so = self.sale_order_id
        assert self.sale_order_id, "Sale Order is missing!"

        # Get sale order line values
        vals = {k: self[k].id if hasattr(self[k], 'id') else self[k]
                for k in self.get_fields_by_con_group('orderline')
                if self[k]}

        # Add sale order
        vals['order_id'] = so.id

        # Create sale order line
        so_line = self.env['sale.order.line'].create(vals)

        # Run _cart_update() to include 'price_donate' and 'payment_interval_id' validation from website_sale_donate
        product_id = vals.pop('product_id')
        set_qty = vals.pop('product_uom_qty')
        so._cart_update(product_id=product_id, line_id=so_line.id, set_qty=set_qty, **vals)

        # Link Sale Order Line
        self.write({'sale_order_line_id': so_line.id})

        return so_line

    @api.multi
    def add_payment_transaction(self):
        assert self.ensure_one(), "Only one record allowed"
        logger.info("Create Payment Transaction for %s" % self.id)

        # Get sale order
        so = self.sale_order_id
        assert so.partner_invoice_id.id == self.partner_id.id, "Partner of sale order do not match! (ID %s)" % self.id
        assert not so.payment_acquirer_id, "Sale Order has already an paymnet acquirere! (ID %s)" % self.id
        assert not so.payment_tx_id, "Sale Order has already a payment transaction! (ID %s)" % self.id

        # Create Payment Transaction
        tx_obj = self.env['payment.transaction']
        tx = tx_obj.create({
            'acquirer_id': self.acquirer_id.id,
            'type': 'form',
            'amount': so.amount_total,
            'currency_id': so.pricelist_id.currency_id.id,
            'partner_id': so.partner_invoice_id.id,
            'partner_country_id': so.partner_invoice_id.country_id.id,
            'reference': self.env['payment.transaction'].get_next_reference(so.name),
            'sale_order_id': so.id,
        })

        # Update Sale Order
        so.write({'payment_acquirer_id': self.acquirer_id.id,
                  'payment_tx_id': tx.id
                  })

        # Get provider name (e.g.: 'frst' or 'ogonedadi')
        provider = self.acquirer_id.provider

        # Prepare provider-field-data for form_feedback()
        provider_fields = self.get_fields_by_con_group('payment_' + provider)
        data = {k: self[k] for k in provider_fields if self[k]}
        data['reference'] = tx.reference
        data['amount'] = tx.amount
        data['currency'] = tx.currency_id.name

        # Use form_feedback() to update the payment transaction by the specific methods of the provider
        # ATTENTION: !!! form_feedback() IS MONKEY PATCHED IN website_sale_donate !!!
        #            the monkey patched version will update the sale order and send an e-mail on tx.state changes!
        tx.form_feedback(self.env.cr, self.env.uid, data, provider, context=self.env.context)

        # Link Payment Transaction
        self.write({'payment_transaction_id': tx.id})

        return tx

    @api.multi
    def update_state_by_sale_order_state(self):
        for r in self:
            sale_order = r.sale_order_id
            if sale_order and sale_order.state not in ('draft', 'error'):
                r.write({'state': 'done'})

    # --------------------
    # MAIN PROCESS METHODS
    # --------------------
    @api.multi
    def create_sale_order(self):
        for r in self:
            logger.info("Run create_sale_order() as superuser for record %s" % r.id)

            # Switch to fson_connector_sale admin user
            # ----------------------------------------
            # ATTENTION: Since the fson_connector_sale user group will only get minimal privileges we need to run
            #            the validation and linked record creation as user 'user_consale_admin'
            r_admin = r.sudo(user=self.env.ref('fson_connector_sale.user_consale_admin'))

            # VALIDATE RECORD
            # ---------------
            r_admin.validate_record()

            # CREATE AND LINK RECORDS
            # -----------------------
            # Add Partner res.partner
            r_admin.add_partner()

            # Add Employee res.partner
            r_admin.add_partner_employee()

            # Add Donee res.partner
            r_admin.add_partner_donee()

            # Add sale.order
            r_admin.add_sale_order()

            # Add sale.order.line
            r_admin.add_sale_order_line()

            # Add payment.transaction
            r_admin.add_payment_transaction()

            # Update the state of the fson_connector_sale record
            r_admin.update_state_by_sale_order_state()

    @api.multi
    def update_sale_order(self):
        for r in self:
            logger.info("NOT IMPLEMENTED! Run update_sale_order() as superuser for record %s" % r.id)

            # Switch to fson_connector_sale admin user
            # ----------------------------------------
            # ATTENTION: Since the fson_connector_sale user group will only get minimal privileges we need to run
            #            the validation and linked record creation as user 'user_consale_admin'
            r_admin = r.sudo(user=self.env.ref('fson_connector_sale.user_consale_admin'))

            # VALIDATE RECORD
            # ---------------
            r_admin.validate_record()

            # TODO: Must be discussed in the team first! (Right now already disabled in the controller)

    # ------------
    # CRUD METHODS
    # ------------
    @api.model
    def create(self, vals):
        # Create Record
        record = super(FSOConnectorSale, self).create(vals)

        # Validate records and process sale order and related records
        if any(f in vals for f in self.get_fields_by_con_group('all')):
            record.create_sale_order()

        return record

    @api.multi
    def write(self, vals):
        # Check records-to-update against vals
        if any(f in vals for f in self.get_fields_by_con_group('all')):
            self.validate_update_data(vals=vals)

        # Update Records
        res = super(FSOConnectorSale, self).write(vals)

        # Validate records and process sale order and related records
        if any(f in vals for f in self.get_fields_by_con_group('update_allowed')):
            self.update_sale_order()

        return res
