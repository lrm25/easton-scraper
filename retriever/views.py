from django.http import HttpResponse
from django.shortcuts import render
from django.template import loader
from bs4 import BeautifulSoup
import logging
from urllib.request import urlopen, Request
from urllib.error import HTTPError

logger = logging.getLogger('django')


class EastonClass:
    def __init__(self):
        name = ""
        start_time = ""
        end_time = ""


# Create your views here.
def get_raw_data(request):
    schedule = None
    try:
        # Pull the main schedule page on easton's website to get the internal MindBody link
        easton_request = Request("https://eastonbjj.com/denver/schedule", headers={'User-Agent': "lmccrone"})
        schedule = urlopen(easton_request)
        soup = BeautifulSoup(schedule.read())
        schedule_id = soup.find_all('healcode-widget')[0]['data-widget-id']
        logger.info("FOUND:  %s" % soup.find_all(schedule_id))

        # Pull the MindBody data directly
        request_str = "https://widgets.healcode.com/widgets/schedules/" + schedule_id + "/print"
        mind_body_request = Request(request_str)
        schedule = urlopen(mind_body_request)
        soup = BeautifulSoup(schedule.read())
        class_list = soup.find_all('tr', {'class': 'hc_class'})
        easton_classes = []
        for class_field in class_list:
            easton_class = EastonClass()
            logger.info(class_field)
            logger.info("CLASS NAME:  %s" % class_field.find('span', {'class': 'classname'}).text)
            easton_class.name = class_field.find('span', {'class': 'classname'}).text
            logger.info("START TIME:  %s" % class_field.find('span', {'class': 'hc_starttime'}).text)
            easton_class.start_time = class_field.find('span', {'class': 'hc_starttime'}).text
            logger.info("END TIME:  %s" % class_field.find('span', {'class': 'hc_endtime'}).text)
            easton_class.end_time = class_field.find('span', {'class': 'hc_endtime'}).text
            easton_classes.append(easton_class)
        template = loader.get_template('retriever/index.html')
        context = {
            'easton_classes': easton_classes
        }
    except HTTPError as e:
        logger.error(e.fp.read())
    return HttpResponse(template.render(context, request))
