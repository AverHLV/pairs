from os import environ
from importlib import import_module

static_version = import_module(environ['DJANGO_SETTINGS_MODULE']).STATIC_VERSION


def version(_) -> dict:
    """ Context processor for setting staticfiles version """

    return {'version': static_version}
