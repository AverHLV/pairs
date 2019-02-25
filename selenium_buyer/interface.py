from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from time import sleep
from re import sub
from config.constants import chromedriver_path


class SeleniumBuyer(object):
    """ Selenium automatic eBay item buyer powered by Chrome in headless mode """

    login_url = 'https://signin.ebay.com/ws/eBayISAPI.dll'
    login_cb_url = 'https://www.topcashback.com/home'
    item_page_url = 'https://www.ebay.com/itm/{0}'
    seller_message = 'Dear seller, please put no price tags or ads at the package. I will be grateful!'

    def __init__(self, credentials, payment_cred, cashback_cred=None, driver_path=chromedriver_path,
                 wait_page_load_delay=10, wait_frequency=2, headless=True, login_to_cb=False):
        options = Options()

        if headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')

        try:
            self.driver = webdriver.Chrome(driver_path, chrome_options=options)

        except IOError:
            raise ValueError('Specified webdriver file does not exists: {0}'.format(driver_path))

        self.page_load_delay = wait_page_load_delay
        self.wait = WebDriverWait(self.driver, self.page_load_delay, poll_frequency=wait_frequency)
        self.payment_credentials = payment_cred

        if login_to_cb and cashback_cred is not None:
            self.login_to_cb(cashback_cred)
        else:
            self.login_to_ebay(credentials)

    def wait_for_element(self, find_by, find_param, raise_exc=True, wait_after=False):
        """
        Wait with self.page_load_delay for specified element on the current page

        :param find_by: search type (id, class or xpath)
        :param find_param: search parameter relative to search type
        :param raise_exc: raise PurchaseStoppedException if element not found or not
        :param wait_after: wait self.page_load_delay after element is clickable
        :return: DOM element or None
        """

        if find_by == 'id':
            find_by = By.ID

        elif find_by == 'xpath':
            find_by = By.XPATH

        elif find_by == 'class':
            find_by = By.CLASS_NAME

        else:
            raise PurchaseStoppedException('Wrong find type: {0}'.format(find_by))

        # wait with delay until element loaded

        try:
            element = self.wait.until(ec.visibility_of_element_located((find_by, find_param)))

        except TimeoutException:
            if raise_exc:
                self.driver.save_screenshot('selenium_buyer_page_exc.png')
                raise PurchaseStoppedException('Not found: {0}, delay: {1}'.format(find_param, self.page_load_delay))

            return

        if wait_after:
            sleep(self.page_load_delay)

        return element

    def login_to_cb(self, credentials):
        """ Log in to cashback service and proceed to eBay """

        self.driver.get(self.login_cb_url)

        try:
            self.driver.find_element_by_id('txtEmail').send_keys(credentials[0])

            self.driver.find_element_by_xpath(
                '//input[@name="ctl00$GeckoOneColPrimary$LoginV2$txtPassword"]'
            ).send_keys(credentials[1])

        except NoSuchElementException:
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            raise PurchaseStoppedException('Login form inputs not found')

        self.wait_for_element('xpath', '//button[@name="ctl00$GeckoOneColPrimary$LoginV2$Loginbtn"]').click()

    def login_to_ebay(self, credentials):
        """ Log in on eBay using given credentials """

        self.driver.get(self.login_url)

        try:
            elements = self.driver.find_elements_by_class_name('fld')

        except NoSuchElementException:
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            raise PurchaseStoppedException('Login form inputs not found')

        elements[2].send_keys(credentials[0])
        elements[3].send_keys(credentials[1])

        self.wait_for_element('id', 'sgnBt').click()

    def choose_paypal(self):
        """ Choose PayPal as payment option on purchase details page """

        self.driver.find_element_by_xpath('//input[@value="PAYPAL"]').click()

        # switch to opened log in window

        self.driver.switch_to.window(self.driver.window_handles[1])
        self.wait_for_element('id', 'email').send_keys(self.payment_credentials[0])
        sleep(self.page_load_delay)

        try:
            self.driver.find_element_by_id('password').send_keys(self.payment_credentials[1])
            self.driver.find_element_by_id('btnLogin').click()

        except NoSuchElementException:
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            raise PurchaseStoppedException('Payment method choosing failed')

        # click 'Remember Me' if exists

        sleep(self.page_load_delay)
        button = self.wait_for_element('xpath', '//button[@value="acceptRememberMe"]', raise_exc=False)

        if button is not None:
            button.click()

        sleep(self.page_load_delay)
        self.driver.switch_to.window(self.driver.window_handles[0])

    def purchase(self, ebay_id, ship_info, confirm_purchase=True):
        """ Open, fill and submit eBay item purchase form """

        self.check_ship_info(ship_info)
        self.driver.get(self.item_page_url.format(ebay_id))

        # set quantity

        quantity_area = self.wait_for_element('class', 'qtyInput')
        quantity_area.clear()
        quantity_area.send_keys(ship_info['count'])

        self.wait_for_element('id', 'binBtn_btn').click()

        # fill and submit ship to form

        self.wait_for_element('xpath', '//a[@data-test-id="EXPAND_SHIPPING_ADDRESSES"]').click()
        self.wait_for_element('xpath', '//a[contains(text(), "Add a new address")]').click()

        # wait for ship to form loading

        self.wait_for_element('id', 'firstName').send_keys(ship_info['first_name'])

        try:
            self.driver.find_element_by_id('lastName').send_keys(ship_info['last_name'])
            self.driver.find_element_by_id('addressLine1').send_keys(ship_info['AddressLine1'])
            self.driver.find_element_by_id('city').send_keys(ship_info['City'])
            self.driver.find_element_by_id('postalCode').send_keys(ship_info['PostalCode'])
            self.driver.find_element_by_id('phoneNumber').send_keys(ship_info['Phone'])

            region = self.driver.find_element_by_xpath('//select[@id="stateOrProvince"]/option[text()="{0}"]'
                                                       .format(ship_info['StateOrRegion']))
            region.click()

            self.driver.find_element_by_xpath('//button[@data-test-id="ADD_ADDRESS_SUBMIT"]').click()

        except NoSuchElementException as e:
            self.driver.save_screenshot('selenium_buyer_page_exc.png')
            raise PurchaseStoppedException('Ship to form element not found: {0}'.format(e))

        button = self.wait_for_element(
            'xpath', '//div[@data-test-id="SHIPPING_ADDRESS_RECOMMENDATION_SUBMIT"]/button', raise_exc=False
        )

        if button is not None:
            button.click()

        # message for seller

        self.wait_for_element('xpath', '//a[@data-test-id="MESSAGE_TO_SELLER_OPEN"]', wait_after=True).click()

        self.wait_for_element(
            'xpath', '//textarea[@data-test-id="MESSAGE_TO_SELLER_TEXT_AREA"]'
        ).send_keys(self.seller_message)

        self.driver.find_element_by_xpath('//button[@data-test-id="MESSAGE_TO_SELLER_SUBMIT"]').click()

        # choose payment method if not chosen yet

        element = self.wait_for_element('xpath', '//span[text()="{0}"]'.format(self.payment_credentials[0]),
                                        raise_exc=False)

        if element is None:
            try:
                button = self.driver.find_element_by_xpath('//a[@data-test-id="SHOW_MORE"]')

            except NoSuchElementException:
                self.choose_paypal()

            else:
                button.click()
                self.choose_paypal()

        # order total price

        total = self.wait_for_element(
            'xpath', '//tr[@data-test-id="TOTAL"]/td[@class="amount"]/span[@class="text-display"]'
        )

        if total is None:
            total = 0
        else:
            try:
                total = float(sub('[^0-9.]', '', total.text))

            except ValueError:
                total = 0

        if not confirm_purchase:
            print('Done. Total: {0}, ebay id: {1}'.format(total, ebay_id))
            return total

        # confirm purchase

        self.wait_for_element('xpath', '//button[@data-test-id="CONFIRM_AND_PAY_BUTTON"]').click()
        return total

    @staticmethod
    def check_ship_info(ship_info):
        """ Check all necessary fields in ship_info dictionary """

        for field in 'first_name', 'last_name', 'AddressLine1', 'City', 'StateOrRegion', 'PostalCode', 'Phone', 'count':
            try:
                ship_info[field]

            except KeyError:
                raise PurchaseStoppedException('This ship_to field does not exists: {0}'.format(field))


class PurchaseStoppedException(Exception):
    """ Exception that indicates purchase process failure """

    def __init__(self, message=None):
        self.message = message

    def __str__(self):
        if self.message is None:
            return 'Purchase process stopped with empty message.'

        return self.message


if __name__ == '__main__':
    from json import loads

    try:
        with open('buyer_secret.json') as file:
            secret = loads(file.read())

    except IOError as ex:
        secret = None
        print('Secret file not found: {0}'.format(ex))
        exit()

    eb_credentials = (secret['eb_username'], secret['eb_password'])
    pp_credentials = (secret['pp_email'], secret['pp_password'])

    info = {
        'first_name': 'Amy',
        'last_name': 'Cross',
        'AddressLine1': '217 booter ln',
        'City': 'Chazy',
        'StateOrRegion': 'New York',
        'PostalCode': '12921',
        'Phone': '8023932181',
        'count': '11'
    }

    buyer = SeleniumBuyer(eb_credentials, pp_credentials, headless=True)
    buyer.purchase(254078382930, ship_info=info, confirm_purchase=False)
