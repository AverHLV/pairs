from django.shortcuts import redirect, render, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.context_processors import csrf
from django.utils.timezone import get_current_timezone
from django.core.exceptions import PermissionDenied
from config import constants
from decorators import moderator_required, is_ajax
from datetime import datetime, timedelta
from .models import Pair, Order, CustomUser
from .forms import PairForm, SearchForm, OrderProfitsForm, OrderReturnForm, OrderFilterForm

# TODO: remake user instance with render shortcut (all apps)


def pairs_paginator(request, page_number=1, for_search=False, search_pair=None):
    """ Display all pairs for current user (or all pairs for moderator) in checked and created order """

    show_reasons, show_check, show_close = False, False, False
    progress, empty_orders_message = None, None
    pairs = Pair.objects.none().order_by('checked', '-created')

    if not request.user.is_anonymous:
        if not for_search:
            pairs = Pair.objects.order_by('checked', '-created')

            if not request.user.is_moderator:
                pairs = pairs.filter(owner=request.user)
                empty_orders_message = 'You have not added a pair yet.'
            else:
                empty_orders_message = 'There are no pairs in the database.'

        else:
            pairs = search_pair
            empty_orders_message = 'The search has not given any results.'

        pairs = Paginator(pairs, constants.on_page_obj_number).page(page_number)

        # show 'Reasons' column or not

        for pair in pairs.object_list:
            if pair.checked > 1:
                show_reasons = True
                break

        # show 'Check' column for moderator or 'Close' column for ordinary user

        if request.user.is_moderator:
            for pair in pairs.object_list:
                if not pair.checked:
                    show_check = True
                    break

        else:
            for pair in pairs.object_list:
                if pair.checked < 2:
                    show_close = True
                    break

        progress = int((request.user.pairs_count * 100) / constants.pair_minimum)

    return render(request, 'pairs.html', {'pairs': pairs,
                                          'page_range': constants.page_range,
                                          'current_page': page_number,
                                          'user': request.user,
                                          'reasons': constants.failure_reasons,
                                          'show_reasons': show_reasons,
                                          'show_check': show_check,
                                          'show_close': show_close,
                                          'progress': progress,
                                          'pair_min': constants.pair_minimum,
                                          'empty': empty_orders_message,
                                          'search': for_search})


@login_required
def orders_paginator(request, page_number=1, for_search=False, search_order=None):
    """ Find all orders for rendering and then filter for specific user (if not moderator) """

    owner = None
    form = None

    if not for_search:
        orders = Order.objects.order_by('all_set', '-purchase_date')

        if not request.user.is_moderator:
            filtered_orders = Order.objects.none()
            owner = request.user.username

            for order in orders:
                if owner in order.get_owners_names():
                    filtered_orders |= Order.objects.filter(pk=order.id)

            orders = filtered_orders.order_by('all_set', '-purchase_date')
            empty_orders_message = 'Not found the orders, which include your added pairs.'

        else:
            empty_orders_message = 'There are no orders in the database.'

        # set get parameter 'period' to 0 by default

        try:
            request.GET['period']

        except KeyError:
            request.GET._mutable = True
            request.GET['period'] = '0'
            request.GET._mutable = False

        # filter orders by period parameter

        form = OrderFilterForm(request.GET)

        if form.is_valid():
            if form.cleaned_data['period']:
                orders = orders.filter(
                    created__gte=datetime.now(get_current_timezone()) - timedelta(days=30 * form.cleaned_data['period'])
                )

                empty_orders_message = 'There are no orders in the database created over specified period.'

    else:
        orders = search_order
        empty_orders_message = 'The search has not given any results.'

    profits = [order.calculate_profits(owner) for order in orders]
    orders = Paginator(orders, constants.on_page_obj_number).page(page_number)
    
    return render(request, 'orders.html', {'orders': orders,
                                           'profits': profits,
                                           'page_range': constants.page_range,
                                           'current_page': page_number,
                                           'user': request.user,
                                           'empty': empty_orders_message,
                                           'search': for_search,
                                           'form': form})


@is_ajax
@login_required
def mark_as_checked(request, pair_id, result, reason, __=None):
    """ Mark requested pair as checked by ajax """

    if not request.user.is_moderator and int(result) != 6:
        raise PermissionDenied

    pair = get_object_or_404(Pair, id=pair_id)

    if pair.checked and request.user.is_moderator:
        return JsonResponse({'status': 'Already checked'})

    pair.checked = int(result)

    if len(reason) and pair.checked == 5:
        if len(reason) > constants.reason_message_max_length:
            reason = reason[:constants.reason_message_max_length]

        pair.reason_message = reason
        pair.save(update_fields=['checked', 'reason_message'])

    else:
        pair.save(update_fields=['checked'])

    if pair.checked == 1:
        pair.owner.pairs_count += 1
        pair.owner.save(update_fields=['pairs_count'])

    return JsonResponse({'status': 'Checked', 'code': pair.checked, 'reason': pair.reason_message,
                         'reasons': constants.failure_reasons})


@is_ajax
@login_required
@moderator_required
def update_ebay_price(_, order_id, result, __=None):
    """ Update eBay price for specified order """

    order = get_object_or_404(Order, id=order_id)

    if order.all_set:
        return JsonResponse({'status': 'Already updated'})

    if order.multi:
        return JsonResponse({'status': 'Wrong order type'})

    result = round(float(result), 2)
    order.ebay_price = result
    order.total_profit = round(order.amazon_price * constants.profit_percentage - result, 2)
    order.all_set = True
    order.save(update_fields=['ebay_price', 'total_profit', 'all_set'])

    owner = order.get_first_owner()
    profit = owner.get_profit(order.total_profit)
    order.set_profits({owner.username: profit})
    owner.update_profit(order.total_profit)

    return JsonResponse({'status': 'Updated', 'price': result, 'income': order.total_profit, 'owner': owner.username,
                         'profit': round(profit, 2)})


@login_required
def add_pair(request):
    """ Create a Pair object or send validation errors """

    context = {'user': request.user, 'form': PairForm(), 'action': '/add_pair/', 'button_text': 'Add pair'}
    context.update(csrf(request))

    if request.POST:
        new_pair = PairForm(None, request.POST)

        if new_pair.is_valid():
            pair = new_pair.save(commit=False)
            user = get_object_or_404(CustomUser, username=request.user.username)
            pair.owner = user

            if new_pair.sku is not None:
                pair.seller_sku = new_pair.sku

            pair.amazon_approximate_price = new_pair.amazon_approximate_price
            pair.check_quantity()
            pair.save()
            return redirect('/')

        else:
            context['form'] = new_pair

    return render(request, 'form.html', context)


@login_required
def change_pair(request, pair_id):
    """ Update an existing Pair object """

    pair = get_object_or_404(Pair, pk=pair_id)

    if pair.owner.username != request.user.username and not request.user.is_moderator:
        raise PermissionDenied

    context = {'user': request.user, 'form': PairForm(initial={'asin': pair.asin, 'ebay_ids': pair.ebay_ids}),
               'action': '/change_pair/{0}/'.format(pair_id), 'button_text': 'Change pair'}
    context.update(csrf(request))

    if request.POST:
        new_pair = PairForm({'asin': pair.asin, 'ebay_ids': pair.ebay_ids}, request.POST)

        if new_pair.is_valid():
            pair.asin = new_pair.cleaned_data['asin']
            pair.ebay_ids = new_pair.cleaned_data['ebay_ids']
            pair.amazon_approximate_price = new_pair.amazon_approximate_price

            if pair.checked == 1:
                pair.owner.pairs_count -= 1
                pair.owner.save(update_fields=['pairs_count'])

            pair.checked = 0
            pair.save(update_fields=['asin', 'ebay_ids', 'checked', 'amazon_approximate_price'])
            return redirect('/')

        else:
            context['form'] = new_pair

    return render(request, 'form.html', context)


@login_required
def profits_table(request):
    """ Display profits table for price intervals """

    intervals = [(constants.profit_intervals[key], key) for key in constants.profit_intervals.keys()]
    return render(request, 'profit_table.html', {'intervals': sorted(intervals, key=lambda x: x[1]),
                                                 'user': request.user,
                                                 'profit_percentage': constants.profit_percentage,
                                                 'buffer': constants.profit_buffer})


@login_required
def search_for(request):
    """ Search specified objects for ordinary user or moderator """

    context = {'form': SearchForm(request.user.is_moderator), 'user': request.user, 'action': '/search/',
               'button_text': 'Search'}
    context.update(csrf(request))

    if request.POST:
        form = SearchForm(request.user.is_moderator, request.POST)
        context['form'] = form

        if form.is_valid():
            if request.user.is_moderator:
                if not int(form.cleaned_data['search_type']):
                    pairs = Pair.objects.filter(asin=form.cleaned_data['search_field'])
                else:
                    orders = Order.objects.filter(order_id=form.cleaned_data['search_field'])
                    return orders_paginator(request, for_search=True,
                                            search_order=orders.order_by('-created'))

            else:
                pairs = Pair.objects.filter(owner=request.user).filter(asin=form.cleaned_data['search_field'])

            return pairs_paginator(request, for_search=True, search_pair=pairs.order_by('-created'))

    return render(request, 'form.html', context)


@login_required
def search_from_orders(request, asin):
    """ Quick pairs search from orders page """

    if request.user.is_moderator:
        pairs = Pair.objects.filter(asin=asin)
    else:
        pairs = Pair.objects.filter(owner=request.user).filter(asin=asin)

    return pairs_paginator(request, for_search=True, search_pair=pairs.order_by('-created'))


@login_required
@moderator_required
def order_profits(request, order_id):
    """ Calculate and save owners profits for specific order """

    order = get_object_or_404(Order, pk=order_id)

    if order.all_set:
        return redirect('/orders/')

    context = {'form': OrderProfitsForm(order.get_owners_names(), order.amazon_price), 'user': request.user,
               'action': '/orders/profits/' + str(order_id) + '/', 'button_text': 'Submit'}
    context.update(csrf(request))

    if request.POST:
        form = OrderProfitsForm(order.get_owners_names(), order.amazon_price, request.POST)

        if form.is_valid():
            profits = {}
            order.ebay_price = form.cleaned_data['ebay_price']
            order.total_profit = form.total_profit

            for owner in order.get_owners():
                profit = form.cleaned_data[owner.username]
                owner.update_profit(profit)
                profits[owner.username] = owner.get_profit(profit)

            order.set_profits(profits, commit=False)
            order.all_set = True
            order.save(update_fields=['ebay_price', 'total_profit', 'owners_profits', 'all_set'])

            return redirect('/orders/')

        else:
            context['form'] = form

    return render(request, 'form.html', context)


@login_required
@moderator_required
def order_return(request, order_id):
    """ Make order return: update owners profits and write off a loss in failure case """

    order = get_object_or_404(Order, pk=order_id)

    if order.returned:
        return redirect('/orders/')

    context = {'form': OrderReturnForm(), 'user': request.user, 'action': '/orders/return/' + str(order_id) + '/',
               'button_text': 'Submit'}
    context.update(csrf(request))

    if request.POST:
        form = OrderReturnForm(request.POST)

        if form.is_valid():
            order.total_profit = 0
            order.returned = True

            for owner in order.get_owners():
                owner.update_profit(owner.recover_profit(order.owners_profits[owner.username]), increase=False)
                order.owners_profits[owner.username] = 0

            order.save(update_fields=['total_profit', 'returned', 'owners_profits'])

            if form.cleaned_data['return_type']:
                request.user.profit -= form.cleaned_data['loss']
                request.user.save(update_fields=['profit'])

            return redirect('/orders/')

        else:
            context['form'] = form

    return render(request, 'form.html', context)
