from django.test import TestCase
from unipath import Path
from ..helpers import tail


class LogTailTest(TestCase):
    """ Test log tail helper """

    def setUp(self):
        self.last_n_lines = 60
        self.path = Path(__file__).absolute().ancestor(2).child('tests').child('test.log')

    def test_tail(self):
        log_tail = tail(self.path, n=self.last_n_lines)
        self.assertEqual(len(log_tail), self.last_n_lines)
