from config.settings.production import STATIC_VERSION


def version(_):
    """ Context processor for setting staticfiles version """

    return {'version': STATIC_VERSION}
