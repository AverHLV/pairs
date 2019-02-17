from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from time import sleep


class SeleniumBuyer(object):
    """ Selenium automatic eBay item buyer powered by Chrome in headless mode """

    login_url = 'https://signin.ebay.com/ws/eBayISAPI.dll'
    item_page_url = 'https://www.ebay.com/itm/{0}'
    seller_message = 'Dear seller, please put no price tags or ads at the package. I will be grateful!'

    def __init__(self, credentials, payment_cred, driver_path='chromedriver', wait_page_load_delay=7,
                 headless=True):
        options = Options()

        if headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')

        try:
            self.driver = webdriver.Chrome(driver_path, chrome_options=options)

        except IOError:
            raise ValueError('Specified webdriver file does not exists: {0}'.format(driver_path))

        self.payment_credentials = payment_cred
        self.wait_page_load_delay = wait_page_load_delay
        self.login(credentials)

    def login(self, credentials):
        self.driver.get(self.login_url)

        try:
            elements = self.driver.find_elements_by_class_name('fld')

        except NoSuchElementException:
            print('Login form inputs not found')
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            return

        elements[2].send_keys(credentials[0])
        elements[3].send_keys(credentials[1])

        try:
            self.driver.find_element_by_id('sgnBt').click()

        except NoSuchElementException:
            print('Login form button not found')
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            return

    def purchase(self, ebay_id, ship_info, confirm_purchase=True):
        """ Open, fill and submit eBay item purchase form """

        if not self.check_ship_info(ship_info):
            return

        self.driver.get(self.item_page_url.format(ebay_id))

        try:
            self.driver.find_element_by_id('binBtn_btn').click()

        except NoSuchElementException:
            print('BuyItNow button not found')
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            return

        # choose payment method if not chosen yet

        try:
            self.driver.find_element_by_xpath('//span[text()="{0}"]'.format(self.payment_credentials[0]))

        except NoSuchElementException:
            try:
                self.driver.find_element_by_xpath('//input[@value="PAYPAL"]').click()
                self.driver.find_element_by_id('email').send_keys(self.payment_credentials[0])
                self.driver.find_element_by_id('password').send_keys(self.payment_credentials[1])
                self.driver.find_element_by_id('btnLogin').click()

            except NoSuchElementException:
                print('Payment method choosing failed')
                self.driver.save_screenshot('selenium_buyer_page_exc.png')
                return

        # fill and submit ship to form

        try:
            self.driver.find_element_by_xpath('//a[@data-test-id="EXPAND_SHIPPING_ADDRESSES"]').click()
            sleep(self.wait_page_load_delay)

            self.driver.find_element_by_xpath('//a[contains(text(),"Add a new address")]').click()
            sleep(self.wait_page_load_delay)

            self.driver.find_element_by_id('firstName').send_keys(ship_info['first_name'])
            self.driver.find_element_by_id('lastName').send_keys(ship_info['last_name'])
            self.driver.find_element_by_id('addressLine1').send_keys(ship_info['address'])
            self.driver.find_element_by_id('city').send_keys(ship_info['city'])
            self.driver.find_element_by_id('postalCode').send_keys(ship_info['zip_code'])
            self.driver.find_element_by_id('phoneNumber').send_keys(ship_info['phone_number'])

            region = self.driver.find_element_by_xpath('//select[@id="stateOrProvince"]/option[text()="{0}"]'
                                                       .format(ship_info['region']))
            region.click()

            self.driver.find_element_by_xpath('//button[@data-test-id="ADD_ADDRESS_SUBMIT"]').click()

        except NoSuchElementException as e:
            print('Ship to form element not found: {0}'.format(e))
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            return

        # message for seller

        sleep(self.wait_page_load_delay)

        try:
            self.driver.find_element_by_xpath('//a[@data-test-id="MESSAGE_TO_SELLER_OPEN"]').click()
            sleep(self.wait_page_load_delay)

            element = self.driver.find_element_by_xpath('//textarea[@data-test-id="MESSAGE_TO_SELLER_TEXT_AREA"]')
            element.send_keys(self.seller_message)

            self.driver.find_element_by_xpath('//button[@data-test-id="MESSAGE_TO_SELLER_SUBMIT"]').click()

        except NoSuchElementException:
            print('Seller message form element not found')

        # set quantity

        sleep(self.wait_page_load_delay)

        try:
            count = self.driver.find_element_by_xpath(
                '//select[@data-test-id="CART_DETAILS_ITEM_QUANTITY"]/option[text()="{0}"]'.format(ship_info['count'])
            )

            count.click()

        except NoSuchElementException:
            print('Quantity select element not found')
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            return

        sleep(self.wait_page_load_delay)

        if not confirm_purchase:
            print('Done')
            self.driver.save_screenshot('selenium_buyer_page_finish.png')
            return

        # confirm purchase

        try:
            self.driver.find_element_by_xpath('//button[@data-test-id="CONFIRM_AND_PAY_BUTTON"]').click()

        except NoSuchElementException:
            print('Purchase confirm failed')
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            return

        return True

    @staticmethod
    def check_ship_info(ship_info):
        """ Check all necessary fields in ship_info dictionary """

        for field in 'first_name', 'last_name', 'address', 'city', 'region', 'zip_code', 'phone_number', 'count':
            try:
                ship_info[field]

            except KeyError:
                print('This ship_to field does not exists: {0}'.format(field))
                return False

        return True


if __name__ == '__main__':
    from json import loads

    with open('buyer_secret.json') as file:
        secret = loads(file.read())

    eb_credentials = (secret['eb_username'], secret['eb_password'])
    pp_credentials = (secret['pp_email'], secret['pp_password'])

    info = {
        'first_name': 'Azaza1',
        'last_name': 'Azaza2',
        'address': 'ololo address',
        'city': 'city',
        'region': 'Alabama',
        'zip_code': '33024',
        'phone_number': '0982438831',
        'count': '2'
    }

    buyer = SeleniumBuyer(eb_credentials, pp_credentials)
    buyer.purchase(223346308239, ship_info=info, confirm_purchase=False)
