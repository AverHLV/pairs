from django.test import TestCase
from unipath import Path
from json import loads
from config import constants
from ..helpers import tail


def load_test_data():
    test_data_path = Path(__file__).absolute().ancestor(2).child('tests').child('test_data.json')

    with open(test_data_path, encoding=constants.load_encoding) as file:
        return loads(file.read())


test_data = load_test_data()


class LogTailTest(TestCase):
    """ Test log tail helper """

    def setUp(self):
        self.path = Path(__file__).absolute().ancestor(2).child('tests').child('test.log')

    def test_tail(self):
        log_tail = tail(self.path, n=test_data['LogTailTest']['tail_len'])

        self.assertEqual(len(log_tail), test_data['LogTailTest']['tail_len'])
        self.assertEqual(str(log_tail), test_data['LogTailTest']['log_tail'])
