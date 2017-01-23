import datetime
import itertools
import locale
import logging
import tempfile
import urllib.parse

import lxml.html
import pdfquery
import requests

import private


def get_menu_url():
    """
    Parse the komida 'Weekmenu' page to find the url to the latest pdf menu for komida Middelheim.

    Returns:
        The url of the komida Middelheim menu.

    Raises:
        `requests.HTTPError`: The 'Weekmenu' page could not be retrieved.
    """
    base_url = 'https://www.uantwerpen.be/nl/campusleven/eten/weekmenu/'

    # find the menu for komida Middelheim
    r_komida = requests.get(base_url)
    r_komida.raise_for_status()

    page = lxml.html.fromstring(r_komida.content)
    url = page.xpath("//h2[contains(text(), 'Campus Middelheim')]/following::p[1]/a/@href")[0]

    return urllib.parse.urljoin('https://www.uantwerpen.be/', url)

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
    r_pdf = requests.get(url)
    r_pdf.raise_for_status()  # check whether the pdf was correctly downloaded

    # write the pdf to a temporary file
    fp = tempfile.TemporaryFile()
    fp.write(r_pdf.content)
    fp.seek(0)

    return fp

def get_menu_today(fp):
    """
    Retrieve the menu from the formatted pdf.

    Parsing the menu requires specific formatting of the pdf according to the komida style.

    Args:
        fp: File pointer to the menu pdf.

    Returns:
        A list of individual items on today's menu (both daily and weekly items).

    Raises:
        ValueError: Today's date does not correspond to the week advertised on the menu.
    """
    # bounding box locations of all menu items for each of the different days
    bboxes = {0: [(95, 655, 230, 695), (95, 595, 230, 655), (95, 535, 230, 595)],
              2: [(95, 450, 230, 490), (95, 390, 230, 450), (95, 330, 230, 390)],
              4: [(95, 245, 230, 285), (95, 185, 230, 245), (95, 125, 230, 185)],
              1: [(355, 655, 490, 695), (355, 595, 485, 655), (355, 535, 490, 595)],
              3: [(355, 450, 490, 490), (355, 390, 485, 450), (355, 330, 490, 390)],
              'all': [(355, 185, 485, 245), (355, 125, 490, 185)],
              'date': (425, 755, 550, 775)}

    # parse the pdf
    pdf = pdfquery.PDFQuery(fp)
    pdf.load(0)

    # check whether this is this week's menu
    locale.setlocale(locale.LC_ALL, 'nl_BE')  # parse the date in Dutch
    week = pdf.pq('LTTextLineHorizontal:in_bbox("{},{},{},{}")'.format(*bboxes['date'])).text()
    end_date = datetime.datetime.strptime(week[week.find('tot') + 4:], '%d %B %Y') + datetime.timedelta(days=1)
    if (end_date - datetime.datetime.today()).days > 4:
        raise ValueError('Incorrect date; menu for: {}'.format(week))

    # extract today's menu (including the weekly fixed menu items)
    menu = [pdf.pq('LTTextLineHorizontal:in_bbox("{},{},{},{}")'.format(*bbox)).text()
            for bbox in itertools.chain(bboxes[datetime.datetime.today().weekday()], bboxes['all'])]

    return menu

def post_to_slack(menu, url):
    """
    Post the prettily formatted menu to Slack.

    Args:
        menu: List of individual items on today's menu.
        url: Location of the original menu pdf.

    Raises:
        `requests.HTTPError`: The Slack message could not be posted.
    """
    message = '*LUNCH!*\n:tea: {}\n:tomato: {}\n:poultry_leg: {}\n:meat_on_bone: {}\n:spaghetti: {}\n' \
              '<{}|Check the menu here.> Mistakes, comments, suggestions, ...? Please contact @wout.' \
        .format(*menu, url)

    r_slack = requests.post(private.webhook, json={'username': 'lunchbot', 'icon_emoji': ':hodor:', 'text': message})
    r_slack.raise_for_status()    # check whether the message was correctly posted


if __name__ == '__main__':
    # initialize logging
    logging.basicConfig(format='%(asctime)s [%(levelname)s/%(processName)s] %(module)s.%(funcName)s : %(message)s',
                        level=logging.WARN)

    try:
        # only post the menu on weekdays
        if datetime.datetime.today().weekday() < 5:
            menu_url = get_menu_url()
            with download_pdf(menu_url) as f_pdf:
                menu_list = get_menu_today(f_pdf)
                post_to_slack(menu_list, menu_url)

    except (requests.HTTPError, ValueError) as e:
        logging.error(e)

    logging.shutdown()
