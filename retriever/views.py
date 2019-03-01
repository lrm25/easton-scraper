from django.http import HttpResponse
from django.template import loader
from bs4 import BeautifulSoup
import logging
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from datetime import datetime
import time
import pytz

logger = logging.getLogger('django')


class EastonClass:
    def __init__(self):
        location = "Unspecified"
        category = "Unspecified"
        name = "Unspecified"
        date = "Unspecified"
        start_time = "Unspecified"
        end_time = "Unspecified"
        full_start_time = None


#
# Scrape class data from gyms that use zencalendar
#
# params:
# gym_location:  string representing gym location ("Castle Rock", etc.)
# webpage_location:  calendar webpage URL
# added_class_list:  reference to list of classes found over all gyms so far, function adds to this
#
def get_calendar_daily_data(gym_location, webpage_location, added_class_list):

    easton_request = Request(webpage_location, headers={'User-Agent': 'lmccrone'})
    schedule = urlopen(easton_request)
    soup = BeautifulSoup(schedule.read())
    today_date = datetime.now(pytz.timezone('US/Mountain')).strftime('%Y-%m-%d')
    today_schedule = soup.find('div', {'date': today_date})
    calendar_classes = today_schedule.find_all('div', {'class': 'item'})
    # strip string "calendar.cfm" (12 chars)
    webpage_base = webpage_location[:-12]
    for calendar_class in calendar_classes:

        # Class info URL query is in single quotes in 'onclick' attribute
        class_link_attr = calendar_class.get('onclick')
        logger.info("CLASS LINK ATTR: " + class_link_attr)
        class_link_query = class_link_attr.split('\'')[1]
        class_info_request = Request(webpage_base + class_link_query)
        class_info = urlopen(class_info_request)
        class_soup = BeautifulSoup(class_info.read())
        class_rows = class_soup.find_all('tr')
        class_time = ""
        for class_row in class_rows:
            if class_row.find('td').text == 'Time':
                class_time = class_row.find('td', {'class': 'bold'}).text
                break

        easton_class = EastonClass()
        easton_class.location = gym_location
        easton_class.category = calendar_class.get('class')[2]
        easton_class.name = calendar_class.text
        easton_class.date = today_date
        class_time_list = class_time.split(" - ")
        easton_class.start_time = class_time_list[0]
        easton_class.end_time = class_time_list[1]
        easton_class.full_start_time = time.strptime(
            easton_class.date + ' ' + easton_class.start_time, '%Y-%m-%d %I:%M %p')
        added_class_list.append(easton_class)


#
# Get class data from a MindBody daily page
#
# params:
# gym_location:  string representing gym location ("Centennial", "Boulder", etc.)
# webpage_location:  easton page for daily schedule
# added_class_list:  reference to current list of easton classes, function adds what it finds to this
#
def get_mb_daily_data(gym_location, webpage_location, added_class_list):
    # Pull the main schedule page on easton's website to get the internal MindBody link
    easton_request = Request(webpage_location, headers={'User-Agent': "lmccrone"})
    schedule = urlopen(easton_request)
    soup = BeautifulSoup(schedule.read())
    today_date = datetime.now(pytz.timezone('US/Mountain')).strftime('%Y-%m-%d')
    schedule_id = soup.find_all('healcode-widget')[0]['data-widget-id']
    logger.info("FOUND:  %s" % soup.find_all(schedule_id))

    # Pull the MindBody data directly (this string is called using js on easton's page)
    request_str = "https://widgets.healcode.com/widgets/schedules/" + schedule_id + "/print"
    mind_body_request = Request(request_str)
    schedule = urlopen(mind_body_request)
    soup = BeautifulSoup(schedule.read())
    table_rows = soup.find_all('tr')
    current_category = ""
    for table_row in table_rows:
        logger.info(table_row)

        if 'hc_class' in table_row.get('class'):
            easton_class = EastonClass()
            easton_class.location = gym_location
            easton_class.category = current_category
            easton_class.name = table_row.find('span', {'class': 'classname'}).text
            easton_class.date = today_date
            easton_class.start_time = table_row.find('span', {'class': 'hc_starttime'}).text
            # [2:] - remove dash at beginning of end time
            easton_class.end_time = table_row.find('span', {'class': 'hc_endtime'}).text[2:]
            easton_class.full_start_time = time.strptime(
                easton_class.date + ' ' + easton_class.start_time, '%Y-%m-%d %I:%M %p')
            added_class_list.append(easton_class)

        # Class category divider
        if 'group_by_class_type' in table_row.get('class'):
            current_category = table_row.find('td').text


def get_raw_data(request):
    try:
        added_class_list = []
        get_mb_daily_data("Littleton", "https://eastonbjj.com/littleton/schedule", added_class_list)
        get_mb_daily_data("Denver", "https://eastonbjj.com/denver/schedule", added_class_list)
        get_mb_daily_data("Boulder", "https://eastonbjj.com/boulder/schedule", added_class_list)
        get_mb_daily_data("Centennial", "https://eastonbjj.com/centennial/schedule", added_class_list)
        get_mb_daily_data("Arvada", "https://eastonbjj.com/arvada/schedule", added_class_list)
        get_mb_daily_data("Aurora", "https://eastonbjj.com/aurora/schedule", added_class_list)
        get_calendar_daily_data("Castle Rock", 'https://etc-castlerock.sites.zenplanner.com/calendar.cfm',
                                added_class_list)
        get_calendar_daily_data("Thornton", 'https://eastonbjjnorth.sites.zenplanner.com/calendar.cfm',
                                added_class_list)
        template = loader.get_template('retriever/index.html')
        added_class_list.sort(key=lambda added_class: added_class.full_start_time)
        context = {
            'easton_classes': added_class_list
        }
    except HTTPError as e:
        logger.error(e.fp.read())
    return HttpResponse(template.render(context, request))
