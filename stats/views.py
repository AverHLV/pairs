import matplotlib.pyplot as plt
from matplotlib import rc
from mpld3 import fig_to_html, plugins
from django.shortcuts import render_to_response
from django.contrib.auth.decorators import login_required
from django.utils.timezone import get_current_timezone
from datetime import datetime
from decorators import moderator_required
from config.constants import pair_minimum
from pairs.models import Order
from users.models import CustomUser


@login_required
@moderator_required
def users(request):
    """ Users stats page """

    return render_to_response('users.html', {'user': request.user, 'users': CustomUser.objects.order_by('username'),
                                             'pair_min': pair_minimum})


@login_required
@moderator_required
def graphs(request):
    """ Display specific graphs with statistics """

    usernames, profits, ordernumbers, ordercounts, orderprofits = [], [], [], [], []
    current_time = datetime.now(get_current_timezone()).replace(hour=0, minute=0, second=0, microsecond=0)
    orders = Order.objects.filter(created__gte=current_time.replace(day=1))

    for user in CustomUser.objects.order_by('username'):
        usernames.append(user.username)
        profits.append(user.profit)
        ordernumbers.append([True for order in orders if user.username in order.get_owners_names()].count(True))

    usernumbers = range(len(usernames))
    days = range(1, current_time.day + 1)

    for day in days:
        found_orders = orders.filter(created__contains=current_time.replace(day=day).date())
        ordercounts.append(len(found_orders))
        orderprofits.append(sum([order.total_profit for order in found_orders]))

    rc('font', size=16)
    fig1 = plt.figure()

    # users profits diagram

    plt.subplot(121)
    plt.bar(usernumbers, profits, color='g')

    for i, v in enumerate(profits):
        plt.text(i - 0.2, v + 0.3, ' ' + str(v), va='center', fontweight='bold')

    plt.xticks(usernumbers, usernames)
    plt.ylabel('$')
    plt.title('Users profits', fontsize=20)

    # users orders number diagram

    plt.subplot(122)
    plt.bar(usernumbers, ordernumbers, color='b')
    plt.xticks(usernumbers, usernames)
    plt.ylabel('Count')
    plt.title('Users orders', fontsize=20)

    fig1.tight_layout()

    # orders stats plot in new figure

    fig2 = plt.figure()

    line1 = plt.plot(days, ordercounts, c='g', marker='o')
    line2 = plt.plot(days, orderprofits, c='b', marker='s')
    plt.legend(['Counts', 'Profits'])
    plt.xlabel('Days')
    plt.title('Orders stats')

    # tooltips

    labels1 = ['count: {0}'.format(x) for x in ordercounts]
    labels2 = ['profit: {0}'.format(x) for x in orderprofits]
    tooltip1 = plugins.PointHTMLTooltip(line1[0], labels1)
    tooltip2 = plugins.PointHTMLTooltip(line2[0], labels2)
    plugins.connect(fig2, tooltip1, tooltip2)

    fig2.tight_layout()

    return render_to_response('graphs.html', {'figure1': fig_to_html(fig1), 'figure2': fig_to_html(fig2),
                                              'user': request.user})
