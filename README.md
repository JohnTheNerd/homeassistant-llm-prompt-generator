# HomeAssistant LLM Prompt Generator

# Introduction

The current de-facto method of using LLMs to automate a smart home involves sending *the entire smart home state* as part of the context. This is insanely slow for local LLM's (especially if you are running without GPUs, as prefill times tend to be llama.cpp's bottleneck), and can get expensive over time for cloud LLM API's. However, in practice, most of this state is not even relevant to what you just asked your assistant!

This repository implements RAG (Retrieval Augmented Generation) to optimize the state that is sent in the first place, which massively reduces the amount of information we need to feed the LLM's. I decided to make this a separate API instead of adding even more logic to the forked HomeAssistant integration in order to more easily add additional information that is not accessible to HomeAssistant, and it honestly just works better with my home infrastructure.

# Usage

- Clone this repository

- Copy `config.sample.json` to `config.json` and update all fields accordingly. Alternatively, set the environment variable `CONFIG_PATH` to where your configuration is located.

    - If you are using a cloud embedding model, beware that the update function re-embeds everything each time, even if the values are static. You may want to set a large `update_interval` or monitor your costs. I'm sure it's not too difficult to cache matching embeddings either. PR's are very welcome!

    - If you would like authentication, use `config.auth.sample.json` instead of `config.json`. You can override plugins per user, as you can see in the example. If authentication is used, all requests are required to have an `Authorization: Bearer <TOKEN>` HTTP header and will otherwise receive a HTTP 401.

    - If you do not want in-context learning via examples, simply disable `include_examples`. Keep in mind that the examples are dynamically generated, do not require any additional configuration, and can be quite useful!

- Run `pip3 install -r requirements.txt` (or build/run the Docker image from the Dockerfile)

- Run `python3 main.py` and the API should be available on port 8000. The only endpoint available is `/prompt` which is a POST that expects a JSON body. The JSON body should have `user_prompt` set as the user prompt.

# Plugins

## Calendar

Reads a number of calendars via CalDAV. Returns all events in the next week. Since it creates a lot of examples, it will also randomly sample them as an attempt to reduce the number of tokens we send to the LLM. You can set `example_count` to the maximum number of examples you wish to have (some are conditional, so you cannot know exactly how many examples will be returned at any time).

The plugin expects a list of objects at `calendars`. Each calendar object must have a `url` which is the CalDAV URL. It can optionally have a `username` and `password` for HTTP Basic Authentication.


## HomeAssistant

All fields in the sample configuration are required. This plugin has several functions, all of which can be toggled from the config file:

- Areas: All entities belonging to all devices in each area. This is grouped by area, where each area is a separate document to be searched for. The LLM prompt addition is the states of all devices, and there are a few examples with lights.

- Shopping list: The shopping list, as defined in HomeAssistant. Includes examples to add/remove items from the shopping list. It is recommended you keep these examples as I found that LLM's otherwise tend to find it hard to manipulate the shopping list.

- Person: Defines every person and whether they are home. No examples as it is very self-explanatory.

- Laundry and Color Loop: Currently extremely custom and is mostly meant for me to use. Feel free to use them if they help you, but it's likely that you will need to change the templates.

`ignored_entities` ignores the entities given in the list. It is a substring search. If you want all entities to be part of the LLM prompt, simply make it an empty list.


## Weather

Currently only pulls information from Environment Canada.

Expects either a `station_id` or `coordinates` as defined in the [PyPI page of env-canada](https://pypi.org/project/env-canada/). Returns the current weather summary and the forecast for the next week. Does not include any examples.


# Creating plugins

Plugins are merely Python scripts that are in the plugins directory. You must define a class named `Adapter` and the following functions:

- `__init__()`: Initialization code. Set arguments of `config` and `utils`. `config` will contain the plugin configuration as a dictionary, and `utils` is a dictionary consisting of functions to get embeddings of any text (`get_embedding` and `get_embedding_async`) and get cosine similarity of two sets of embeddings (`compute_similarity`).

- `update()`: This will run every once in a while, at an interval determined by the user. Do not accept any arguments. You should use this to cache as much information as possible, as it runs in the background.

- `get_documents()`: This is where you return all the "documents" for RAG. Do not accept any arguments. The user prompt will be queried against your documents. This should run as fast as possible, ideally only returning an object you created and cached by `update()`. You must return a dictionary with `title` as what the prompt should be searched against, and `embedding` as the embedding of it. You may add additional information to help you in the function below, as you will receive that object back. The best way to get the embeddings is to call `utils['get_embedding'](your_title)` from `update()` and cache it locally.

- `get_llm_prompt_addition()`: This is where you return the LLM prompt (and optionally, examples). It is only called if the user prompt is determined to require your plugin's input. Accept two arguments, `document` and `user_prompt`. `document` is one of the documents you returned from `get_documents()` and `user_prompt` is merely the prompt that was received from the user. This should still run reasonably quickly, but don't have to be as cautious as `get_documents()`. You must return a dictionary with `prompt` set to the text you would like to append to the LLM prompt, and `examples` as a list of tuples. The tuples should be (question, answer). If you do not need in-context learning in your plugin, simply return `examples` as an empty list.