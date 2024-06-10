import icalendar
import requests
from datetime import datetime, timedelta
from urllib.parse import urljoin
import tzlocal

class Adapter:
    def __init__(self, config, utils):
        self.utils = utils
        self.calendar_configuration = config['calendars']
        self.local_tz = tzlocal.get_localzone()
        self.calendars = {}

    def update(self):
        for calendar in self.calendar_configuration:
            caldav_url = calendar.get('url')
            # Set up your credentials
            username = calendar.get('username')
            password = calendar.get('password')

            # Create a requests session with basic auth
            session = requests.Session()
            session.auth = (username, password)

            # Get the calendar data
            response = session.get(caldav_url)

            # Parse the calendar data
            calendar_object = icalendar.Calendar.from_ical(response.text)
            self.calendars[caldav_url] = calendar_object

    def get_documents(self):
        # for now, let's only give one category for the calendar events
        title = "All calendar events (meetings, appointments, tasks) for the next week."
        return [
            {
                "title": title,
                "embedding": self.utils['get_embedding'](title)
            }
        ]

    def get_llm_prompt_addition(self, selected_categories, user_prompt):
        llm_prompt = "Calendar events for the next week:\n"
        examples = []
        for calendar in self.calendars.keys():
            calendar_obj = self.calendars[calendar]
            # Get the current datetime
            now = datetime.now(self.local_tz)

            # Set up the start and end dates for the next week
            start = now
            end = now + timedelta(days=7)

            # Iterate through the events in the calendar
            for component in calendar_obj.walk():
                if component.name == "VEVENT":
                    # Get the event start and end dates
                    event_start = component.get("DTSTART").dt.astimezone(self.local_tz)
                    event_end = component.get("DTEND").dt.astimezone(self.local_tz)

                    # Check if the event is within the next week
                    if start <= event_start < end:
                        day_of_week = event_start.strftime("%A")
                        llm_prompt = llm_prompt + '\n- ' + (f"{component.get('SUMMARY')} at {event_start.strftime('%I:%M %p')} on {day_of_week}, {event_start.strftime('%B %d')}")

        # TODO implement this
        return {
            "prompt": llm_prompt,
            "examples": examples
        }

