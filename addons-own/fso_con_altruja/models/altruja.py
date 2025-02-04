# -*- coding: utf-'8' "-*-"
from openerp import api, models, fields
from openerp.exceptions import ValidationError

import logging
logger = logging.getLogger(__name__)


class Altruja(models.Model):
    _name = "altruja"

    # ------
    # FIELDS
    # ------
    state = fields.Selection(selection=[('new', 'New'),
                                        ('error', 'Error'),
                                        ('done', 'Done'),
                                        ('skipped', 'Skipped'),
                                        ('synced', 'Synced')],
                             string="State",
                             readonly=True)

    # Check if the same job exits already
    skipped = fields.One2many(comodel_name='altruja', inverse_name='skipped_by', readonly=True)
    skipped_by = fields.Many2one(comodel_name='altruja', inverse_name='skipped', index=True, readonly=True)

    # Errors and exceptions
    error_type = fields.Selection([('processing', 'Processing'),
                                   ('unknown', 'Unknown')],
                                  string="Error Type",
                                  readonly=True)
    error_details = fields.Text(string='Error Details',
                                readonly=True)
    # Receiving
    controller_update_date = fields.Datetime(string="Last Update from Controller",
                                             help="Last updated from json controllers. E.g.: /altruja/*",
                                             readonly=True)

    # Linking
    partner_id = fields.Many2one(comodel_name='res.partner', inverse_name="altruja_ids",
                                 readonly=True, index=True)
    sale_order_id = fields.Many2one(comodel_name='sale.order', inverse_name="altruja_ids",
                                    index=True,
                                    readonly=True)
    sale_order_line_id = fields.Many2one(comodel_name='sale.order.line', inverse_name="altruja_ids",
                                         index=True,
                                         readonly=True)
    payment_transaction_id = fields.Many2one(comodel_name='payment.transaction', inverse_name="altruja_ids",
                                             index=True,
                                             readonly=True)
    bank_id = fields.Many2one(comodel_name='res.partner.bank', inverse_name="altruja_ids",
                              index=True,
                              readonly=True, help="Bankkonto")

    # Altruja Fields
    # --------------
    altruja_status = fields.Char('Altruja Status', readonly=True)               # Derzeit nicht verarbeitet
    datum = fields.Datetime('Datum', readonly=True, required=True)              # ACHTUNG: = Buchungsdatum = Payment Transaction Datum!

    anonym = fields.Char('Anonym', readonly=True)                               # Derzeit nicht verarbeitet
    rechnungsnummer = fields.Char('Rechnungsnummer', readonly=True)             # Derzeit nicht verarbeitet
    wirecard_zeitraum = fields.Char('Wirecard-Zeitraum', readonly=True)         # Derzeit nicht verarbeitet
    quittungavailableat = fields.Char('Quittungavailableat', readonly=True)     # Derzeit nicht verarbeitet
    selbst_buchen = fields.Char('Selbst buchen', readonly=True)                 # Derzeit nicht verarbeitet

    sonderwert_1 = fields.Char('sonderwert_1', readonly=True)                   # Derzeit nicht verarbeitet
    sonderwert_2 = fields.Char('sonderwert_2', readonly=True)                   # Derzeit nicht verarbeitet
    sonderwert_3 = fields.Char('sonderwert_3', readonly=True)                   # Derzeit nicht verarbeitet

    # res.partner
    firma = fields.Char('Firma', readonly=True)                                 # TODO: Check if we need an extra partner for company?
    vorname = fields.Char('Vorname', readonly=True,)                            # TODO: Ceck if firstname and lastname is required!
    nachname = fields.Char('Nachname', readonly=True, required=True)
    email = fields.Char('Email', readonly=True)

    strasse = fields.Char('Strasse', readonly=True)
    adresszusatz = fields.Char('Adresszusatz', readonly=True)
    postleitzahl = fields.Char('Postleitzahl', readonly=True)
    ort = fields.Char('Ort', readonly=True)
    land = fields.Char('Land', readonly=True)

    geburtsdatum = fields.Char('Geburtsdatum', readonly=True)

    kontakt_erlaubt = fields.Char('Kontakt erlaubt', readonly=True)
    spendenquittung = fields.Char('Spendenquittung', readonly=True)                                 # Nicht mehr benoetig

    # res.partner.bank
    iban = fields.Char('IBAN', readonly=True)
    bic = fields.Char('BIC', readonly=True)
    kontoinhaber = fields.Char('Kontoinhaber', readonly=True)                                       # TODO: Add field to payment_frst ?!?

    # sale.order
    spenden_id = fields.Integer('Spenden-ID', index=True, readonly=True, required=True)             # EXTERNAL ID OF THE RECORD
    erstsspenden_id = fields.Char('Erstsspenden-ID', readonly=True,
                                  help="Entspricht dem ersten Auftrag bei wiederkehrenden Spenden (Vertrag)")
    waehrung = fields.Selection(string='Waehrung',
                                selection=[('EUR', 'EUR')], required=True, readonly=True)           # Only 'EUR' is allowed

    # sale.order.line
    spenden_typ = fields.Char('Spenden-Typ', readonly=True, required=True)                          # Possible values = (Einzelspende, Dauerfolgespende)
    spendenbetrag = fields.Float('Spendenbetrag', readonly=True, required=True)                     # float ?
    intervall = fields.Char('Intervall', readonly=True, required=True)                              # Possible values = (einmalig, jährlich, halbjährlich, vierteljährlich, monatlich)

    seiten_id = fields.Char('Seiten-ID', readonly=True)                                             # Derzeit nicht verarbeitet
    Seitenname = fields.Char('Seitenname', readonly=True)                                           # FRST Verarbeitung ZVerz.

    # payment.transaction
    quelle = fields.Char('Quelle', required=True,
                         help="z.B.: Online (Wirecard/Lastschrift)", readonly=True)                 # Possible values = ("Online (Wirecard/Kreditkarte)", "Online (Wirecard/Lastschrift)", "direkt / PayPal")

    # --------------------------
    # CONSTRAINTS AND VALIDATION
    # --------------------------
    # https://www.postgresql.org/docs/9.3/static/ddl-constraints.html
    _sql_constraints = [
        ('spenden_id_unique', 'UNIQUE(spenden_id)', "'spenden_id' must be unique!"),
    ]

    @api.constrains('spenden_typ')
    def constrain_spenden_typ(self):
        for r in self:
            allowed_values = ('Einzelspende', 'Dauerfolgespende')
            if r.spenden_typ not in allowed_values:
                raise ValidationError("'spenden_typ' must be one of: %s" % str(allowed_values))

    @api.constrains('intervall')
    def constrain_intervall(self):
        for r in self:
            allowed_values = ('einmalig', 'jährlich', 'halbjährlich', 'vierteljährlich', 'monatlich')
            if r.intervall and r.intervall not in allowed_values:
                raise ValidationError("'intervall' must be one of: %s" % str(allowed_values))

    @api.constrains('quelle')
    def constrain_quelle(self):
        for r in self:
            allowed_values = ('Online (Wirecard/Kreditkarte)', 'Online (Wirecard/Lastschrift)', 'direkt / PayPal')
            if r.quelle not in allowed_values:
                raise ValidationError("'quelle' must be one of: %s" % str(allowed_values))
