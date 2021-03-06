from django.http import HttpResponse
from . import models
from django.template import loader
from bs4 import BeautifulSoup
import logging
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from datetime import datetime, timedelta
import time
import pytz
from enum import Enum
import re

logger = logging.getLogger('django')


def for_django(cls):
    cls.do_not_call_in_templates = True
    return cls


@for_django
class EastonGym(Enum):
    ARVADA = 1
    AURORA = 2
    BOULDER = 3
    CASTLE_ROCK = 4
    CENTENNIAL = 5
    DENVER = 6
    LITTLETON = 7
    THORNTON = 8


@for_django
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


@for_django
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
    NOT_SET = 10
    INVITATION = 11
    YELLOW_BELT = 12
    SOLID_GREY_BELT = 13
    OVER_200_LBS = 14
    TWO_STRIPES_AND_UNDER_160_LBS = 15
    OVER_40_YEARS_OLD = 16
    FEMALE = 17
    GREY_WHITE_BELT = 18
    BLUE_SHIRT = 19


class EastonMbCalendarPage:

    def __init__(self, location, page_url):
        self._location = location
        self._page_url = page_url

    #
    # Get the schedule ID for the inner MindBody calendar
    # (Easton's page has a javascript link which loads the schedule, we have to connect to mindbody's site
    #  with this ID to get the class data)
    def get_inner_mbc_id(self):
        easton_request = Request(self._page_url, headers={'User-Agent': "lmccrone"})
        schedule = urlopen(easton_request)
        soup = BeautifulSoup(schedule.read())
        schedule_id = soup.find_all('healcode-widget')[0]['data-widget-id']
        return schedule_id


class MindBodyCalendar:

    def __init__(self, location, main_page):
        self._location = location
        self._main_page = main_page

    def get_class_data(self, first_date, number_of_days=1):

        # Pull the main schedule page on easton's website to get the internal MindBody link schedule ID
        easton_request = Request(self._main_page, headers={'User-Agent': "lmccrone"})
        schedule = urlopen(easton_request)
        soup = BeautifulSoup(schedule.read())
        schedule_id = soup.find_all('healcode-widget')[0]['data-widget-id']
        request_str = "https://widgets.healcode.com/widgets/schedules/" + schedule_id + "/print"

        gym_class_list = []
        for day_number in range(number_of_days):
            logger.info("TIMEDELTA:  " + str(day_number))
            # Call MindBody widget with the schedule ID and the specific day
            day_calendar = MindBodyDailyCalendar(self._location, request_str, first_date + timedelta(days=day_number))
            gym_class_list.extend(day_calendar.get_class_data())
            logger.info("TOTAL SIZE:  " + str(len(gym_class_list)))
        return gym_class_list


class MindBodyDailyCalendar:

    def __init__(self, location, webpage, date):
        self._location = location
        self._webpage = webpage
        self._date = date

    def get_class_data(self):
        request_str = self._webpage + "?options%5Bstart_date%5D=" + datetime.strftime(self._date, "%Y-%m-%d")
        logger.info("REQUEST_STR: " + request_str)
        mind_body_request = Request(request_str)
        schedule = urlopen(mind_body_request)
        soup = BeautifulSoup(schedule.read())
        table_rows = soup.find_all('tr')
        current_category = ""
        daily_class_list = []

        for table_row in table_rows:
            logger.info(table_row)

            if 'hc_class' in table_row.get('class'):
                easton_class = EastonClass()
                easton_class.id = table_row.get('data-hc-mbo-class-id')
                easton_class.location = self._location
                easton_class.category = current_category
                easton_class.name = table_row.find('span', {'class': 'classname'}).text
                easton_class.date = datetime.strftime(self._date, "%Y-%m-%d")
                easton_class.start_time = table_row.find('span', {'class': 'hc_starttime'}).text
                # [2:] - remove dash at beginning of end time
                easton_class.end_time = table_row.find('span', {'class': 'hc_endtime'}).text[2:]
                easton_class.full_start_time = time.strptime(
                    easton_class.date + ' ' + easton_class.start_time, '%Y-%m-%d %I:%M %p %z')
                get_list_category(easton_class)
                daily_class_list.append(easton_class)

            # Class category divider
            if 'group_by_class_type' in table_row.get('class'):
                current_category = table_row.find('td').text

        logger.info("CLASS SIZE: " + str(len(daily_class_list)))
        return daily_class_list

#class EastonGym:
#    def __init__(self, location, calendar):

class EastonClass:
    def __init__(self):
        self.location = "Unspecified"
        self.category = "Unspecified"
        self.category_enum = EastonClassCategory.NOT_SET
        self.name = "Unspecified"
        self.requirements = EastonRequirements.NOT_SET
        self.date = "Unspecified"
        self.start_time = "Unspecified"
        self.end_time = "Unspecified"
        self.full_start_time = None
        self.canceled = False
        self.id = None


def retrieve_data(request):
    models.retrieve_data_from_web(models.NUMBER_RETRIEVAL_DAYS)
    # NOTE:  let django return error if there's a failure
    return HttpResponse("<html><title>Success</title><body>{}</body></html>".format("Retrieval successful"))


# TODO - clean up
# TODO - combine with other
def get_list_category(easton_class):

    c = easton_class.category
    n = easton_class.name

    # TODO - comment each section
    if "Youth BJJ" in c:
        if "Lil Yeti" in n:
            easton_class.category_enum = EastonClassCategory.LITTLE_TIGERS
            easton_class.requirements = EastonRequirements.NONE
        elif "Yeti" in n:
            easton_class.category_enum = EastonClassCategory.KIDS_BJJ
            easton_class.requirements = EastonRequirements.NONE
        else:
            easton_class.category_enum = EastonClassCategory.KIDS_BJJ
            easton_class.requirements = EastonRequirements.YELLOW_BELT
    elif "BJJ" in c or \
         (not c and ("BJJ" in n and not "Tiger" in n)):
        # I put some of these into different categories.  Split them off first.
        if "Wrestling" in n:
            easton_class.category_enum = EastonClassCategory.WRESTLING
            easton_class.requirements = EastonRequirements.TWO_STRIPES_OR_WRESTLING_EXPERIENCE
        elif "Yoga" in n:
            easton_class.category_enum = EastonClassCategory.YOGA
            easton_class.requirements = EastonRequirements.NONE
        elif "MMA" in n:
            easton_class.category_enum = EastonClassCategory.MMA
            easton_class.requirements = EastonRequirements.GREEN_SHIRT_AND_FOUR_STRIPES
        else:
            easton_class.category_enum = EastonClassCategory.BJJ
            if "Beware" in n:
                easton_class.requirements = EastonRequirements.PURPLE_BELT
            elif "Advanced" in n:
                easton_class.requirements = EastonRequirements.BLUE_BELT
            elif "Randori" in n:
                if "All Levels" in n:
                    easton_class.requirements = EastonRequirements.NONE
                elif "160" in n:
                    easton_class.requirements = EastonRequirements.TWO_STRIPES_AND_UNDER_160_LBS
                elif "40" in n:
                    easton_class.requirements = EastonRequirements.OVER_40_YEARS_OLD
                else:
                    easton_class.requirements = EastonRequirements.TWO_STRIPES
            elif "Competition Training" in n:
                easton_class.requirements = EastonRequirements.TWO_STRIPES
            elif "Adv/Int" in n or \
                    ("Intermediate" in n and "Fundamentals" not in n):
                easton_class.requirements = EastonRequirements.TWO_STRIPES
            elif "200" in n:
                easton_class.requirements = EastonRequirements.OVER_200_LBS
            elif "Women" in n:
                easton_class.requirements = EastonRequirements.FEMALE
            # TODO set c and n to lowercase
            elif "Flow Roll" in n or \
                "Fundamentals" in n or \
                    "Family" in n or \
                    "All Levels" in n or \
                    "All-levels" in n or \
                    "All levels" in n or \
                    "Intro" in n or "Int/Fund" in n:
                easton_class.requirements = EastonRequirements.NONE
    conditioning_pattern = re.compile(".*?Strength and Conditioning.*?")
    if conditioning_pattern.match(easton_class.category):
        easton_class.category_enum = EastonClassCategory.CONDITIONING
        easton_class.requirements = EastonRequirements.NONE
    open_gym_pattern = re.compile(".*?Open [Gg]ym.*?")
    if open_gym_pattern.match(easton_class.category):
        easton_class.category_enum = EastonClassCategory.OPEN_GYM
        easton_class.requirements = EastonRequirements.NONE
    if "Kids Muay Thai" in c or "Youth Kick" in c:
        easton_class.category_enum = EastonClassCategory.KIDS_STRIKING
        easton_class.requirements = EastonRequirements.NONE
    elif "Kids" in c and "Tiger" not in c:
        easton_class.category_enum = EastonClassCategory.KIDS_BJJ
        if "Advanced" in n:
            easton_class.requirements = EastonRequirements.SOLID_GREY_BELT
        else:
            easton_class.requirements = EastonRequirements.NONE
    elif "Muay Thai" in c or "Striking" in c:
        easton_class.category_enum = EastonClassCategory.STRIKING
        if "blue shirt" in n:
            easton_class.requirements = EastonRequirements.BLUE_SHIRT
        elif "Competition" in n or "Sparring" in n or "green shirt" in n:
            easton_class.requirements = EastonRequirements.GREEN_SHIRT
        elif "Advanced" in n or "Intermediate" in n or "orange shirt" in n:
            easton_class.requirements = EastonRequirements.ORANGE_SHIRT
        elif "Muay Thai" in n or \
             "Thai Pad" in n or \
             "Clinch" in n:
            easton_class.requirements = EastonRequirements.YELLOW_SHIRT
        elif "Kickboxing" in n or \
             "Open Mat" in n or \
             "Fundamentals of Striking" in n or \
             "Teens" in n:
            easton_class.requirements = EastonRequirements.NONE
        elif "Invite Only" in n:
            easton_class.requirements = EastonRequirements.INVITATION
    elif "Open Mat" in c:
        easton_class.category_enum = EastonClassCategory.OPEN_GYM
        easton_class.requirements = EastonRequirements.NONE
    elif "Little Tigers" in c or (not c and "Little Tigers" in n):
        easton_class.category_enum = EastonClassCategory.LITTLE_TIGERS
        easton_class.requirements = EastonRequirements.NONE
    elif "Tigers" in c or (not c and ("Kids Martial Arts" in n or "Tiger" in n)):
        easton_class.category_enum = EastonClassCategory.KIDS_BJJ
        if "Invite-Only" in n:
            easton_class.requirements = EastonRequirements.INVITATION
        elif "Advanced" in n or \
                "Competition" in n:
            easton_class.requirements = EastonRequirements.SOLID_GREY_BELT
        elif "comp" in n:
            easton_class.requirements = EastonRequirements.GREY_WHITE_BELT
        else:
            easton_class.requirements = EastonRequirements.NONE
    elif "Seminar" in c and "Kids" in n:
        easton_class.category_enum = EastonClassCategory.KIDS_BJJ
        easton_class.requirements = EastonRequirements.NONE
    kids_wrestling_pattern = re.compile(".*?Wrestling [Ff]or [Yy]outh.*?")
    if kids_wrestling_pattern.match(n):
        easton_class.category_enum = EastonClassCategory.KIDS_WRESTLING
        easton_class.requirements = EastonRequirements.NONE
    elif "Pro Fight Team" in c:
        easton_class.category_enum = EastonClassCategory.MMA
        easton_class.requirements = EastonRequirements.INVITATION


# TODO - clean up
def get_calendar_category(easton_class):
    if "Fitness" in easton_class.name:
        easton_class.category_enum = EastonClassCategory.CONDITIONING
        easton_class.requirements = EastonRequirements.NONE
    bjj_pattern = re.compile(".*?([Rr]andori|B[Jj][Jj]|No(-| )Gi|Drilling).*?")
    if bjj_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.BJJ
        if "Teen BJJ" in easton_class.name:
            easton_class.requirements = EastonRequirements.INVITATION
        elif "Advanced" in easton_class.name:
            easton_class.requirements = EastonRequirements.BLUE_BELT
        elif ("Intermediate" in easton_class.name and "Fundamentals" not in easton_class.name) or \
             "Randori" in easton_class.name:
            easton_class.requirements = EastonRequirements.TWO_STRIPES
        elif "All Levels" in easton_class.name or \
             "Fundamentals" in easton_class.name or \
             "No Gi" in easton_class.name or \
             "No-Gi" in easton_class.name or \
             "Family" in easton_class.name or \
             "Drilling" in easton_class.name:
            easton_class.requirements = EastonRequirements.NONE
    private_lesson_pattern = re.compile(".*?Private Lesson.*?")
    if private_lesson_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.PRIVATE_LESSON
        easton_class.requirements = EastonRequirements.NONE
    muay_thai_pattern = re.compile(".*?(Muay [Tt]hai|[Kk]ickboxing).*?")
    if muay_thai_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.STRIKING
        if "Muay Thai" in easton_class.name:
            easton_class.requirements = EastonRequirements.YELLOW_SHIRT
        elif "Kickboxing" in easton_class.name:
            easton_class.requirements = EastonRequirements.NONE
    kids_muay_thai_pattern = re.compile(".*?Kids [Mm]uay [Tt]hai.*?")
    if kids_muay_thai_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.KIDS_STRIKING
        easton_class.requirements = EastonRequirements.NONE
    kids_muay_thai_pattern = re.compile(".*?Little Tigers.*?")
    if "Kids Competition" in easton_class.name:
        easton_class.category_enum = EastonClassCategory.KIDS_BJJ
        easton_class.requirements = EastonRequirements.YELLOW_BELT
    if kids_muay_thai_pattern.match(easton_class.name):
        easton_class.category_enum = EastonClassCategory.LITTLE_TIGERS
        easton_class.requirements = EastonRequirements.NONE
    elif "Tigers" in easton_class.name:
        easton_class.category_enum = EastonClassCategory.KIDS_BJJ
        easton_class.requirements = EastonRequirements.NONE


#
# Scrape class data from gyms that use zencalendar
#
# params:
# gym_location:  string representing gym location ("Castle Rock", etc.)
# webpage_location:  calendar webpage URL
# added_class_list:  reference to list of classes found over all gyms so far, function adds to this
#
def get_calendar_daily_data(gym_location, webpage_location, added_class_list, first_date, total_days=1):

    for day_number in range(total_days):
        date_string = (first_date + timedelta(days=day_number)).strftime("%Y-%m-%d")
        easton_request = Request(webpage_location+"?DATE="+date_string+"&VIEW=WEEK", headers={'User-Agent': 'lmccrone'})
        schedule = urlopen(easton_request)
        soup = BeautifulSoup(schedule.read())
        day_schedule = soup.find('div', {'date': date_string})
        calendar_classes = day_schedule.find_all('div', {'class': 'item'})
        # strip string "calendar.cfm" (12 chars)
        webpage_base = webpage_location[:-12]
        for calendar_class in calendar_classes:

            # Class info URL query is in single quotes in 'onclick' attribute
            # FORMAT:  onclick="checkLoggedId('enrollment.cfm?appointmentId=<id>')"
            class_link_attr = calendar_class.get('onclick')
            logger.info("CLASS LINK ATTR: " + class_link_attr)
            class_link_query = class_link_attr.split('\'')[1]
            class_id = class_link_query.split('?')[1].split('=')[1]
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
            easton_class.id = class_id
            easton_class.name = calendar_class.text
            easton_class.date = date_string
            class_time_list = class_time.split(" - ")
            easton_class.start_time = class_time_list[0]
            easton_class.end_time = class_time_list[1]
            easton_class.full_start_time = time.strptime(
                easton_class.date + ' ' + easton_class.start_time, '%Y-%m-%d %I:%M %p')
            get_calendar_category(easton_class)
            added_class_list.append(easton_class)


def get_raw_data(request):
    try:
        added_class_list = []
        today_date = datetime.now(pytz.timezone('US/Mountain'))

        #littleton_calendar = MindBodyCalendar("Littleton", "https://eastonbjj.com/littleton/schedule")
        #added_class_list.extend(littleton_calendar.get_class_data(today_date, 7))

        #denver_calendar = MindBodyCalendar("Denver", "https://eastonbjj.com/denver/schedule")
        #added_class_list.extend(denver_calendar.get_class_data(today_date, 7))

        #boulder_calendar = MindBodyCalendar("Boulder", "https://eastonbjj.com/boulder/schedule")
        #added_class_list.extend(boulder_calendar.get_class_data(today_date, 7))

        #centennial_calendar = MindBodyCalendar("Centennial", "https://eastonbjj.com/centennial/schedule")
        #added_class_list.extend(centennial_calendar.get_class_data(today_date, 7))

        #arvada_calendar = MindBodyCalendar("Arvada", "https://eastonbjj.com/arvada/schedule")
        #added_class_list.extend(arvada_calendar.get_class_data(today_date, 7))

        aurora_calendar = MindBodyCalendar("Aurora", "https://eastonbjj.com/aurora/schedule")
        added_class_list.extend(aurora_calendar.get_class_data(today_date, 7))

        #get_calendar_daily_data("Castle Rock", 'https://etc-castlerock.sites.zenplanner.com/calendar.cfm',
        #                        added_class_list, today_date, 7)
        #get_calendar_daily_data("Thornton", 'https://eastonbjjnorth.sites.zenplanner.com/calendar.cfm',
        #                        added_class_list, today_date, 7)
        template = loader.get_template('retriever/index.html')
        added_class_list.sort(key=lambda added_class: added_class.start_time)
        context = {
            'easton_classes': added_class_list
        }
    except HTTPError as e:
        logger.error(e.fp.read())
    return HttpResponse(template.render(context, request))


def get_class_list(today_date, gym_location):

    added_class_list = []

    logger.debug("GYM LOCATION:  " + gym_location)
    if gym_location == "EastonGym.LITTLETON":
        littleton_calendar = MindBodyCalendar("Littleton", "https://eastonbjj.com/littleton/schedule")
        added_class_list.extend(littleton_calendar.get_class_data(today_date, 7))

    elif gym_location == "EastonGym.DENVER":
        denver_calendar = MindBodyCalendar("Denver", "https://eastonbjj.com/denver/schedule")
        added_class_list.extend(denver_calendar.get_class_data(today_date, 7))

    elif gym_location == "EastonGym.BOULDER":
        boulder_calendar = MindBodyCalendar("Boulder", "https://eastonbjj.com/boulder/schedule")
        added_class_list.extend(boulder_calendar.get_class_data(today_date, 7))

    elif gym_location == "EastonGym.CENTENNIAL":
        centennial_calendar = MindBodyCalendar("Centennial", "https://eastonbjj.com/centennial/schedule")
        added_class_list.extend(centennial_calendar.get_class_data(today_date, 7))

    elif gym_location == "EastonGym.ARVADA":
        arvada_calendar = MindBodyCalendar("Arvada", "https://eastonbjj.com/arvada/schedule")
        added_class_list.extend(arvada_calendar.get_class_data(today_date, 7))

    elif gym_location == "EastonGym.AURORA":
        aurora_calendar = MindBodyCalendar("Aurora", "https://eastonbjj.com/aurora/schedule")
        added_class_list.extend(aurora_calendar.get_class_data(today_date, 7))

    elif gym_location == "EastonGym.CASTLE_ROCK":
        get_calendar_daily_data("Castle Rock", 'https://etc-castlerock.sites.zenplanner.com/calendar.cfm',
                                added_class_list, today_date, 7)

    elif gym_location == "EastonGym.THORNTON":
        get_calendar_daily_data("Thornton", 'https://eastonbjjnorth.sites.zenplanner.com/calendar.cfm',
                                added_class_list, today_date, 7)

    return added_class_list


def get_select_page(request):
    context = {
        'easton_class_type': models.EastonClassCategory,
        'easton_gym': models.EastonGym,
        'easton_requirements': models.EastonRequirements
    }
    template = loader.get_template('retriever/select.html')
    return HttpResponse(template.render(context, request))


def get_checks(request):

    # If no specific values are specified for a category, return all values for that category
    gym_list = [gym.split('.')[1] for gym in request.GET.getlist('gym')] if request.GET.get('gym') else \
        [str(e.name) for e in models.EastonGym]
    class_type = [class_type.split('.')[1] for class_type in request.GET.getlist('class-type')] \
        if request.GET.getlist('class-type') else [str(e.name) for e in models.EastonClassCategory]
    requirements = [requirements.split('.')[1] for requirements in request.GET.getlist('requirements')] \
        if request.GET.getlist('requirements') else [str(e.name) for e in models.EastonRequirements]
    easton_class_list = models.get_classes(gym_list, class_type, requirements)

    template = loader.get_template('retriever/index.html')
    easton_class_list.sort(key=lambda added_class: added_class.start_time)
    context = {
        'easton_classes': easton_class_list
    }
    return HttpResponse(template.render(context, request))


#def get_checks(request):
#
#    easton_class_list = []
#    today_date = datetime.now(pytz.timezone('US/Mountain'))
#
#    # TODO - optimize
#    if request.GET.get('gym') and request.GET.get('class-type') and request.GET.get('requirements'):
#        for gym in request.GET.getlist('gym'):
#            easton_class_list.extend(get_class_list(today_date, gym))
#        logger.debug("BEGINNING CLASS SIZE: {}".format(len(easton_class_list)))
#        easton_class_list[:] = [easton_class for easton_class in easton_class_list if
#                                str(easton_class.category_enum) in request.GET.getlist('class-type')]
#        logger.debug("SIZE AFTER TRIMMING: {}".format(len(easton_class_list)))
#        easton_class_list[:] = [easton_class for easton_class in easton_class_list if
#                                str(easton_class.requirements) in request.GET.getlist('requirements')]
#
#    template = loader.get_template('retriever/index.html')
#    easton_class_list.sort(key=lambda added_class: added_class.full_start_time)
#    context = {
#        'easton_classes': easton_class_list
#    }
#    return HttpResponse(template.render(context, request))
