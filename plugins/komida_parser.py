import datetime
import itertools
import logging
import os
import re
import sqlite3
import tempfile
import urllib.parse

import dateparser
import lxml.html
import pdfquery
import requests
from rtmbot.core import Job


# disable low-level pdfminer logging
logging.getLogger('pdfminer').setLevel(logging.WARNING)


def get_menu_url(campus):
    """
    Parse the komida 'Weekmenu' page to find the url to the latest pdf menu for komida Middelheim.

    Args:
        campus: The campus for which the pdf menu has to be retrieved. Can be either `cmi` for Campus Middelheim, `cde`
                for Campus Drie Eiken, `cgb` for Campus Groenenborger, or `cst` for the City Campus.

    Returns:
        The menu url of the specified campus.

    Raises:
        `requests.HTTPError`: The 'Weekmenu' page could not be retrieved.
        `LookupError`: The requested menu url could not be found on the 'Weekmenu' page.
    """
    base_url = 'https://www.uantwerpen.be/nl/campusleven/eten/weekmenu/'
    campus_id = {'cmi': 'Campus Middelheim', 'cde': 'Campus Drie Eiken',
                 'cgb': 'Campus Groenenborger', 'cst': 'Stadscampus'}

    # find the menu for the specified campus
    logging.debug("Load the general 'Weekmenu' page")
    r_komida = requests.get(base_url)
    r_komida.raise_for_status()

    try:
        page = lxml.html.fromstring(r_komida.content)
        url = page.xpath('//h2[contains(text(), "{}")]/following::p[1]/a/@href'.format(campus_id[campus]))[0]
        url = urllib.parse.urljoin('https://www.uantwerpen.be/', url)
        logging.debug('Retrieved menu url for campus {}: <{}>'.format(campus.upper(), url))

        return url
    except IndexError as e:
        raise LookupError('Error while parsing the HTML page: {}'.format(e))


def download_pdf(url):
    """
    Download the given url and save the content to a temporary file.

    Args:
        url: The url to download.

    Returns:
        A file pointer to the temporary file where the url's contents were saved.

    Raises:
        `requests.HTTPError`: The pdf could not be retrieved.
    """
    logging.debug('Download the menu PDF')
    r_pdf = requests.get(url)
    r_pdf.raise_for_status()  # check whether the pdf was correctly downloaded

    # write the pdf to a temporary file
    logging.debug('Save the menu PDF to a temporary file')
    fp = tempfile.TemporaryFile()
    fp.write(r_pdf.content)
    fp.seek(0)

    return fp


def parse_pdf(f_pdf, campus):
    """
    Parse the menu items from the menu PDF.

    Args:
        f_pdf: File pointer to the menu PDF.
        campus: Campus for which the given PDF contains the menu.

    Returns:
        A dictionary of the menu in the form (date, campus, menu_type) -> (menu_item, price_student, price_staff).
    """
    bbox = {'date': (415, 750, 750, 775),
            'menu_items': {(0, 'soup'): ((90, 640, 235, 700), (230, 640, 285, 700)),
                           (0, 'vegetarian'): ((90, 590, 235, 650), (230, 590, 285, 650)),
                           (0, 'meat'): ((90, 535, 235, 600), (230, 535, 285, 600)),
                           (2, 'soup'): ((90, 435, 235, 495), (230, 435, 285, 495)),
                           (2, 'vegetarian'): ((90, 385, 235, 445), (230, 385, 285, 445)),
                           (2, 'meat'): ((90, 335, 235, 395), (230, 335, 285, 395)),
                           (4, 'soup'): ((90, 235, 235, 290), (230, 235, 285, 290)),
                           (4, 'vegetarian'): ((90, 185, 235, 245), (230, 185, 285, 245)),
                           (4, 'meat'): ((90, 130, 235, 195), (230, 130, 285, 195)),
                           (1, 'soup'): ((350, 640, 485, 700), (480, 640, 555, 700)),
                           (1, 'vegetarian'): ((350, 590, 485, 650), (480, 590, 555, 650)),
                           (1, 'meat'): ((350, 535, 485, 600), (480, 535, 555, 600)),
                           (3, 'soup'): ((350, 435, 485, 495), (480, 435, 555, 495)),
                           (3, 'vegetarian'): ((350, 385, 485, 445), (480, 385, 555, 445)),
                           (3, 'meat'): ((350, 335, 485, 395), (480, 335, 555, 395)),
                           (None, 'grill'): ((350, 185, 485, 245), (480, 185, 555, 245)),
                           (None, 'pasta'): ((350, 130, 485, 205), (480, 130, 555, 205))}}

    # load the pdf
    logging.debug('Load the menu PDF')
    pdf = pdfquery.PDFQuery(f_pdf)
    pdf.load(0)

    # parse the menu's date
    logging.debug('Parse the menu date')
    week = pdf.pq('LTTextLineHorizontal:in_bbox("{},{},{},{}")'.format(*bbox['date'])).text()
    end_date = dateparser.parse(re.split('-|tot|tem', week)[1], languages=['nl'])\
        .replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    # parse the menu items
    logging.debug('Parse the individual menu items and assign to specific dates')
    menu = {}
    for (date_key, menu_type), (bb_menu, bb_price) in bbox['menu_items'].items():
        # figure out the date(s) for the selected menu item
        if date_key is not None:
            dates = [end_date - datetime.timedelta(end_date.weekday() - date_key)]
        else:
            # repeat weekly menu items for each day of the week
            dates = [end_date - datetime.timedelta(end_date.weekday() - d) for d in range(5)]

        # parse the menu item
        menu_item = pdf.pq('LTTextLineHorizontal:in_bbox("{},{},{},{}")'.format(*bb_menu)).text()
        price = pdf.pq('LTTextLineHorizontal:in_bbox("{},{},{},{}")'.format(*bb_price)).text()
        price = [float(p.replace(',', '.')) for p in re.findall('[\d,]+', price)]

        # verify that we parsed the student as well as the staff price
        if len(price) < 2:
            logging.warning('Error parsing the menu; unexpected price format: {} - {}'.format(menu_type, price))
            continue

        # check if there are multiple menu options under the same category
        num_items = len(price) / 2
        # multiple options are only possible for selected pasta and grill menus
        if num_items > 1 and (menu_type == 'pasta' or (menu_type == 'grill' and campus == 'cst')):
            menu_items = re.split(' & | of ', menu_item)
            # the split is correct if it results in 2 menu items, don't do anything in this case
            # however, if there are more than 2 items one (or more) of the items was individually split as well
            # try to merge split items using the heuristic that both menu items should be roughly equally long
            if len(menu_items) > 2:
                len_middle = len(menu_item) / 2
                cum_len = [len(sub_item) for sub_item in [' of '.join(menu_items[:i]) for i in range(1, len(menu_items) + 1)]]
                best_split_idx = min(enumerate(cum_len), key=lambda l: abs(l[1] - len_middle))[0] + 1
                menu_items = [' of '.join(menu_items[: best_split_idx]), ' of '.join(menu_items[best_split_idx:])]
        else:
            menu_items = [menu_item]

        for date, (i, item) in itertools.product(dates, enumerate(menu_items)):
            menu[(date, campus, '{}{}'.format(menu_type, i + 1 if len(menu_items) > 1 else ''))] = (item, price[i * 2], price[i * 2 + 1])

    return menu


def store_menu(menu):
    """
    Store the given menu items in the database.

    Args:
        menu: A dictionary of the menu in the form (date, campus, menu_type) -> (menu_item, price_student, price_staff).
    """
    conn = sqlite3.connect('menu.db')
    c = conn.cursor()

    logging.debug('Store the menu items in the database')
    for (date, campus, menu_type), (menu_item, price_student, price_staff) in menu.items():
        try:
            c.execute('INSERT INTO menu VALUES (?, ?, ?, ?, ?, ?)',
                      (date, campus, menu_type, menu_item, price_student, price_staff))
        except sqlite3.IntegrityError as e:
            # this menu item is already present in the database
            logging.debug('Could not insert into the menu database: {}'.format(e))

    conn.commit()
    conn.close()


def update_menus():
    """
    Retrieve the latest menus for campuses CDE, CMI, and CST and store the individual menu items in the database.
    """
    for campus in ('cde', 'cmi', 'cst'):
        try:
            # retrieve the latest menu from the website
            menu_url = get_menu_url(campus)
            with download_pdf(menu_url) as f_pdf:
                # parse the menu from the pdf
                menu = parse_pdf(f_pdf, campus)
                # store the menu in the database
                store_menu(menu)
        except (requests.HTTPError, LookupError) as e:
            logging.error('Could not retrieve the menu for campus {}: {}'.format(campus.upper(), e))


def init_database():
    """
    Initialize the menu items database.

    The database contains a single `menu` table of the form `(date, campus, menu_type, menu_item, price_student, price_staff)`.
    """
    conn = sqlite3.connect('menu.db')
    c = conn.cursor()

    c.execute('CREATE TABLE menu (date TIMESTAMP, campus TEXT, type TEXT, item TEXT, '
              'price_student REAL, price_staff REAL, PRIMARY KEY(date, campus, type))')

    conn.commit()
    conn.close()


class KomidaUpdate(Job):

    def run(self, slack_client):
        # create the database if needed
        if not os.path.exists('menu.db'):
            init_database()

        # update the menu
        update_menus()

        # expects an iterable
        return []
