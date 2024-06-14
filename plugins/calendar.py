import icalendar
import requests
from datetime import datetime, timedelta
import random
import tzlocal

class Adapter:
    def __init__(self, config, utils):
        self.utils = utils
        self.calendar_configuration = config['calendars']
        self.example_count = config.get('example_count', 1)
        self.local_tz = tzlocal.get_localzone()
        self.calendars = {}
        self.calendar_events = []
        self.documents = []

    def update(self):
        for calendar in self.calendar_configuration:
            caldav_url = calendar.get('url')
            username = calendar.get('username')
            password = calendar.get('password')

            session = requests.Session()
            session.auth = (username, password)

            response = session.get(caldav_url, timeout=10)

            calendar_object = icalendar.Calendar.from_ical(response.text)
            self.calendars[caldav_url] = calendar_object

        self.calendar_events = []
        title = "All calendar events (meetings, appointments, tasks) for the next week:"
        for calendar in self.calendars.keys():
            calendar_obj = self.calendars[calendar]
            # localize the date time
            now = datetime.now(self.local_tz)

            # for now, let's just work with the next week of events
            start = now
            end = now + timedelta(days=7)

            for component in calendar_obj.walk():
                if component.name == "VEVENT":
                    event_start = component.get("DTSTART").dt.astimezone(self.local_tz)
                    event_end = component.get("DTEND").dt.astimezone(self.local_tz)
                    if start <= event_start < end:
                        self.calendar_events.append(component)

        if self.calendar_events:
            self.calendar_events.sort(key=lambda x: x.get('DTSTART').dt.astimezone(self.local_tz))
            llm_prompt = f"{title}\n"
            for event in self.calendar_events:
                event_start = event.get("DTSTART").dt.astimezone(self.local_tz)
                event_end = event.get("DTEND").dt.astimezone(self.local_tz)
                event_day_of_week = event_start.strftime("%A")
                event_start_formatted = event_start.strftime('%I:%M %p')
                event_end_formatted = event_end.strftime('%I:%M %p')
                event_start_date_formatted = event_start.strftime('%B %-d')
                event_summary = event.get('SUMMARY')
                if not event_summary:
                    event_summary = event.get('TITLE')
                llm_prompt = llm_prompt + '\n- ' + (f"{event_summary} between {event_start_formatted} and {event_end_formatted} on {event_day_of_week}, {event_start_date_formatted}")

        else:
            llm_prompt = f"{title}\n\nThere are no calendar events in the next week."

        self.llm_prompt = llm_prompt
        self.documents = [
            {
                "title": self.llm_prompt,
                "embedding": self.utils['get_embedding'](self.llm_prompt)
            }
        ]

    def get_documents(self):
        return self.documents

    def get_llm_prompt_addition(self, selected_categories, user_prompt):
        examples = []
        if self.calendar_events:
            now = datetime.now(self.local_tz)
            # we can only reliably create three examples, so let's cap there for now
            # also, why would you want more than 3 calendar examples anyway?
            number_of_samples = min(self.example_count, 3)

            days_with_events = {}
            for event in self.calendar_events:
                event_start = event.get("DTSTART").dt.astimezone(self.local_tz)
                event_day_of_week = event_start.strftime("%A")
                event_start_formatted = event_start.strftime('%I:%M %p')
                if event_day_of_week not in days_with_events:
                    days_with_events[event_day_of_week] = []
                event_summary = event.get('SUMMARY')
                if not event_summary:
                    event_summary = event.get('TITLE')
                days_with_events[event_day_of_week].append((event_summary, event_start_formatted))

            days_without_events = []
            days_excluding_today = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            days_excluding_today.remove(now.strftime("%A"))
            for day in days_excluding_today:
                if day not in days_with_events:
                    days_without_events.append(day)

            closest_event = min(self.calendar_events, key=lambda x: abs((x.get("DTSTART").dt.astimezone(self.local_tz) - now).total_seconds()))

            closest_event_start = closest_event.get("DTSTART").dt.astimezone(self.local_tz)
            closest_event_start_formatted = closest_event_start.strftime('%I:%M %p')
            closest_event_day_of_week = closest_event_start.strftime("%A")

            random_event = random.choice(list(days_with_events.values())[0])

            day_with_event = random.choice(list(days_with_events.keys()))
            schedule = ", ".join([f"{summary} at {time}" for summary, time in days_with_events[day_with_event]])
            examples.append(
                (
                    f"What's my schedule for {day_with_event}?",
                    f"You have {schedule} on {day_with_event}, {closest_event_start.strftime('%B %-d')}."
                    )
                )

            if days_without_events:
                day_without_event = random.choice(days_without_events)
                examples.append(
                    (
                        f"What's my schedule for {day_without_event}?",
                        f"Your calendar for {day_without_event} is empty."
                        )
                    )

            closest_event_summary = closest_event.get('SUMMARY')
            if not closest_event_summary:
                closest_event_summary = closest_event.get('TITLE')
            examples.append(
                (
                    "What's the first thing in my calendar?",
                    f"It is {closest_event_summary} at {closest_event_start_formatted} on {closest_event_day_of_week}, {closest_event_start.strftime('%B %d')}"
                    )
                )

            examples.append(
                (
                    f"When was that {random_event[0]} again?",
                    f"It is at {random_event[1]} on {list(days_with_events.keys())[0]}, {closest_event_start.strftime('%B %d')}"
                    )
                )

            examples = random.sample(examples, number_of_samples)

        return {
            "prompt": self.llm_prompt,
            "examples": examples
        }
