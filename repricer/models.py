from django.db import models
from datetime import datetime


class RepricerStats(models.Model):
    """ Models that provides repricer items statistics """

    buybox_count = models.PositiveSmallIntegerField(default=0)
    min_price_count = models.PositiveSmallIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    class Meta:
        db_table = 'repricerstats'

    def __str__(self):
        return 'BB count: {0}, LP count: {1}, time: {2}'.format(
            self.buybox_count, self.min_price_count, self.get_time_str()
        )

    def save_stats(self):
        """ Get necessary pairs data and save object """

        from pairs.models import Pair

        self.buybox_count = len(Pair.objects.filter(is_buybox_winner=True))
        self.min_price_count = len(Pair.objects.lowest_price_pairs())
        self.save()

    def get_time_str(self):
        """ Get object created time in format 'hours: minutes' """

        return datetime.strftime(self.created, '%H:%M')
