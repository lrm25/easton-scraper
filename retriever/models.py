from django.db import models

from bs4 import BeautifulSoup
from enum import Enum
from datetime import datetime, timedelta
from urllib.request import urlopen, Request

import logging
import pytz
import re

logger = logging.getLogger('django')


# *** ENUMS ***

def for_django(cls):
    cls.do_not_call_in_templates = True
    return cls


class EastonCalendarType(Enum):
    M = "MindBody"
    Z = "Zen"


@for_django
class EastonGym(Enum):
    AR = "Arvada"
    AU = "Aurora"
    BR = "Boulder"
    CR = "Castle Rock"
    CE = "Centennial"
    DE = "Denver"
    LI = "Littleton"
    TH = "Thornton"


class EastonBjjAttire(Enum):
    GI = "Gi"
    NG = "No-gi"


class EastonBjjCat(Enum):
    TR = "Drilling/Training"
    RA = "Randori"


class EastonStrCat(Enum):
    KB = "Kickboxing"
    MT = "Muay thai"
    SP = "Sparring"


@for_django
class EastonClassCategory(Enum):
    MMA = "MMA"
    BJJ = "BJJ"
    STR = "Striking"
    WRE = "Wrestling"
    CON = "Conditioning"
    YOG = "Yoga"
    OGY = "Open Gym"
    PLE = "Private Lesson"
    # Kids
    LTS = "Little Tigers"
    KBJ = "Kids BJJ"
    KST = "Kids Striking"
    KWR = "Kids Wrestling"
    # Not set
    NSE = "Not Set"


@for_django
class EastonRequirements(Enum):
    # All invitation-only
    INV = "Invitation"
    # MMA
    GFS = "Green shirt, four stripe white belt"
    # Wrestling
    TSW = "Two stripes or wrestling experience"
    # Age
    OFY = "Over 40 years old"
    # Gender
    FEM = "Female"
    # Weight
    OTH = "Over 200 pounds"
    TSU = "Two stripes, under 160 pounds"
    # Muay thai
    BSH = "Blue shirt"
    GSH = "Green shirt"
    OSH = "Orange shirt"
    YSH = "Yellow shirt"
    # BJJ
    PBT = "Purple belt"
    BBT = "Blue belt"
    WTS = "White belt two stripes"
    # Kids BJJ
    YBL = "Yellow belt"
    SGB = "Solid grey belt"
    GWB = "Grey/white belt"
    # Everyone (who paid)
    NON = "None"
    # Not set
    NSE = "Not set"


# *** Constants ***

NUMBER_RETRIEVAL_DAYS = 7
LAST_UPDATE_TIME = datetime.now(pytz.timezone('US/Mountain'))

CALENDAR_LINK_GYM_IDX = 0
CALENDAR_LINK_TYPE_IDX = 1;
CALENDAR_LINK_URL_IDX = 2;
CALENDAR_LINK_LIST = [
    [EastonGym.AR, EastonCalendarType.M, "https://eastonbjj.com/arvada/schedule"],
    [EastonGym.AU, EastonCalendarType.M, "https://eastonbjj.com/aurora/schedule"],
    [EastonGym.BR, EastonCalendarType.M, "https://eastonbjj.com/boulder/schedule"],
    [EastonGym.CE, EastonCalendarType.M, "https://eastonbjj.com/centennial/schedule"],
    [EastonGym.CR, EastonCalendarType.Z, "https://etc-castlerock.sites.zenplanner.com/calendar.cfm"],
    [EastonGym.DE, EastonCalendarType.M, "https://eastonbjj.com/denver/schedule"],
    [EastonGym.LI, EastonCalendarType.M, "https://eastonbjj.com/littleton/schedule"],
    [EastonGym.TH, EastonCalendarType.Z, "https://eastonbjjnorth.sites.zenplanner.com/calendar.cfm"]
]


# Create your models here.
class EastonClass(models.Model):

    # *** Database fields ***

    gym = models.CharField(
        max_length=2,
        choices=[(e, e.value) for e in EastonGym]
    )
    category = models.CharField(
        max_length=3,
        choices=[(e, e.value) for e in EastonClassCategory],
        default=EastonClassCategory.NSE
    )
    # MindBody or ZenCalendar class ID, used, along with 'gym', to uniquely identify classes
    class_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    requirements = models.CharField(
        max_length=3,
        choices=[(e, e.value) for e in EastonRequirements],
        default=EastonClassCategory.NSE
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    canceled = models.BooleanField(default=False)

    # Non-db field
    mindbody_category = None

    def __str__(self):
        return "GYM:  {}, NAME:  {}, START:  {}, END:  {}".format(self.gym, self.name, self.start_time, self.end_time)


class EastonBjjClass(models.Model):
    easton_class = models.ForeignKey(EastonClass, on_delete=models.CASCADE)
    attire = models.CharField(
        max_length=2,
        choices=[(e, e.value) for e in EastonBjjAttire]
    )
    category = models.CharField(
        max_length=2,
        choices=[(e, e.value) for e in EastonBjjCat]
    )


class EastonStrkClass(models.Model):
    easton_class = models.ForeignKey(EastonClass, on_delete=models.CASCADE)
    category = models.CharField(
        max_length=2,
        choices=[(e, e.value) for e in EastonStrCat]
    )


def retrieve_data_from_web(number_of_days):

    current_time = datetime.now(pytz.timezone('US/Mountain'))

    for calendar_data in CALENDAR_LINK_LIST:
        # TODO gym reference is temp
        if calendar_data[CALENDAR_LINK_TYPE_IDX] == EastonCalendarType.M:
            easton_page = EastonMbCalendarPage(calendar_data[CALENDAR_LINK_GYM_IDX],
                                               calendar_data[CALENDAR_LINK_URL_IDX])
            mb_schedule_id = easton_page.get_inner_mbc_id()
            mb_calendar = MindBodyCalendar(calendar_data[CALENDAR_LINK_GYM_IDX])
            mb_calendar.get_class_data(mb_schedule_id, current_time, number_of_days)

        elif calendar_data[CALENDAR_LINK_TYPE_IDX] == EastonCalendarType.Z:
            get_calendar_daily_data(calendar_data[CALENDAR_LINK_GYM_IDX],
                                    calendar_data[CALENDAR_LINK_URL_IDX], current_time, number_of_days)


class EastonMbCalendarPage:

    def __init__(self, location, page_url):
        self._location = location
        self._page_url = page_url

    #
    # Get the schedule ID for the inner MindBody calendar
    # (Easton's page has a javascript link which loads the schedule, we have to connect to mindbody's site
    #  with this ID to get the class data)
    #
    def get_inner_mbc_id(self):
        easton_request = Request(self._page_url, headers={'User-Agent': "lmccrone"})
        schedule = urlopen(easton_request)
        soup = BeautifulSoup(schedule.read())
        schedule_id = soup.find_all('healcode-widget')[0]['data-widget-id']
        return schedule_id


class MindBodyCalendar:

    def __init__(self, location):
        self._location = location

    def get_class_data(self, schedule_id, first_date, number_of_days=1):

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

            # TODO comments - what's actually going on here
            if 'hc_class' in table_row.get('class'):
                easton_class = EastonClass()
                # Littleton uses 'data-bw-widget-mbo-class-id' instead of 'data-hc-mbo-class-id'
                easton_class.gym = self._location
                class_id_tag = 'data-bw-widget-mbo-class-id' if easton_class.gym == EastonGym.LI \
                    else 'data-hc-mbo-class-id'
                easton_class.class_id = table_row.get(class_id_tag)
                easton_class.mindbody_category = current_category
                easton_class.name = table_row.find('span', {'class': 'classname'}).text
                class_date = datetime.strftime(self._date, "%Y-%m-%d")
                start_hr_time = table_row.find('span', {'class': 'hc_starttime'}).text
                # [2:] - remove dash at beginning of end time
                end_hr_time = table_row.find('span', {'class': 'hc_endtime'}).text[2:]
                easton_class.start_time = datetime.strptime(
                    class_date + ' ' + start_hr_time, '%Y-%m-%d %I:%M %p')
                easton_class.start_time.astimezone(pytz.timezone('US/Mountain'))
                easton_class.end_time = datetime.strptime(
                    class_date + ' ' + end_hr_time, '%Y-%m-%d %I:%M %p')
                easton_class.end_time.astimezone(pytz.timezone('US/Mountain'))
                easton_class.requirements = EastonRequirements.NSE
                easton_class.category = EastonClassCategory.NSE
                get_list_category(easton_class)

                insert_or_update(easton_class)

            # Class category divider
            if 'group_by_class_type' in table_row.get('class'):
                current_category = table_row.find('td').text

        logger.info("CLASS SIZE: " + str(len(daily_class_list)))
        return daily_class_list


def insert_or_update(easton_class):

    # Check if field already exists in database
    try:
        old_class = EastonClass.objects.get(gym=easton_class.gym, class_id=str(easton_class.class_id))
        old_class.gym = easton_class.gym
        old_class.name = easton_class.name
        old_class.start_time = easton_class.start_time
        old_class.end_time = easton_class.end_time
        old_class.requirements = easton_class.requirements
        old_class.category = easton_class.category
        old_class.save()

        logger.debug("UPDATED CLASS: {}".format(easton_class))
    except EastonClass.DoesNotExist:
        easton_class.save()
        logger.debug("SAVED NEW CLASS: {}".format(easton_class))
    # daily_class_list.append(easton_class)


#
# Scrape class data from gyms that use zencalendar
#
# params:
# gym_location:  string representing gym location ("Castle Rock", etc.)
# webpage_location:  calendar webpage URL
# added_class_list:  reference to list of classes found over all gyms so far, function adds to this
#
def get_calendar_daily_data(gym_location, webpage_location, first_date, total_days=1):

    # TODO don't requery calendar page every day, it isn't necessary
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
            easton_class.gym = gym_location
            easton_class.category = calendar_class.get('class')[2]
            easton_class.class_id = class_id
            easton_class.name = calendar_class.text
            easton_class.date = date_string
            class_time_list = class_time.split(" - ")
            start_time = class_time_list[0]
            end_time = class_time_list[1]
            easton_class.start_time = datetime.strptime(
                easton_class.date + ' ' + start_time, '%Y-%m-%d %I:%M %p')
            easton_class.start_time.astimezone(pytz.timezone('US/Mountain'))
            easton_class.end_time = datetime.strptime(
                easton_class.date + ' ' + end_time, '%Y-%m-%d %I:%M %p')
            easton_class.end_time.astimezone(pytz.timezone('US/Mountain'))
            get_list_category(easton_class)

            insert_or_update(easton_class)


def get_classes(gym_list, class_type_list, requirements_list):

    query_sets = []
    for gym_query in gym_list:
        for class_type_query in class_type_list:
            for requirements_query in requirements_list:
                try:
                    query_sets.extend([easton_class for easton_class in
                                       EastonClass.objects.filter(gym=EastonGym[gym_query],
                                                                  category=EastonClassCategory[class_type_query],
                                                                  requirements=EastonRequirements[requirements_query])])
                except EastonClass.DoesNotExist:
                    continue
    return query_sets


def get_list_category(easton_class):

    c = easton_class.mindbody_category.lower() if easton_class.mindbody_category else ""
    n = easton_class.name.lower()

    # Little tigers
    if ("youth bjj" in c and "lil yeti" in n) or \
            ("little tigers" in c) or \
            (not c and "little tigers" in n):
        easton_class.category = EastonClassCategory.LTS
        easton_class.requirements = EastonRequirements.NON

    # Kids bjj, wrestling
    elif "youth bjj" in c:
        easton_class.category = EastonClassCategory.KBJ
        if "yeti" in n:
            easton_class.requirements = EastonRequirements.NON
        else:
            easton_class.requirements = EastonRequirements.YBL
    elif "kids" in c and "tiger" not in c:
        easton_class.category = EastonClassCategory.KBJ
        if "advanced" in n:
            easton_class.requirements = EastonRequirements.SGB
        elif "wrestling for youth" in n:
            easton_class.category = EastonClassCategory.KWR
            easton_class.requirements = EastonRequirements.NON
        else:
            easton_class.requirements = EastonRequirements.NON
    elif "tigers" in c or (not c and ("kids martial arts" in n or "tiger" in n)):
        easton_class.category = EastonClassCategory.KBJ
        if "invite-only" in n:
            easton_class.requirements = EastonRequirements.INV
        elif "advanced" in n or \
                "competition" in n:
            easton_class.requirements = EastonRequirements.SGB
        elif "comp" in n:
            easton_class.requirements = EastonRequirements.GWB
        else:
            easton_class.requirements = EastonRequirements.NON
    elif "seminar" in c and "kids" in n:
        easton_class.category = EastonClassCategory.KBJ
        easton_class.requirements = EastonRequirements.NON
    elif not c and "kids competition" in n:
        easton_class.category = EastonClassCategory.KBJ
        easton_class.requirements = EastonRequirements.YBL
    elif not c and "tigers" in n:
        easton_class.category = EastonClassCategory.KBJ
        easton_class.requirements = EastonRequirements.NON
    elif not c and "teen bjj" in n:
        easton_class.category = EastonClassCategory.KBJ
        easton_class.requirements = EastonRequirements.INV

    # Kids muay thai
    elif "kids muay thai" in c or "youth kick" in c:
        easton_class.category = EastonClassCategory.KST
        easton_class.requirements = EastonRequirements.NON
    elif not c and "kids muay thai" in n:
        easton_class.category = EastonClassCategory.KST
        easton_class.requirements = EastonRequirements.NON

    # Adult BJJ, wrestling, yoga, MMA (MMA also below)
    elif "bjj" in c or \
         (not c and ("bjj" in n and not "tiger" in n)):
        # I put some of these into different categories.  Split them off first.
        if "wrestling" in n:
            easton_class.category = EastonClassCategory.WRE
            easton_class.requirements = EastonRequirements.TSW
        elif "yoga" in n:
            easton_class.category = EastonClassCategory.YOG
            easton_class.requirements = EastonRequirements.NON
        elif "mma" in n:
            easton_class.category = EastonClassCategory.MMA
            easton_class.requirements = EastonRequirements.GFS
        else:
            easton_class.category = EastonClassCategory.BJJ
            if "beware" in n:
                easton_class.requirements = EastonRequirements.PBT
            elif "advanced" in n:
                easton_class.requirements = EastonRequirements.BBT
            elif "randori" in n:
                if "all levels" in n:
                    easton_class.requirements = EastonRequirements.NON
                elif "160" in n:
                    easton_class.requirements = EastonRequirements.TSU
                elif "40" in n:
                    easton_class.requirements = EastonRequirements.OFY
                else:
                    easton_class.requirements = EastonRequirements.WTS
            elif "competition training" in n:
                easton_class.requirements = EastonRequirements.WTS
            elif "adv/int" in n or \
                    ("intermediate" in n and "fundamentals" not in n):
                easton_class.requirements = EastonRequirements.WTS
            elif "200" in n:
                easton_class.requirements = EastonRequirements.OTH
            elif "women" in n:
                easton_class.requirements = EastonRequirements.FEM
            # TODO set c and n to lowercase
            elif "flow roll" in n or \
                "fundamentals" in n or \
                    "family" in n or \
                    "all levels" in n or \
                    "all-levels" in n or \
                    "intro" in n or "int/fund" in n:
                 easton_class.requirements = EastonRequirements.NON
    elif not c and ("randori" in n or "bjj" in n or "no-gi" in n or "no gi" in n or "drilling" in n):
        easton_class.category = EastonClassCategory.BJJ
        if "advanced" in easton_class.name:
            easton_class.requirements = EastonRequirements.BBT
        elif ("intermediate" in easton_class.name and "fundamentals" not in easton_class.name) or \
                "randori" in easton_class.name:
            easton_class.requirements = EastonRequirements.WTS
        elif "all levels" in easton_class.name or \
                "fundamentals" in easton_class.name or \
                "no gi" in easton_class.name or \
                "no-gi" in easton_class.name or \
                "family" in easton_class.name or \
                "drilling" in easton_class.name:
            easton_class.requirements = EastonRequirements.NON

    # Conditioning
    elif "conditioning" in c:
        easton_class.category = EastonClassCategory.CON
        easton_class.requirements = EastonRequirements.NON

    # Open gym
    elif "open gym" in c or "open mat" in c:
        easton_class.category = EastonClassCategory.OGY
        easton_class.requirements = EastonRequirements.NON

    # Adult muay thai
    elif "muay thai" in c or "striking" in c:
        easton_class.category = EastonClassCategory.STR
        if "blue shirt" in n:
            easton_class.requirements = EastonRequirements.BSH
        elif "competition" in n or "sparring" in n or "green shirt" in n:
            easton_class.requirements = EastonRequirements.GSH
        elif "advanced" in n or "intermediate" in n or "orange shirt" in n:
            easton_class.requirements = EastonRequirements.OSH
        elif "muay thai" in n or \
             "thai pad" in n or \
             "clinch" in n:
            easton_class.requirements = EastonRequirements.YSH
        elif "kickboxing" in n or \
             "open mat" in n or \
             "fundamentals of striking" in n or \
             "teens" in n:
            easton_class.requirements = EastonRequirements.NON
        elif "invite only" in n:
            easton_class.requirements = EastonRequirements.INV
    elif not c and ("muay thai" in n or "kickboxing" in n):
        easton_class.category = EastonClassCategory.STR
        if "Muay Thai" in easton_class.name:
            easton_class.requirements = EastonRequirements.YSH
        elif "Kickboxing" in easton_class.name:
            easton_class.requirements = EastonRequirements.NON



    # MMA
    elif "pro fight team" in c:
        easton_class.category = EastonClassCategory.MMA
        easton_class.requirements = EastonRequirements.INV

    # Fitness
    if not c and "fitness" in n:
        easton_class.category = EastonClassCategory.CON
        easton_class.requirements = EastonRequirements.NON

    # Private lesson
    if not c and "private lesson" in n:
        easton_class.category = EastonClassCategory.PLE
        easton_class.requirements = EastonRequirements.NON

