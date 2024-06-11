import asyncio
from env_canada import ECWeather

class Adapter:
    def __init__(self, config, utils):
        if 'station_id' in config:
            self.ECWeather = ECWeather(station_id=config["station_id"])
        elif 'coordinates' in config:
            self.ECWeather = ECWeather(coordinates=config["coordinates"])
        else:
            raise Exception("station_id or coordinates must be defined in the configuration!")
        self.utils = utils
        self.values_to_use = [
            "temperature",
            "wind_chill",
            "humidex",
            "humidity",
            "condition",
            "wind_speed",
            "wind_gust",
            "high_temp",
            "low_temp",
            "pop",
            "text_summary",
            "Forecast"
        ]

    def update(self):
        asyncio.run(self.ECWeather.update())

    def get_documents(self):
        # for now, let's only give one category for the weather
        title = "The current weather conditions and weather forecast for the next week."
        return [
            {
                "title": title,
                "embedding": self.utils['get_embedding'](title)
            }
        ]
    
    def augment_summary(self, data):
        summary = []
        text_summary = ""
        for key, data in data.items():
            label = data["label"]
            value = self.format_value(data.get("value"), data.get("unit"))
            if key in self.values_to_use:
                if value:
                    if key == "text_summary":
                        text_summary = value
                        continue
                    summary.append(f"{label}: {value}")

        if 'text_summary' in data:
            summary.append(data["text_summary"]["value"])
        if 'Forecast' in data:
            summary.append(data["text_summary"]["value"])

        augmented_summary = (
            text_summary + ' ' +
            ", ".join([s for s in summary if "Temperature" in s or "Condition" in s or "Wind" in s]) + ". "
        )

        return augmented_summary

    def get_llm_prompt_addition(self, selected_categories, user_prompt):
        llm_prompt = ""
        # we don't need examples as the weather tends to be fairly self-explanatory
        examples = []

        llm_prompt = "Current weather conditions: " + self.augment_summary(self.ECWeather.conditions)
        for forecast in self.ECWeather.daily_forecasts:
            summary = f"{forecast['text_summary']} Expected temperature: {forecast['temperature']}"
            llm_prompt = llm_prompt + f"\nWeather forecast for {forecast['period']}: {summary}"
        return {
            "prompt": llm_prompt,
            "examples": examples
        }

    def format_value(self, value, unit=None):
        if value is None:
            return ""
        elif unit:
            return f"{value} {unit}"
        else:
            return str(value)

