import requests
import json
from cachetools import cached, TTLCache

class Adapter:
    def __init__(self, config, utils):
        self.access_token = config["access_token"]
        self.base_url = config["base_url"]
        self.current_initial_values = None
        self.utils = utils
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
{%- set meaningless_entities = ['_power_source', '_learned_ir_code', '_sensor_battery', '_hooks_state', '_motor_state', '_target_position', '_button_action', '_vibration_sensor_x_axis', '_vibration_sensor_y_axis', '_vibration_sensor_z_axis', '_vibration_sensor_angle_x', '_vibration_sensor_angle_y', '_vibration_sensor_angle_z', '_vibration_sensor_device_temperature', '_vibration_sensor_action', '_vibration_sensor_power_outage_count', 'update.', '_motion_sensor_sensitivity', '_motion_sensor_keep_time', '_motion_sensor_sensitivity', '_curtain_driver_left_hooks_lock', '_curtain_driver_right_hooks_lock', 'sensor.cgllc_cgd1st_9254_charging_state', 'sensor.cgllc_cgd1st_9254_voltage', '_curtain_driver_left_hand_open', '_curtain_driver_right_hand_open', '_curtain_driver_left_device_temperature', 'curtain_driver_right_device_temperature', '_curtain_driver_left_running', '_curtain_driver_right_running', '_update_available'] %}
  {%- for device in area_devices({{AREA_ID}}) %}
    {%- if not device_attr(device, "disabled_by") and not device_attr(device, "entry_type") and device_attr(device, "name") %}
      {%- for entity in device_entities(device) %}
        {%- set ns = namespace(skip_entity=False) %}
        {%- set entity_domain = entity.split('.')[0] %}
        {%- if not is_state(entity,'unavailable') and not is_state(entity,'unknown') and not is_state(entity,"None") and not is_hidden_entity(entity) %}
          {%- set ns.skip_entity = false %}
          {%- for meaningless_entity in meaningless_entities %}
            {%- if meaningless_entity in entity|string %}
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
{%- set meaningless_entities = ['_power_source', '_learned_ir_code', '_sensor_battery', '_hooks_state', '_motor_state', '_target_position', '_button_action', '_vibration_sensor_x_axis', '_vibration_sensor_y_axis', '_vibration_sensor_z_axis', '_vibration_sensor_angle_x', '_vibration_sensor_angle_y', '_vibration_sensor_angle_z', '_vibration_sensor_device_temperature', '_vibration_sensor_action', '_vibration_sensor_power_outage_count', 'update.', '_motion_sensor_sensitivity', '_motion_sensor_keep_time', '_motion_sensor_sensitivity', '_curtain_driver_left_hooks_lock', '_curtain_driver_right_hooks_lock', 'sensor.cgllc_cgd1st_9254_charging_state', 'sensor.cgllc_cgd1st_9254_voltage', '_curtain_driver_left_hand_open', '_curtain_driver_right_hand_open', '_curtain_driver_left_device_temperature', 'curtain_driver_right_device_temperature', '_curtain_driver_left_running', '_curtain_driver_right_running', '_update_available'] %}
  {%- for device in area_devices({{AREA_ID}}) %}
    {%- if not device_attr(device, "disabled_by") and not device_attr(device, "entry_type") and device_attr(device, "name") %}
      {%- for entity in device_entities(device) %}
        {%- set ns = namespace(skip_entity=False) %}
        {%- set entity_domain = entity.split('.')[0] %}
        {%- if not is_state(entity,'unavailable') and not is_state(entity,'unknown') and not is_state(entity,"None") and not is_hidden_entity(entity) %}
          {%- set ns.skip_entity = false %}
          {%- for meaningless_entity in meaningless_entities %}
            {%- if meaningless_entity in entity|string %}
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

    def update(self):
        current_initial_values = []
        areas = self.get_areas()
        for area in areas:
            title_template_with_area = self.title_template.replace('{{AREA_ID}}', "'" + area['area_id'] + "'")
            title_template_with_area = title_template_with_area.replace('{{AREA_NAME}}', "'" + area['area_name'] + "'")
            title = requests.post(f'{self.base_url}/api/template',
                                    json={"template": title_template_with_area},
                                    headers={"Authorization": f"Bearer {self.access_token}"}).text
            area['title'] = title
            # see if we have any summary information at all
            # if we don't, do not include the area in the initial values
            if len(area['title'].split('\n')) > 1:
                area['embedding'] = self.utils['get_embedding'](title)
                current_initial_values.append(area)
        
        # add the shopping list manually as it is not represented in an area
        shopping_list_title = 'Shopping list for the entire household'
        current_initial_values.append({
            "type": "shopping_list",
            "title": shopping_list_title,
            "embedding": self.utils['get_embedding'](shopping_list_title)
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
        return areas

    def get_shopping_list(self):
        shopping_list_response = requests.get(f'{self.base_url}/api/shopping_list',
                                            headers={"Authorization": f"Bearer {self.access_token}"})

        shopping_list_dict = shopping_list_response.json()
        shopping_list = 'Shopping list contents:\n'
        for shopping_list_item in shopping_list_dict:
            shopping_list = shopping_list + f"- {shopping_list_item['name']}\n"
        
        return shopping_list

    def get_documents(self):
        return self.current_initial_values

    def get_llm_prompt_addition(self, document, user_prompt):
        # TODO add examples!
        examples = []
        llm_prompt = ""
        match document['type']:
            case "shopping_list":
                llm_prompt = llm_prompt + '\n' + self.get_shopping_list() + '\n'
            case "area":
                summary_template_with_area = self.summary_template.replace('{{AREA_ID}}', "'" + document['area_id'] + "'")
                summary = requests.post(f'{self.base_url}/api/template',
                                        json={"template": summary_template_with_area},
                                        headers={"Authorization": f"Bearer {self.access_token}"})

                llm_prompt = llm_prompt + f"""
{document['area_name']} (Area ID: {document['area_id']}):

{summary.text}

                """
        return {
            "prompt": llm_prompt,
            "examples": examples
        }
