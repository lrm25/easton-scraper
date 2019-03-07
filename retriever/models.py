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

class EastonCalendarType(Enum):
    M = "MindBody"
    Z = "Zen"


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


class EastonStrClass(models.Model):
    easton_class = models.ForeignKey(EastonClass, on_delete=models.CASCADE)
    category = models.CharField(
        max_length=2,
        choices=[(e, e.value) for e in EastonStrCat]
    )


def retrieve_data_from_web(number_of_days):

    current_time = datetime.now(pytz.timezone('US/Mountain'))

    for calendar_data in CALENDAR_LINK_LIST:
        # TODO gym reference is temp
        if calendar_data[CALENDAR_LINK_TYPE_IDX] == EastonCalendarType.M and calendar_data[CALENDAR_LINK_GYM_IDX] == EastonGym.AU:
            easton_page = EastonMbCalendarPage(calendar_data[CALENDAR_LINK_GYM_IDX],
                                               calendar_data[CALENDAR_LINK_URL_IDX])
            mb_schedule_id = easton_page.get_inner_mbc_id()
            mb_calendar = MindBodyCalendar(calendar_data[CALENDAR_LINK_GYM_IDX])
            mb_calendar.get_class_data(mb_schedule_id, current_time, number_of_days)

        # elif calendar_data[CALENDAR_LINK_TYPE_IDX] == EastonCalendarType.Z:
            # retrieve_zen_data(number_of_days)


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

            if 'hc_class' in table_row.get('class'):
                easton_class = EastonClass()
                easton_class.class_id = table_row.get('data-hc-mbo-class-id')
                easton_class.gym = self._location
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

                # Check if field already exists in database
                try:
                    old_class = EastonClass.objects.get(gym=easton_class.gym, class_id=easton_class.class_id)
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
                #daily_class_list.append(easton_class)

            # Class category divider
            if 'group_by_class_type' in table_row.get('class'):
                current_category = table_row.find('td').text

        logger.info("CLASS SIZE: " + str(len(daily_class_list)))
        return daily_class_list


# TODO - clean up
# TODO - combine with other
def get_list_category(easton_class):

    c = easton_class.mindbody_category
    n = easton_class.name

    # TODO - comment each section
    if "Youth BJJ" in c:
        if "Lil Yeti" in n:
            easton_class.category = EastonClassCategory.LTS
            easton_class.requirements = EastonRequirements.NON
        elif "Yeti" in n:
            easton_class.category = EastonClassCategory.KBJ
            easton_class.requirements = EastonRequirements.NON
        else:
            easton_class.category = EastonClassCategory.KBJ
            easton_class.requirements = EastonRequirements.YBL
    elif "BJJ" in c or \
         (not c and ("BJJ" in n and not "Tiger" in n)):
        # I put some of these into different categories.  Split them off first.
        if "Wrestling" in n:
            easton_class.category = EastonClassCategory.WRE
            easton_class.requirements = EastonRequirements.TSW
        elif "Yoga" in n:
            easton_class.category = EastonClassCategory.YOG
            easton_class.requirements = EastonRequirements.NON
        elif "MMA" in n:
            easton_class.category = EastonClassCategory.MMA
            easton_class.requirements = EastonRequirements.GFS
        else:
            easton_class.category = EastonClassCategory.BJJ
            if "Beware" in n:
                easton_class.requirements = EastonRequirements.PBT
            elif "Advanced" in n:
                easton_class.requirements = EastonRequirements.BBT
            elif "Randori" in n:
                if "All Levels" in n:
                    easton_class.requirements = EastonRequirements.NON
                elif "160" in n:
                    easton_class.requirements = EastonRequirements.TSU
                elif "40" in n:
                    easton_class.requirements = EastonRequirements.OFY
                else:
                    easton_class.requirements = EastonRequirements.WTS
            elif "Competition Training" in n:
                easton_class.requirements = EastonRequirements.WTS
            elif "Adv/Int" in n or \
                    ("Intermediate" in n and "Fundamentals" not in n):
                easton_class.requirements = EastonRequirements.WTS
            elif "200" in n:
                easton_class.requirements = EastonRequirements.OTH
            elif "Women" in n:
                easton_class.requirements = EastonRequirements.FEM
            # TODO set c and n to lowercase
            elif "Flow Roll" in n or \
                "Fundamentals" in n or \
                    "Family" in n or \
                    "All Levels" in n or \
                    "All-levels" in n or \
                    "All levels" in n or \
                    "Intro" in n or "Int/Fund" in n:
                easton_class.requirements = EastonRequirements.NON
    if "Conditioning" in c:
        easton_class.category = EastonClassCategory.CON
        easton_class.requirements = EastonRequirements.NON
    elif "Open Gym" in c or "Open gym" in c:
        easton_class.category = EastonClassCategory.OGY
        easton_class.requirements = EastonRequirements.NON
    elif "Kids Muay Thai" in c or "Youth Kick" in c:
        easton_class.category = EastonClassCategory.KST
        easton_class.requirements = EastonRequirements.NON
    elif "Kids" in c and "Tiger" not in c:
        easton_class.category = EastonClassCategory.KBJ
        if "Advanced" in n:
            easton_class.requirements = EastonRequirements.SOLID_GREY_BELT
        else:
            easton_class.requirements = EastonRequirements.NON
    elif "Muay Thai" in c or "Striking" in c:
        easton_class.category = EastonClassCategory.STR
        if "blue shirt" in n:
            easton_class.requirements = EastonRequirements.BSH
        elif "Competition" in n or "Sparring" in n or "green shirt" in n:
            easton_class.requirements = EastonRequirements.GSH
        elif "Advanced" in n or "Intermediate" in n or "orange shirt" in n:
            easton_class.requirements = EastonRequirements.OSH
        elif "Muay Thai" in n or \
             "Thai Pad" in n or \
             "Clinch" in n:
            easton_class.requirements = EastonRequirements.YSH
        elif "Kickboxing" in n or \
             "Open Mat" in n or \
             "Fundamentals of Striking" in n or \
             "Teens" in n:
            easton_class.requirements = EastonRequirements.NON
        elif "Invite Only" in n:
            easton_class.requirements = EastonRequirements.INV
    elif "Open Mat" in c:
        easton_class.category = EastonClassCategory.OGY
        easton_class.requirements = EastonRequirements.NON
    elif "Little Tigers" in c or (not c and "Little Tigers" in n):
        easton_class.category = EastonClassCategory.LTS
        easton_class.requirements = EastonRequirements.NON
    elif "Tigers" in c or (not c and ("Kids Martial Arts" in n or "Tiger" in n)):
        easton_class.category = EastonClassCategory.KBJ
        if "Invite-Only" in n:
            easton_class.requirements = EastonRequirements.INV
        elif "Advanced" in n or \
                "Competition" in n:
            easton_class.requirements = EastonRequirements.SGB
        elif "comp" in n:
            easton_class.requirements = EastonRequirements.GWB
        else:
            easton_class.requirements = EastonRequirements.NON
    elif "Seminar" in c and "Kids" in n:
        easton_class.category = EastonClassCategory.KBJ
        easton_class.requirements = EastonRequirements.NON
    kids_wrestling_pattern = re.compile(".*?Wrestling [Ff]or [Yy]outh.*?")
    if kids_wrestling_pattern.match(n):
        easton_class.category = EastonClassCategory.KWR
        easton_class.requirements = EastonRequirements.NON
    elif "Pro Fight Team" in c:
        easton_class.category = EastonClassCategory.MMA
        easton_class.requirements = EastonRequirements.INV


# TODO - clean up
def get_calendar_category(easton_class):
    if "Fitness" in easton_class.name:
        easton_class.category = EastonClassCategory.CON
        easton_class.requirements = EastonRequirements.NON
    bjj_pattern = re.compile(".*?([Rr]andori|B[Jj][Jj]|No(-| )Gi|Drilling).*?")
    if bjj_pattern.match(easton_class.name):
        easton_class.category = EastonClassCategory.BJJ
        if "Teen BJJ" in easton_class.name:
            easton_class.requirements = EastonRequirements.INV
        elif "Advanced" in easton_class.name:
            easton_class.requirements = EastonRequirements.BBT
        elif ("Intermediate" in easton_class.name and "Fundamentals" not in easton_class.name) or \
                "Randori" in easton_class.name:
            easton_class.requirements = EastonRequirements.WTS
        elif "All Levels" in easton_class.name or \
             "Fundamentals" in easton_class.name or \
             "No Gi" in easton_class.name or \
             "No-Gi" in easton_class.name or \
             "Family" in easton_class.name or \
             "Drilling" in easton_class.name:
            easton_class.requirements = EastonRequirements.NON
    private_lesson_pattern = re.compile(".*?Private Lesson.*?")
    if private_lesson_pattern.match(easton_class.name):
        easton_class.category = EastonClassCategory.PLE
        easton_class.requirements = EastonRequirements.NON
    muay_thai_pattern = re.compile(".*?(Muay [Tt]hai|[Kk]ickboxing).*?")
    if muay_thai_pattern.match(easton_class.name):
        easton_class.category = EastonClassCategory.STR
        if "Muay Thai" in easton_class.name:
            easton_class.requirements = EastonRequirements.YSH
        elif "Kickboxing" in easton_class.name:
            easton_class.requirements = EastonRequirements.NON
    kids_muay_thai_pattern = re.compile(".*?Kids [Mm]uay [Tt]hai.*?")
    if kids_muay_thai_pattern.match(easton_class.name):
        easton_class.category = EastonClassCategory.KST
        easton_class.requirements = EastonRequirements.NON
    kids_muay_thai_pattern = re.compile(".*?Little Tigers.*?")
    if "Kids Competition" in easton_class.name:
        easton_class.category = EastonClassCategory.KBJ
        easton_class.requirements = EastonRequirements.YBL
    if kids_muay_thai_pattern.match(easton_class.name):
        easton_class.category = EastonClassCategory.LTS
        easton_class.requirements = EastonRequirements.NON
    elif "Tigers" in easton_class.name:
        easton_class.category = EastonClassCategory.KBJ
        easton_class.requirements = EastonRequirements.NON
