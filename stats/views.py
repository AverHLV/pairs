import matplotlib.pyplot as plt
from matplotlib import rc
from mpld3 import fig_to_html, plugins

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.timezone import get_current_timezone

from datetime import datetime, timedelta

from decorators import moderator_required
from config import constants
from pairs.models import Order
from users.models import CustomUser


@login_required
@moderator_required
def users_stats(request):
    """ Users stats page """

    users = CustomUser.objects.filter(is_active=True).order_by('username')
    orders = Order.objects.filter(created__gte=datetime.now(get_current_timezone()).replace(day=1))
    cost = sum([order.ebay_price for order in orders]) if len(orders) else 0

    return render(request, 'users.html', {
        'users': users,
        'profit': sum([user.profit for user in users]),
        'cost': cost,
        'pair_min': constants.pair_minimum
    })


@login_required
@moderator_required
def graphs(request):
    """ Display specific graphs with statistics """

    usernames, profits, ordernumbers, ordercounts, orderprofits = [], [], [], [], []
    current_time = datetime.now(get_current_timezone()).replace(hour=0, minute=0, second=0, microsecond=0)
    orders = Order.objects.filter(created__gte=current_time.replace(day=1))

    for user in CustomUser.objects.filter(is_active=True).order_by('username'):
        usernames.append(user.username)
        profits.append(round(user.profit, 2))
        ordernumbers.append([True for order in orders if user.username in order.get_owners_names()].count(True))

    usernumbers = range(len(usernames))
    days = range(1, current_time.day + 1)

    for day in days:
        found_orders = orders.filter(created__contains=current_time.replace(day=day).date())
        ordercounts.append(len(found_orders))
        orderprofits.append(round(sum([order.total_profit for order in found_orders]), 2))

    plt.style.use('ggplot')
    rc('font', size=14)
    rc('xtick', labelsize=10)
    fig1 = plt.figure()

    # users profits diagram

    plt.bar(usernumbers, profits, color='g')

    for i, v in enumerate(profits):
        plt.text(i - 0.2, v + 0.3, ' ' + str(v), va='center', fontweight='bold')

    plt.xticks(usernumbers, usernames)
    plt.ylabel('$')
    plt.title('Users profits', fontsize=20)

    fig1.tight_layout()

    # users orders number diagram

    fig2 = plt.figure()

    plt.bar(usernumbers, ordernumbers, color='b')
    plt.xticks(usernumbers, usernames)
    plt.ylabel('Count')
    plt.title('Users orders', fontsize=20)

    fig2.tight_layout()

    # orders stats plot

    fig3 = plt.figure()

    line1 = plt.plot(days, ordercounts, c='g', marker='o')
    line2 = plt.plot(days, orderprofits, c='b', marker='s')
    plt.legend(['Counts', 'Profits'])
    plt.xlabel('Days')
    plt.title('Orders stats')

    fig3.tight_layout()

    # repricer stats

    from repricer.models import RepricerStats
    fig4 = plt.figure()

    stats = RepricerStats.objects.filter(created__gte=datetime.now(get_current_timezone()) - timedelta(
        hours=constants.repricer_stats_hours))

    if len(stats):
        buybox_counts, minimum_price_counts, dates = [], [], []

        for stat in stats:
            buybox_counts.append(stat.buybox_count)
            minimum_price_counts.append(stat.min_price_count)
            dates.append(stat.get_time_str())

        plt.plot(dates, buybox_counts, c='g')
        plt.plot(dates, minimum_price_counts, c='b')
        plt.xticks(range(len(dates)), labels=dates)
        plt.yticks(range(max(max(buybox_counts), max(minimum_price_counts)) + 1))
        plt.legend(['BB count', 'LP count'])

    plt.xlabel('Time')
    plt.title('Repricer stats')

    fig4.tight_layout()

    # tooltips

    labels1 = ['count: {0}'.format(x) for x in ordercounts]
    labels2 = ['profit: {0}'.format(x) for x in orderprofits]

    tooltip1 = plugins.PointHTMLTooltip(line1[0], labels1)
    tooltip2 = plugins.PointHTMLTooltip(line2[0], labels2)

    plugins.connect(fig3, tooltip1, tooltip2)

    return render(request, 'graphs.html', {
        'figure1': fig_to_html(fig1),
        'figure2': fig_to_html(fig2),
        'figure3': fig_to_html(fig3),
        'figure4': fig_to_html(fig4)
    })
