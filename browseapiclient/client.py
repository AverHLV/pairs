from requests import post, exceptions
from browseapiclient.exceptions import BrowseAPIConnectionError, BrowseAPITimeoutError


class EBayBrowseAPIClient(object):
    """ Client class for eBay BrowseAPI """

    __url = 'https://api.ebay.com/buy/browse/v1/item_summary'
    __search_by_image_url = __url + '/search_by_image?limit={}'

    def __init__(self, app_token: str):
        """
        Client initialization

        :param app_token: eBay developer application token
        """

        self.__headers = {
            'Accept': 'application/json',
            'Accept-Charset': 'utf-8',
            'Authorization': 'Bearer {}'.format(app_token),
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US'
        }

    def search_by_image(self, image_string: str, limit=200) -> dict:
        """
        BrowseAPI searchByImage method

        :param image_string: base64 encoded image
        :param limit: max items count in one response
        :return: response json
        """

        url = self.__search_by_image_url.format(limit)

        try:
            return post(url, headers=self.__headers, json={'image': image_string}).json()

        except exceptions.Timeout as e:
            raise BrowseAPITimeoutError(e)

        except exceptions.ConnectionError as e:
            raise BrowseAPIConnectionError(e)


if __name__ == '__main__':
    from PIL import Image
    from json import loads

    try:
        with open('user_secret.json') as file:
            secret = loads(file.read())

    except IOError as ex:
        secret = None
        print('Secret file not found: {0}'.format(ex))
        exit()

    image = Image.open('s-l1600.jpg')

    import base64
    from io import BytesIO

    buffered = BytesIO()
    image.save(buffered, format='JPEG')
    img_str = str(base64.b64encode(buffered.getvalue()))[2:-1]

    browse_api = EBayBrowseAPIClient(secret['eb_app_token'])
    response = browse_api.search_by_image(img_str)

    print(response)
