from keepa import Keepa


class KeepaFinder(object):
    def __init__(self, credentials: dict):
        try:
            self.api = Keepa(credentials['secret_key'])

        except KeyError:
            raise ValueError('No secret key field in credentials')

        except Exception:
            # no custom exception in keepa interface for this case

            raise ValueError('Invalid api key')

    def products_history(self, asins: list):
        result = self.api.query(asins, )
        print(result[0]['data']['SALES'])


if __name__ == '__main__':
    from json import loads

    try:
        with open('finder_secret.json') as file:
            secret = loads(file.read())

    except IOError as ex:
        secret = None
        print('Secret file not found: {0}'.format(ex))
        exit()

    finder = KeepaFinder(secret)
    finder.products_history(['B01BZXMDWS', 'B00J2JNU52', 'B07LH15L8S'])
