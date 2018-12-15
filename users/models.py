from django.db import models
from django.contrib.auth.models import AbstractUser
from config.constants import profit_percent


class CustomUser(AbstractUser):
    """ User model with additional fields """

    email = models.EmailField(unique=True)
    email_checked = models.BooleanField(default=False)
    is_moderator = models.BooleanField(default=False)
    pairs_count = models.PositiveSmallIntegerField(default=0)
    profit_level = models.PositiveSmallIntegerField(default=0)
    profit = models.FloatField(default=0)

    class Meta:
        db_table = 'users'

    def get_profit(self, profit):
        """ Calculate profit for this user """

        return round(profit * profit_percent[self.profit_level]['mine'], 2)

    def recover_profit(self, profit):
        """ Calculate initial income by user profit """

        return profit / profit_percent[self.profit_level]['mine']

    def update_profit(self, profit, increase=True):
        """ Update profit of this user and all others in the established hierarchy """

        if increase:
            self.profit += self.get_profit(profit)
        else:
            self.profit -= self.get_profit(profit)

        self.save(update_fields=['profit'])

        profit_vector = profit_percent[self.profit_level]
        levels = list(profit_vector.keys())
        levels.remove('mine')

        for level in levels:
            for user in CustomUser.objects.filter(profit_level=level):
                if increase:
                    user.profit += profit * profit_vector[level]
                else:
                    user.profit -= profit * profit_vector[level]

                user.save(update_fields=['profit'])
