# -*- coding: utf-8 -*-

from openerp.tests import common
from openerp.tools.safe_eval import safe_eval
from openerp import fields
from datetime import datetime
from datetime import timedelta
from openerp.exceptions import ValidationError

import logging
logger = logging.getLogger(__name__)


class TestFRSTPersonEmail(common.TransactionCase):
    def setUp(self):
        super(TestFRSTPersonEmail, self).setUp()

        self.partner_max1 = self.env['res.partner'].create({
            'name': u"Max Mustermann",
            'email': u"max@test.com"
        })

        self.partner_max2 = self.env['res.partner'].create({
            'name': u"Max Mustermann",
            'email': u"max@test.com"
        })

    # ATTENTION: Tests have no specific order! Therefore i use the "dumb" method of numbers added!
    # ATTENTION: The setUp() is done individually for every test:
    #            !!! Tests do NOT share the data !!!

    def test_01_create_partner_and_main_personemail(self):
        self.assertEqual(self.partner_max1.email, u"max@test.com")
        self.assertEqual(self.partner_max1.main_personemail_id.email, self.partner_max1.email)

    def test_02_update_partner_email(self):
        """ Create a new PersonEmail which must be the new Hauptemailadresse """
        self.partner_max1.write({'email': 'max_email2@test.com'})
        self.assertEqual(self.partner_max1.email, 'max_email2@test.com')
        self.assertEqual(self.partner_max1.main_personemail_id.email, self.partner_max1.email)
        self.assertIs(len(self.partner_max1.frst_personemail_ids), 2)

    def test_03_reactivate_partner_email(self):
        """ Reactivate the first PersonEmail and set it as the Hauptemailadresse """
        self.partner_max1.write({'email': 'max_email2@test.com'})
        self.partner_max1.write({'email': 'max@test.com'})
        self.assertEqual(self.partner_max1.email, 'max@test.com')
        self.assertEqual(self.partner_max1.main_personemail_id.email, self.partner_max1.email)
        self.assertIs(len(self.partner_max1.frst_personemail_ids), 2)

    def test_04_merge_personemails_of_two_different_partners(self):
        """ Test the merging of two PersonEmail from different persons """
        personemail_obj = self.env['frst.personemail']
        logger.info("TEST 04: MERGE PERSONEMAIL (remove_id) %s OF PERSON MAX2 %s "
                    "INTO PERSONEMAIL (keep_id) %s OF PERSON MAX1 %s"
                    "" % (self.partner_max2.main_personemail_id.id, self.partner_max2.id,
                          self.partner_max1.main_personemail_id.id, self.partner_max1.id))
        personemail_obj.fso_merge(remove_id=self.partner_max2.main_personemail_id.id,
                                  keep_id=self.partner_max1.main_personemail_id.id)
        self.assertFalse(self.partner_max2.main_personemail_id)
        self.assertFalse(self.partner_max2.frst_personemail_ids)

    def test_05_merge_personemails_of_two_different_partners_reactivate_pe(self):
        """
        Test the merging of two PersonEmail from different persons and make sure the person where the
        PersonEmail gets removed will reactivate the remaining PersonEmail as the main e-mail
        """
        # Create another PersonEmail for max2 and reactivate the original personemail
        self.partner_max2.write({'email': 'max2_email2@test.com'})
        self.partner_max2.write({'email': 'max@test.com'})
        # Merge the PersonEmails
        personemail_obj = self.env['frst.personemail']
        logger.info("TEST 05: MERGE PERSONEMAIL (remove_id) %s OF PERSON MAX2 %s "
                    "INTO PERSONEMAIL (keep_id) %s OF PERSON MAX1 %s AND CHECK MAX2 MAIN EMAIL"
                    "" % (self.partner_max2.main_personemail_id.id, self.partner_max2.id,
                          self.partner_max1.main_personemail_id.id, self.partner_max1.id))
        personemail_obj.fso_merge(remove_id=self.partner_max2.main_personemail_id.id,
                                  keep_id=self.partner_max1.main_personemail_id.id)
        # Check if the main email of max 2 is max2_email2@test.com
        self.assertEqual(self.partner_max2.main_personemail_id.email, 'max2_email2@test.com')

    def test_06_forced_main_email_address(self):
        # Lock the current partner email as the main email
        self.partner_max1.main_personemail_id.write({'forced_main_address': True})
        # Create another personemail
        self.partner_max1.write({'email': 'new_email_address@test.com'})
        # Check that the first personemail is still the main
        self.assertEqual(self.partner_max1.main_personemail_id.email, 'max@test.com')

    def test_07_inactivate_forced_main_email_address_before(self):
        email_max1 = self.partner_max1.main_personemail_id
        # Lock the current partner email as the main email
        email_max1.write({'forced_main_address': True})
        # Deactivate the personemail
        email_max1.write({'gueltig_bis': datetime.now() - timedelta(days=1)})
        self.assertEqual(email_max1.state, 'inactive')
        # Create another email
        self.partner_max1.write({'email': 'new_email_address@test.com'})
        # Make sure the new email is the new main email
        self.assertEqual(self.partner_max1.main_personemail_id.email, 'new_email_address@test.com')

    def test_08_inactivate_forced_main_email_address_after(self):
        email_max1 = self.partner_max1.main_personemail_id
        # Lock the current partner email as the main email
        email_max1.write({'forced_main_address': True})
        # Create another email
        self.partner_max1.write({'email': 'new_email_address@test.com'})
        # Make sure the max@ email is still the main mail because it is the forced main email
        self.assertEqual(self.partner_max1.main_personemail_id.email, 'max@test.com')
        # Deactivate the max@ email after the new email was created
        email_max1.write({'gueltig_bis': datetime.now() - timedelta(days=1)})
        self.assertEqual(email_max1.state, 'inactive')
        # Make sure the new email is the new main email
        self.assertEqual(self.partner_max1.main_personemail_id.email, 'new_email_address@test.com')

    def test_09_set_two_emails_as_forced_main_address(self):
        email_max1 = self.partner_max1.main_personemail_id
        email_max1.write({'forced_main_address': True})
        self.assertEqual(email_max1.forced_main_address, True)
        with self.assertRaises(AssertionError):
            self.env['frst.personemail'].create({'partner_id': self.partner_max1.id,
                                                 'email': 'new_email_address@test.com',
                                                 'forced_main_address': True})
