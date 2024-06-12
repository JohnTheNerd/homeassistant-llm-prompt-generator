import requests
import json
import random

class Adapter:
    def __init__(self, config, utils):
        self.access_token = config["access_token"]
        self.base_url = config["base_url"]
        self.ignored_entities = config.get('ignored_entities', [])
        self.current_initial_values = None
        self.utils = utils
        self.areas_enabled = config.get('areas_enabled', False)
        self.shopping_list_enabled = config.get('shopping_list_enabled', False)
        self.laundry_enabled = config.get('laundry_enabled', False)
        self.media_player_enabled = config.get('media_player_enabled', False)
        self.person_enabled = config.get('person_enabled', False)
        self.color_loop_enabled = config.get('color_loop_enabled', False)
        self.areas_template = """
        {%- for area in areas() %}
        {
            "area_id": "{{area}}",
            "area_name": "{{ area_name(area) }}",
            "type": "area"
        },
        {%- endfor %}
        """
        self.title_template = """
Devices in area {{AREA_NAME}} (Area ID: {{AREA_ID}}):
{%- set ignored_entities = {{IGNORED_ENTITIES}} %}
  {%- for device in area_devices('{{AREA_ID}}') %}
    {%- if not device_attr(device, "disabled_by") and not device_attr(device, "entry_type") and device_attr(device, "name") %}
      {%- for entity in device_entities(device) %}
        {%- set ns = namespace(skip_entity=False) %}
        {%- set entity_domain = entity.split('.')[0] %}
        {%- if not is_state(entity,'unavailable') and not is_state(entity,'unknown') and not is_state(entity,"None") and not is_hidden_entity(entity) %}
          {%- set ns.skip_entity = false %}
          {%- for ignored_entity in ignored_entities %}
            {%- if ignored_entity in entity|string %}
              {%- set ns.skip_entity = true %}
              {%- break %}
            {%- endif %}
          {%- endfor %}
          {%- if ns.skip_entity == false %}

{{ state_attr(entity, 'friendly_name') }} (Entity ID: {{entity}})

          {%- endif %}
        {%- endif %}
      {%- endfor %}
    {%- endif %}
  {%- endfor %}
  """
        self.summary_template = """
{%- set ignored_entities = {{IGNORED_ENTITIES}} %}
  {%- for device in area_devices('{{AREA_ID}}') %}
    {%- if not device_attr(device, "disabled_by") and not device_attr(device, "entry_type") and device_attr(device, "name") %}
      {%- for entity in device_entities(device) %}
        {%- set ns = namespace(skip_entity=False) %}
        {%- set entity_domain = entity.split('.')[0] %}
        {%- if not is_state(entity,'unavailable') and not is_state(entity,'unknown') and not is_state(entity,"None") and not is_hidden_entity(entity) %}
          {%- set ns.skip_entity = false %}
          {%- for ignored_entity in ignored_entities %}
            {%- if ignored_entity in entity|string %}
              {%- set ns.skip_entity = true %}
              {%- break %}
            {%- endif %}
          {%- endfor %}
          {%- if ns.skip_entity == false %}

          {%- if entity_domain == "light" and state_attr(entity, 'brightness') %}

{{ state_attr(entity, 'friendly_name') }} (Entity ID: {{entity}}) is {{ states(entity) }} with a brightness of {{ (state_attr(entity, 'brightness') | float / 255 * 100 ) | int }}%

            {%- else %}

{{ state_attr(entity, 'friendly_name') }} (Entity ID: {{entity}}) is {{ states(entity) }}

            {%- endif %}

          {%- endif %}
        {%- endif %}
      {%- endfor %}
    {%- endif %}
  {%- endfor %}
"""
        self.area_lights_template = """
{% if expand(area_entities(area_name('{{AREA_ID}}')) | select('match', 'light'))
       | selectattr('state', 'eq', 'on') | list | count == 0 %}
  The {{AREA_NAME}} lights are off.
{% else %}
  The {{AREA_NAME}} lights are on.
{% endif %}"""
        self.media_player_template = """
{%- for player in states.media_player %}
  {%- if is_state(player.entity_id, 'playing') %}
{{ state_attr(player.entity_id, 'friendly_name') }} is playing {{ state_attr(player.entity_id, 'media_title') }} by {{ state_attr(player.entity_id, 'media_artist') }}.
  {%- endif %}
{%- endfor %}"""
        self.laundry_template = """
{%- macro time_diff_in_words(timediff) %}
    {%- if timediff.total_seconds() < 60 -%}
        less than a minute ago
    {%- elif timediff.total_seconds() < 7200 -%}
        {{ (timediff.total_seconds() // 60) | int }} minutes ago.
    {%- elif timediff.total_seconds() < 172800 -%}
        {{ (timediff.total_seconds() // 7200) | int }} hours ago.
    {%- else -%}
        {{ (timediff.total_seconds() // 172800) | int }} days ago.
    {%- endif %}
{% endmacro %}

{% set now = now %}

{% if is_state("automation.washer_turned_off", "on") -%}
The washer is running.
    {%- if states.automation.washer_turned_off.attributes.last_triggered -%}
        {% set washer_diff = now() - states.automation.washer_turned_on.attributes.last_triggered %}
It started {{ time_diff_in_words(washer_diff) -}}
    {%- endif %}
{% else -%}
The washer is not running.
    {%- if states.automation.washer_turned_off.attributes.last_triggered -%}
        {% set washer_diff = now() - states.automation.washer_turned_off.attributes.last_triggered %}
It stopped {{ time_diff_in_words(washer_diff) -}}
    {% endif %}
{%- endif %}

{%- if is_state("automation.dryer_turned_off", "on") -%}
The dryer is running.
    {%- if states.automation.dryer_turned_off.attributes.last_triggered -%}
        {% set dryer_diff = now() - states.automation.dryer_turned_on.attributes.last_triggered %}
It started {{ time_diff_in_words(dryer_diff) -}}
    {%- endif -%}
{%- else -%}
The dryer is not running.
    {%- if states.automation.dryer_turned_off.attributes.last_triggered -%}
        {% set dryer_diff = now() - states.automation.dryer_turned_off.attributes.last_triggered %}
It stopped {{ time_diff_in_words(dryer_diff) -}}
    {%- endif %}
{% endif %}
"""
        self.person_template = """
{%- for person in states.person %}

{{ person.name }} is {% if is_state(person.entity_id, 'home') %}home{% else %}not home{% endif %}.

{%- endfor %}
"""
        self.color_loop_template = """
{% if is_state("automation.color_loop_bedroom_lamp", "on") or
is_state("automation.color_loop_bedroom_overhead", "on") -%}
Color loop (unicorn vomit) in the bedroom is enabled. Run service named script.disable_color_loop_bedroom to disable.
{%- else -%}
Color loop (unicorn vomit) in the bedroom is disabled. Run service named script.enable_color_loop_bedroom to enable.
{%- endif %}

{% if is_state("automation.color_loop_office_overhead_left", "on") or
is_state("automation.color_loop_office_overhead_right", "on") -%}
Color loop (unicorn vomit) in the office is enabled. Run service named script.disable_color_loop_office to disable.
{%- else -%}
Color loop (unicorn vomit) in the office is disabled. Run service named script.enable_color_loop_office to enable.
{%- endif %}

{% if is_state("automation.color_loop_living_room_couch_overhead", "on")
or is_state("automation.color_loop_living_room_table_overhead", "on") or
is_state("automation.color_loop_living_room_lamp_upper", "on") or
is_state("automation.color_loop_living_room_big_couch_overhead", "on") or
is_state("automation.color_loop_living_room_lamp_side", "on")  -%}
Color loop (unicorn vomit) in the living room is enabled. Run service named script.enable_color_loop_living_room to disable.
{%- else -%}
Color loop (unicorn vomit) in the living room is disabled. Run service named script.enable_color_loop_living_room to enable.
{%- endif %}

{% if is_state("automation.color_loop_music_room_lamp_side", "on") or
is_state("automation.color_loop_music_room_lamp_top", "on") or
is_state("automation.color_loop_music_room_light_strip", "on")  -%}
Color loop (unicorn vomit) in the music room is enabled. Run service named script.enable_color_loop_music_room to disable.
{%- else -%}
Color loop (unicorn vomit) in the music room is disabled. Run service named script.enable_color_loop_music_room to enable.
{%- endif %}

{% if is_state("automation.party_mode_living_room_couch_overhead", "on")
or is_state("automation.party_mode_living_room_table_overhead", "on") or
is_state("automation.party_mode_living_room_lamp_upper", "on") or
is_state("automation.party_mode_living_room_big_couch_overhead", "on") or
is_state("automation.party_mode_living_room_lamp_side", "on") or
is_state("automation.party_mode_music_room_lamp_side", "on") or
is_state("automation.party_mode_music_room_lamp_top", "on") or
is_state("automation.party_mode_music_room_light_strip", "on")  -%}
Party mode is enabled. Run service named script.disable_party_mode to disable.
{%- else -%}
Party mode is disabled. Run service named script.enable_party_mode to enable.
{%- endif %}
"""

    def update(self):
        current_initial_values = []
        if self.areas_enabled:
            areas = self.get_areas()
            for area in areas:
                title_template_edited = self.title_template.replace('{{AREA_NAME}}', area['area_name'])
                title_template_edited = title_template_edited.replace('{{AREA_ID}}', area['area_id'])
                title_template_edited = title_template_edited.replace('{{IGNORED_ENTITIES}}', json.dumps(self.ignored_entities))
                title = requests.post(f'{self.base_url}/api/template',
                                        json={"template": title_template_edited},
                                        headers={"Authorization": f"Bearer {self.access_token}"}).text
                area['title'] = title
                # see if we have any summary information at all
                # if we don't, do not include the area in the initial values
                if len(area['title'].split('\n')) > 1:
                    area['embedding'] = self.utils['get_embedding'](title)
                    current_initial_values.append(area)
        
        if self.shopping_list_enabled:
            shopping_list_title = 'Shopping list for the entire household'
            current_initial_values.append({
                "type": "shopping_list",
                "title": shopping_list_title,
                "embedding": self.utils['get_embedding'](shopping_list_title)
            })

        if self.laundry_enabled:
            laundry_title = 'States of laundry appliances (washer and dryer)'
            current_initial_values.append({
                "type": "laundry",
                "title": laundry_title,
                "embedding": self.utils['get_embedding'](laundry_title)
            })

        if self.media_player_enabled:
            media_player_title = 'States of all media players (songs, movies, shows, videos) in the household'
            current_initial_values.append({
                "type": "media_player",
                "title": media_player_title,
                "embedding": self.utils['get_embedding'](media_player_title)
            })

        if self.person_enabled:
            person_title = 'All people in HomeAssistant and whether if any of them are home'
            current_initial_values.append({
                "type": "person",
                "title": person_title,
                "embedding": self.utils['get_embedding'](person_title)
            })

        if self.color_loop_enabled:
            color_loop_title = 'The status of color loop (unicorn vomit mode) and party modes across the house'
            current_initial_values.append({
                "type": "color_loop",
                "title": color_loop_title,
                "embedding": self.utils['get_embedding'](color_loop_title)
            })

        self.current_initial_values = current_initial_values

    def get_areas(self):
        areas_response = requests.post(f'{self.base_url}/api/template',
                                    json={"template": self.areas_template},
                                    headers={"Authorization": f"Bearer {self.access_token}"})

        # create a JSON from the result
        # remove the trailing comma so the parsing wont fail
        areas_json = f'[{areas_response.text[:-1]}]'
        areas = json.loads(areas_json)
        # make all area names lowercase
        # this will help the LLM understand as different capitalization can sometimes be tokenized differently
        for area in areas:
            area['area_name'] = area['area_name'].lower()
        return areas

    def get_shopping_list(self):
        shopping_list_response = requests.get(f'{self.base_url}/api/shopping_list',
                                            headers={"Authorization": f"Bearer {self.access_token}"})

        shopping_list = shopping_list_response.json()
        return shopping_list

    def get_documents(self):
        return self.current_initial_values

    def get_llm_prompt_addition(self, document, user_prompt):
        examples = []
        llm_prompt = ""
        match document['type']:
            case "shopping_list":
                shopping_list = self.get_shopping_list()
                llm_prompt = llm_prompt + 'Shopping list contents:\n'
                for shopping_list_item in shopping_list:
                    llm_prompt = llm_prompt + f"- {shopping_list_item['name']}\n"
                examples.append(
                    (
                        'Add eggs to the shopping list.',
                        'Eggs were successfully added to the shopping list. $ActionRequired {"service": "shopping_list.add_item", "name": "eggs"}"'
                    )
                )
                sample_shopping_list_item = 'chicken'
                if shopping_list:
                    sample_shopping_list_item = random.choice(shopping_list)['name']
                examples.append(
                    (
                        'Remove ' + sample_shopping_list_item + ' from the shopping list.',
                        sample_shopping_list_item + ' was removed from the shopping list. $ActionRequired {"service": "shopping_list.remove_item", "name": "' + sample_shopping_list_item + '"}'
                    )
                )
            case "area":
                summary_template_edited = self.summary_template.replace('{{AREA_NAME}}', document['area_name'])
                summary_template_edited = summary_template_edited.replace('{{AREA_ID}}', document['area_id'])
                summary_template_edited = summary_template_edited.replace('{{IGNORED_ENTITIES}}', json.dumps(self.ignored_entities))
                summary = requests.post(f'{self.base_url}/api/template',
                                        json={"template": summary_template_edited},
                                        headers={"Authorization": f"Bearer {self.access_token}"}).text

                llm_prompt = llm_prompt + f"""
{document['area_name']} (Area ID: {document['area_id']}):

{summary}

                """
                examples.append(
                    (
                        f'Brighten the {document["area_name"]} lights.',
                        'The ' + document["area_name"] + ' lights are set to 100% brightness. $ActionRequired {"service": "light.turn_on", "brightness_pct": 100, "area_id": "' + document['area_id'] + '"}'
                    )
                )

                area_lights_template_edited = self.area_lights_template.replace('{{AREA_NAME}}', document['area_name'])
                area_lights_template_edited = area_lights_template_edited.replace('{{AREA_ID}}', document['area_id'])
                area_lights_status = requests.post(f'{self.base_url}/api/template',
                        json={"template": area_lights_template_edited},
                        headers={"Authorization": f"Bearer {self.access_token}"}).text
                examples.append(
                    (
                        f'Are the {document["area_name"]} lights on?',
                        area_lights_status + ' $NoActionRequired'
                    )
                )

                examples.append(
                    (
                        f'Turn off the {document["area_name"]} lights.',
                        'The ' + document["area_name"] + ' lights are now off. $ActionRequired {"service": "light.turn_off", "area_id": "' + document['area_id'] + '"}'
                    )
                )
            case "laundry":
                summary = requests.post(f'{self.base_url}/api/template',
                                        json={"template": self.laundry_template},
                                        headers={"Authorization": f"Bearer {self.access_token}"}).text

                llm_prompt = llm_prompt + f"""

{summary}

                """
            case "media_player":
                summary = requests.post(f'{self.base_url}/api/template',
                                        json={"template": self.media_player_template},
                                        headers={"Authorization": f"Bearer {self.access_token}"}).text
                if not summary.strip():
                    summary = "No media is playing in the household right now."

                llm_prompt = llm_prompt + f"""

{summary}

                """
            case "person":
                summary = requests.post(f'{self.base_url}/api/template',
                                        json={"template": self.person_template},
                                        headers={"Authorization": f"Bearer {self.access_token}"}).text

                llm_prompt = llm_prompt + f"""

{summary}

                """
            case "color_loop":
                summary = requests.post(f'{self.base_url}/api/template',
                                        json={"template": self.color_loop_template},
                                        headers={"Authorization": f"Bearer {self.access_token}"}).text

                llm_prompt = llm_prompt + f"""

{summary}

                """
        return {
            "prompt": llm_prompt,
            "examples": examples
        }
