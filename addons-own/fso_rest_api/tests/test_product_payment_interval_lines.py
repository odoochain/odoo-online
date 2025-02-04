# -*- coding: utf-8 -*-

from fso_rest_api_test_case import FsoRestApiTestCase

import logging
logger = logging.getLogger(__name__)


class TestFsoRestApiProductPaymentInterval(FsoRestApiTestCase):
    _model_name = "product.payment_interval_lines"

    def create_payment_interval_line(self):
        product = self.read_first_from_api(model="product.product")
        interval = self.read_first_from_api(model="product.payment_interval")
        response = self.create_via_api(data={
            "product_id": product["product_tmpl_id"],
            "payment_interval_id": interval["id"]
        })
        return response

    def create_payment_interval_line_as_other(self):
        product_obj = self.phantom_env["product.product"]
        interval_obj = self.phantom_env["product.payment_interval"]
        line_obj = self.phantom_env[self._model_name]

        product = product_obj.search([], order="id", limit=1)
        interval = interval_obj.search([], order="id", limit=1)

        line = line_obj.sudo().create({
            "product_id": product.product_tmpl_id.id,
            "payment_interval_id": interval.id
        })
        return line.id

    def test_read_product_payment_interval_lines_works(self):
        _ = self.create_payment_interval_line()

        model = self.read_first_from_api()
        self.assertModel(model)

    def test_create_minimal_product_payment_interval_lines_works(self):
        response = self.create_payment_interval_line()
        self.assertEqual(response.status_code, self.HTTP_OK_CREATED)

    def test_update_own_product_payment_interval_lines_works(self):
        _ = self.create_payment_interval_line()

        expected_sequence = 1001
        model = self.read_first_from_api()

        self.assertModel(model)
        self.assertNotEqual(model["sequence"], expected_sequence)

        response = self.update_via_api(data={
            "id": int(model["id"]),
            "sequence": expected_sequence
        })
        self.assertEqual(response.status_code, self.HTTP_OK_NO_CONTENT)

        actual = self.phantom_env[self._model_name].browse([int(model["id"])])
        self.assertEqual(actual.sequence, expected_sequence)

    def test_update_others_product_payment_interval_lines_is_denied(self):
        other_line_id = self.create_payment_interval_line_as_other()
        expected_sequence = 1001

        response = self.update_via_api(data={
            "id": other_line_id,
            "sequence": expected_sequence
        })
        self.assertTrue(not str(response.status_code).startswith("2"))
        self.assertTrue("Access Denied" in response.content)

    def test_delete_own_product_payment_interval_lines_works(self):
        _ = self.create_payment_interval_line()

        model = self.read_first_from_api()
        response = self.delete_via_api(model["id"])
        self.assertModel(model)
        self.assertEqual(response.status_code, self.HTTP_OK_NO_CONTENT)

    def test_delete_others_product_payment_interval_lines_is_denied(self):
        other_line_id = self.create_payment_interval_line_as_other()
        response = self.delete_via_api(other_line_id)
        self.assertTrue(not str(response.status_code).startswith("2"))
        self.assertTrue("Access Denied" in response.content)
