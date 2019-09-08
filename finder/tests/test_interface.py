from django.test import TestCase
from datetime import datetime, timedelta

from config import constants
from utils import secret_dict
from ..interface import KeepaFinder


class KeepaTest(TestCase):
    """ Test KeepaFinder methods """

    def setUp(self) -> None:
        self.keepa = KeepaFinder(secret_dict['keepa_key'])

        now = datetime.now()
        old_day = now - timedelta(days=31 * constants.threshold_month_number)

        self.dates = [old_day, now]
        self.not_fit_dates = [old_day, old_day]
        self.all_fit_dates = [now, now]

        start_value = 10
        self.good_sales = []
        self.bad_sales = [start_value] * (constants.threshold_month_number + 1)

        for _ in range(constants.threshold_month_number + 1):
            self.good_sales.append(start_value)
            start_value *= 0.5

        self.good_products = ['B07QH6F56T']
        self.bad_products = ['B01BB3VLNY']

    def test_actualize(self):
        index = self.keepa.actualize(self.dates)
        self.assertTrue(index == 1)

        index = self.keepa.actualize(self.not_fit_dates)
        self.assertTrue(index == -1)

        index = self.keepa.actualize(self.all_fit_dates)
        self.assertTrue(index == 0)

    def test_analyze_sales(self):
        mark = self.keepa.analyze_sales(self.good_sales)
        self.assertTrue(mark)

        mark = self.keepa.analyze_sales(self.bad_sales)
        self.assertTrue(not mark)

    def test_keepa_call(self):
        products = self.keepa(self.good_products)
        self.assertTrue(len(products))

        products = self.keepa(self.bad_products)
        self.assertTrue(not len(products))
