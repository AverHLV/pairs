from django import template

register = template.Library()


@register.filter
def subtract(arg1, arg2):
    return int(arg1) - int(arg2)


@register.filter
def addstr(arg1, arg2):
    return str(arg1) + str(arg2)


@register.filter
def splitstr(string, delimiter=';'):
    return string.split(delimiter)


@register.filter
def list_item(input_list, index):
    if len(input_list) > index - 1:
        return input_list[index - 1]


@register.filter
def get_item(dictionary, key):
    if dictionary is not None:
        return dictionary.get(key)


@register.filter
def sort_json(dictionary=None):
    if dictionary is not None:
        return sorted(dictionary.items(), key=lambda x: x[0])


@register.filter
def split(string, _=None):
    return string.split(';')


@register.simple_tag
def define(value=None):
    return value
