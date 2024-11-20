import icalendar
import requests
import datetime
import random
import tzlocal
import dateutil.rrule

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
            now = datetime.datetime.now(self.local_tz)
            # for now, let's just work with the next week of events
            start = now
            end = now + datetime.timedelta(days=7)
            for component in calendar_obj.walk():
                if component.name == "VEVENT":
                    event_start = component.get("DTSTART").dt
                    if isinstance(event_start, datetime.date) and not isinstance(event_start, datetime.datetime):
                        event_start = datetime.datetime.combine(event_start, datetime.time(0, tzinfo=self.local_tz))
                    if hasattr(event_start, 'astimezone'):
                        event_start = event_start.astimezone(self.local_tz)
                    event_end = component.get("DTEND").dt
                    if isinstance(event_end, datetime.date) and not isinstance(event_end, datetime.datetime):
                        event_end = datetime.datetime.combine(event_end, datetime.time(0, tzinfo=self.local_tz))
                    if hasattr(event_end, 'astimezone'):
                        event_end = event_end.astimezone(self.local_tz)
                    if start <= event_start < end:
                        self.calendar_events.append(component)
                    # handle recurring events
                    rrule_attr = component.get("RRULE")
                    if rrule_attr:
                        rrule_string = rrule_attr.to_ical().decode()
                        params = rrule_string.split(";")
                        freq = None
                        interval = 1
                        byweekday = None
                        until = None
                        bymonthday = None
                        bymonth = None
                        for param in params:
                            if param.startswith("FREQ="):
                                freq = param.split("=")[1]
                            elif param.startswith("INTERVAL="):
                                interval = int(param.split("=")[1])
                            elif param.startswith("BYDAY="):
                                byweekday = param.split("=")[1]
                            elif param.startswith("UNTIL="):
                                until = param.split("=")[1]
                            elif param.startswith("BYMONTHDAY="):
                                bymonthday = int(param.split("=")[1])
                            elif param.startswith("BYMONTH="):
                                bymonth = int(param.split("=")[1])
                        if until:
                            until_date = datetime.datetime.strptime(until, "%Y%m%dT%H%M%SZ").date()
                            until_date = datetime.datetime.combine(until_date, datetime.time(0, tzinfo=self.local_tz))
                        else:
                            until_date = datetime.datetime.now(tzinfo=self.local_tz) + datetime.timedelta(days=400)
                        if freq == "DAILY":
                            rrule_set = dateutil.rrule.rrule(dateutil.rrule.DAILY, interval=interval, dtstart=event_start, until=until_date)
                        elif freq == "WEEKLY":
                            weekday_mapping = {
                                'MO': dateutil.rrule.MO,
                                'TU': dateutil.rrule.TU,
                                'WE': dateutil.rrule.WE,
                                'TH': dateutil.rrule.TH,
                                'FR': dateutil.rrule.FR,
                                'SA': dateutil.rrule.SA,
                                'SU': dateutil.rrule.SU,
                            }
                            weekdays = []
                            for weekday_str in byweekday.split(','):
                                weekdays.append(weekday_mapping[weekday_str.upper()])
                            rrule_set = dateutil.rrule.rrule(dateutil.rrule.WEEKLY, interval=interval, dtstart=event_start, byweekday=weekdays, until=until_date)
                        elif freq == "MONTHLY":
                            rrule_set = dateutil.rrule.rrule(dateutil.rrule.MONTHLY, interval=interval, dtstart=event_start, until=until_date)
                        elif freq == "YEARLY":
                            if bymonthday and bymonth:
                                rrule_set = dateutil.rrule.rrule(dateutil.rrule.YEARLY, interval=interval, dtstart=event_start, bymonth=bymonth, bymonthday=bymonthday, until=until_date)
                            elif bymonthday:
                                rrule_set = dateutil.rrule.rrule(dateutil.rrule.YEARLY, interval=interval, dtstart=event_start, bymonthday=bymonthday, until=until_date)
                            elif bymonth:
                                rrule_set = dateutil.rrule.rrule(dateutil.rrule.YEARLY, interval=interval, dtstart=event_start, bymonth=bymonth, until=until_date)
                            else:
                                rrule_set = dateutil.rrule.rrule(dateutil.rrule.YEARLY, interval=interval, dtstart=event_start, until=until_date)
                        else:
                            print(f"Unsupported frequency for rule {rrule_string}")
                            continue
                        for recurring_event_start in rrule_set.between(before=end, after=datetime.datetime.now(self.local_tz), inc=True):
                            # create a new VEVENT component for the recurring event
                            recurring_event = icalendar.Event()
                            recurring_event.add("DTSTART", recurring_event_start)
                            recurring_event.add("DTEND", recurring_event_start + (event_end - event_start))
                            recurring_event.add("SUMMARY", component.get("SUMMARY"))
                            recurring_event.add("TITLE", component.get("TITLE"))
                            self.calendar_events.append(recurring_event)

        if self.calendar_events:
            self.calendar_events.sort(key=lambda x: x.get('DTSTART').dt)
            llm_prompt = f"{title}\n"
            for event in self.calendar_events:
                event_start = event.get("DTSTART").dt
                if isinstance(event_start, datetime.date) and not isinstance(event_start, datetime.datetime):
                    event_start = datetime.datetime.combine(event_start, datetime.time(0, tzinfo=self.local_tz))
                if hasattr(event_start, 'astimezone'):
                    event_start = event_start.astimezone(self.local_tz)
                event_end = event.get("DTEND").dt
                if isinstance(event_end, datetime.date) and not isinstance(event_end, datetime.datetime):
                    event_end = datetime.datetime.combine(event_end, datetime.time(0, tzinfo=self.local_tz))
                if hasattr(event_end, 'astimezone'):
                    event_end = event_end.astimezone(self.local_tz)

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

    def get_event_key(self, event):
        event_start = event.get("DTSTART").dt
        now = datetime.datetime.now(event_start.tzinfo)
        if isinstance(event_start, datetime.date) and not isinstance(event_start, datetime.datetime):
            event_start = datetime.datetime.combine(event_start, datetime.time(0))
        return abs((event_start - now).total_seconds())

    def get_documents(self):
        return self.documents

    def get_llm_prompt_addition(self, selected_categories, user_prompt):
        examples = []
        if self.calendar_events:
            now = datetime.datetime.now(self.local_tz)
            # we can only reliably create three examples, so let's cap there for now
            # also, why would you want more than 3 calendar examples anyway?
            number_of_samples = min(self.example_count, 3)

            days_with_events = {}
            for event in self.calendar_events:
                event_start = event.get("DTSTART").dt
                if isinstance(event_start, datetime.date) and not isinstance(event_start, datetime.datetime):
                    event_start = datetime.datetime.combine(event_start, datetime.time(0, tzinfo=self.local_tz))
                if hasattr(event_start, 'astimezone'):
                    event_start = event_start.astimezone(self.local_tz)
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

            closest_event = min(self.calendar_events, key=self.get_event_key)

            closest_event_start = closest_event.get("DTSTART").dt
            if isinstance(closest_event_start, datetime.date) and not isinstance(closest_event_start, datetime.datetime):
                closest_event_start = datetime.datetime.combine(closest_event_start, datetime.time(0, tzinfo=self.local_tz))
            if hasattr(closest_event_start, 'astimezone'):
                closest_event_start = closest_event_start.astimezone(self.local_tz)

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
