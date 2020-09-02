from  __future__  import print_function
import os
import requests
import urllib.parse
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import datetime, timedelta, date
from cal_auth import cal_auth

service = cal_auth()


def cal_create(length, interval, last):
    # Set base date to end date of last period
    start = date(last.year, last.month, last.day)+timedelta(days=int(interval))
    start_date = start.isoformat()
    end = start + timedelta(days=length)
    end_date = end.isoformat()

    event_result = service.events().insert(calendarId="primary",
        body={
            "summary": "Period!",
            "description": "This is when your period is predicted to occur.",
            "start": {"date": start_date},
            "end": {"date": end_date},
            "recurrence": [f"RRULE:FREQ=DAILY;INTERVAL={interval}"], 
        }
    ).execute()

    # Return event id 
    return event_result


def cal_update(length, interval, last, event_id):

    start = date(last.year, last.month, last.day)+timedelta(days=round(float(interval)))
    start_date = start.isoformat()
    end = start + timedelta(days=length)
    end_date = end.isoformat()
    interval = round(float(interval))
    event_result = service.events().update(
        calendarId="primary",
        eventId=event_id, 
        body={
            "summary": "Period!",
            "description": "This is when your period is predicted to occur.",
            "start": {"date": start_date},
            "end": {"date": end_date},
            "recurrence": [f"RRULE:FREQ=DAILY;INTERVAL={interval}"],
           },
    ).execute()

    return event_result


def cal_delete():
    # Delete the event
       try:
           service.events().delete(
               calendarId='primary',
               eventId='hc37hodlfg715pielc2lfj9avg', # Todo: MAKE RESPONSIVE
           ).execute()
       except service.errors.HttpError:
           print("Failed to delete event")

       print("Event deleted")




