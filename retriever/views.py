from django.http import HttpResponse
from django.template import loader
from bs4 import BeautifulSoup
import logging
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from datetime import datetime
import time
import pytz
from enum import Enum
import re

logger = logging.getLogger('django')


class EastonClassCategory(Enum):
    MMA = 1
    BJJ = 2
    STRIKING = 3
    WRESTLING = 4
    LITTLE_TIGERS = 5
    KIDS_BJJ = 6
    KIDS_STRIKING = 7
    CONDITIONING = 8
    YOGA = 9
    OTHER = 10
    KIDS_WRESTLING = 11
    NOT_SET = 12
    OPEN_GYM = 13
    PRIVATE_LESSON = 14


class EastonRequirements(Enum):
    YELLOW_SHIRT = 1
    ORANGE_SHIRT = 2
    GREEN_SHIRT = 3
    TWO_STRIPES = 4
    TWO_STRIPES_OR_WRESTLING_EXPERIENCE = 5
    GREEN_SHIRT_AND_FOUR_STRIPES = 6
    BLUE_BELT = 7
    PURPLE_BELT = 8
    NONE = 9
    UNKNOWN = 10
    INVITATION = 11
    YELLOW_BELT = 12


class EastonClass:
    def __init__(self):
        self.location = "Unspecified"
        self.category = "Unspecified"
        self.category_enum = EastonClassCategory.NOT_SET
        self.name = "Unspecified"
        self.requirements = EastonRequirements.UNKNOWN
        self.date = "Unspecified"
        self.start_time = "Unspecified"
        self.end_time = "Unspecified"
        self.full_start_time = None
        self.canceled = False


# TODO - clean up
def get_list_category(easton_class):
    if "Youth BJJ" in easton_class.category:
        easton_class.category_enum = EastonClassCategory.KIDS_BJJ
        easton_class.requirements = EastonRequirements.YELLOW_BELT
    elif "BJJ" in easton_class.category:
        easton_class.category_enum = EastonClassCategory.BJJ
        if "Randori" in easton_class.name:
            if "All Levels" in easton_class.name:
                easton_class.requirements = EastonRequirements.NONE
            else:
                easton_class.requirements = EastonRequirements.TWO_STRIPES
        if "Adv/Int" in easton_class.name or \
           "Intermediate" in easton_class.name:
            easton_class.requirements = EastonRequirements.TWO_STRIPES
        elif "Flow Roll" in easton_class.name or \
             "Fundamentals" in easton_class.name or \
             "Family" in easton_class.name or \
             "All Levels" in easton_class.name or \
             "All-levels" in easton_class.name:
            easton_class.requirements = EastonRequirements.NONE
    conditioning_pattern = re.compile(".*?Strength and Conditioning.*?")
    if conditioning_pattern.match(easton_class.category):
        easton_class.category_enum = EastonClassCategory.CONDITIONING
        easton_class.requirements = EastonRequirements.NONE
    open_gym_pattern = re.compile(".*?Open [Gg]ym.*?")
    if open_gym_pattern.match(easton_class.category):
        easton_class.category_enum = EastonClassCategory.OPEN_GYM
        easton_class.requirements = EastonRequirements.NONE
    if "Kids Muay Thai" in easton_class.category:
        easton_class.category_enum = EastonClassCategory.KIDS_STRIKING
        easton_class.requirements = EastonRequirements.NONE
    elif "Muay Thai" in easton_class.category or "Striking" in easton_class.category:
        easton_class.category_enum = EastonClassCategory.STRIKING
        if "Advanced" in easton_class.name:
            easton_class.requirements = EastonRequirements.ORANGE_SHIRT
        if "green shirt" in easton_class.name:
            easton_class.requirements = EastonRequirements.GREEN_SHIRT
        elif "Muay Thai" in easton_class.name or \
             "Thai Pad" in easton_class.name:
            easton_class.requirements = EastonRequirements.YELLOW_SHIRT
        elif "Kickboxing" in easton_class.name or \
             "Open Mat" in easton_class.name or \
             "Fundamentals of Striking" in easton_class.name:
            easton_class.requirements = EastonRequirements.NONE
        elif "Invite Only" in easton_class.name:
            easton_class.requirements = EastonRequirements.INVITATION
    little_tigers_pattern = re.compile(".*?Little [Tt]igers.*?")
    if little_tigers_pattern.match(easton_class.category):
        easton_class.category_enum = EastonClassCategory.LITTLE_TIGERS
        easton_class.requirements = EastonRequirements.NONE
    elif "Tigers" in easton_class.category:
        easton_class.requirements = EastonRequirements.NONE
    kids_wrestling_pattern = re.compile(".*?Wrestling [Ff]or [Yy]outh.*?")
    if kids_wrestling_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.KIDS_WRESTLING
        easton_class.requirements = EastonRequirements.NONE


# TODO - clean up
def get_calendar_category(easton_class):
    bjj_pattern = re.compile(".*?([Rr]andori|BJJ|No-Gi).*?")
    if bjj_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.BJJ
    private_lesson_pattern = re.compile(".*?Private Lesson.*?")
    if private_lesson_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.PRIVATE_LESSON
    muay_thai_pattern = re.compile(".*?(Muay [Tt]hai|[Kk]ickboxing).*?")
    if muay_thai_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.STRIKING
    kids_muay_thai_pattern = re.compile(".*?Kids [Mm]uay [Tt]hai.*?")
    if kids_muay_thai_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.KIDS_STRIKING
    kids_muay_thai_pattern = re.compile(".*?Little Tigers.*?")
    if kids_muay_thai_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.LITTLE_TIGERS
    kids_bjj_pattern = re.compile(".*?Tigers.*?")
    if easton_class.location == "Thornton" and kids_bjj_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.KIDS_BJJ

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
        get_calendar_category(easton_class)
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
            get_list_category(easton_class)
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
