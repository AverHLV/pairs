class BrowseAPIError(Exception):
    """ Browse API base exception """

    def __init__(self, msg):
        self.msg = msg


class BrowseAPITimeoutError(BrowseAPIError):
    pass


class BrowseAPIConnectionError(BrowseAPIError):
    pass
