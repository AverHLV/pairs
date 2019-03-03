from django.db import models
from django.contrib.auth.models import AbstractUser
from config import constants


class CustomUser(AbstractUser):
    """
    User model with additional fields

    :field email: user email address
    :field email_checked: is email proved by following link in send message
    :field is_moderator: is user has a moderator permissions
    :field pairs_count: count of pairs added by this user
    :field profit_level: the level of benefits received by this user
    :field profit: benefit of this user in dollars
    """

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

        return round(profit * constants.profit_percent[self.profit_level]['mine'], 2)

    def get_relative_profit(self):
        """ Calculate relative profit according to user pairs count """

        return round(self.profit * (self.pairs_count / constants.pair_minimum), 2)

    def recover_profit(self, profit):
        """ Calculate initial income by user profit """

        return profit / constants.profit_percent[self.profit_level]['mine']

    def update_profit(self, profit, increase=True):
        """ Update profit of this user and all others in the established hierarchy """

        if increase:
            self.profit += self.get_profit(profit)
        else:
            self.profit -= self.get_profit(profit)

        self.save(update_fields=['profit'])

        profit_vector = constants.profit_percent[self.profit_level]
        levels = list(profit_vector.keys())
        levels.remove('mine')

        for level in levels:
            for user in CustomUser.objects.filter(profit_level=level):
                if increase:
                    user.profit += profit * profit_vector[level]
                else:
                    user.profit -= profit * profit_vector[level]

                user.save(update_fields=['profit'])


class Note(models.Model):
    """ Model for user private notes """

    text = models.TextField()
    author = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    objects = models.Manager()

    class Meta:
        db_table = 'notes'

    def __str__(self):
        if len(self.text) < constants.note_preview_length:
            return '{0}`s note. {1}'.format(self.author, self.text)
        else:
            return '{0}`s note. {1}...'.format(self.author, self.text[:constants.note_preview_length])
