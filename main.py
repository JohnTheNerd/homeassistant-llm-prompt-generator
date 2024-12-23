import aiohttp
from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import importlib.util
import json
import logging
import numpy as np
import requests
import time
import threading
from typing import Optional

app = FastAPI()

config_path = os.environ.get('CONFIG_PATH', 'config.json')

with open(config_path) as f:
    config = json.load(f)
    users_config = config.get('users', {})

logging.basicConfig(level=config['log_level'], format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

api_key = config['embedding_api_key']

def compute_similarity(first, second):
    dot_product = np.dot(first, second)
    magnitude_product = np.linalg.norm(first) * np.linalg.norm(second)
    cosine_similarity = dot_product / magnitude_product
    return cosine_similarity

def instantiate_plugins(directory, config):
    plugins = []
    utils = {
        "get_embedding": get_embedding,
        "get_embedding_async": get_embedding_async,
        "compute_similarity": compute_similarity
    }
    if 'plugins' in config:
        for module_name in config['plugins']:
            spec = importlib.util.spec_from_file_location(module_name, os.path.join(directory, f'{module_name}.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            obj = getattr(module, 'Adapter')
            if hasattr(obj, "__class__") and callable(obj):
                plugin_config = config['plugins'].get(module_name, {})
                plugin_class = obj(plugin_config, utils)
                plugins.append({
                    "name": module_name,
                    "class": plugin_class
                })
    return plugins

def get_plugins(user_name):
    relevant_plugins = []
    user_plugin_names = []
    if not user_name:
        return plugins
    for user_plugin in plugins_by_user[user_name]:
        relevant_plugins.append(user_plugin)
        user_plugin_names.append(user_plugin['name'])
    for plugin in plugins:
        if plugin['name'] not in user_plugin_names:
            relevant_plugins.append(plugin)
    return relevant_plugins

def update_plugins_thread():
    while True:
        time.sleep(config['update_interval'])
        update_plugins()

def update_plugins():
    for plugin in plugins:
        try:
            plugin["class"].update()
        except Exception as e:
            logger.error(f"Error updating plugin {plugin['name']}: {str(e)}")

        if plugins_by_user:
            for user_name in plugins_by_user:
                for plugin in plugins_by_user[user_name]:
                    try:
                        plugin["class"].update()
                    except Exception as e:
                        logger.error(f"Error updating plugin {plugin['name']} for user {user_name}: {str(e)}")

def get_embedding(prompt):
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {"model": config['embedding_model'], "input": prompt}
    response = requests.post(f"{config['embedding_base_url']}/embeddings", headers=headers, json=data, timeout=10)

    if response.status_code == 200:
        embedding = response.json()["data"]
        return embedding[0]['embedding']
    else:
        logger.error(f"Error: {response.status_code}")
        return response

async def get_embedding_async(prompt):
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {"model": config['embedding_model'], "input": prompt}
        async with session.post(f"{config['embedding_base_url']}/embeddings", headers=headers, json=data) as response:
            if response.status == 200:
                embedding = await response.json()
                return embedding["data"][0]['embedding']
            else:
                logger.error(f"Error: {response.status}")
                return response

def compute_similarity(first, second):
    dot_product = np.dot(first, second)
    magnitude_product = np.linalg.norm(first) * np.linalg.norm(second)
    cosine_similarity = dot_product / magnitude_product
    return cosine_similarity

def compute_plugin_similarities(prompt_embedding, plugins_to_use):
    similarities = []
    for plugin in plugins_to_use:
        plugin_name = plugin['name']
        plugin_class = plugin['class']
        documents = plugin_class.get_documents()
        for document in documents:
            document_embedding = document['embedding']
            similarity = compute_similarity(prompt_embedding, document_embedding)
            similarities.append({
                "document": document,
                "similarity": similarity,
                "plugin_name": plugin_name
            })
    return similarities


async def process_prompt(user_prompt, plugins_to_use):
    prompt_embedding = await get_embedding_async(user_prompt)
    similarities = compute_plugin_similarities(prompt_embedding, plugins_to_use)
    logger.debug(f'similarities: {similarities}')
    for similarity in similarities:
        logger.debug(f'cosine similarity between "{user_prompt}" and "{similarity["document"]["title"]}" is {similarity["similarity"]}')
    similarities.sort(key=lambda x: x['similarity'], reverse=True)
    selected_results = similarities[:config['number_of_results']]
    llm_prompt = ""
    examples = []
    for result in selected_results:
        document_title = result['document']['title']
        similarity = result['similarity']
        plugin_name = result['plugin_name']
        logger.debug(f'selected "{document_title}" with a cosine similarity of {similarity}')
        for plugin in plugins_to_use:
            if plugin['name'] == plugin_name:
                plugin_class = plugin['class']
                prompt_addition = plugin_class.get_llm_prompt_addition(result['document'], user_prompt)
                logger.debug(f'prompt_addition: {prompt_addition}')
                llm_prompt = llm_prompt + prompt_addition['prompt'].strip()
                llm_prompt = llm_prompt + '\n\n\n'
                for example in prompt_addition['examples']:
                    examples.append(example)
    if 'include_examples' in config and config['include_examples'] == True:
        if examples:
            llm_prompt = llm_prompt.strip() + '\n\n\nFind examples below. Reword the answers to fit your personality. Prompts are given as Q: and the example answers are given as A:\n\n'
            for example in examples:
                question = example[0]
                answer = example[1]
                llm_prompt = f'{llm_prompt}Q:{question}\nA:{answer}\n\n'
    llm_prompt = llm_prompt.strip()
    return llm_prompt

@app.post("/prompt")
async def process_prompt_endpoint(
    user_prompt: str = Body(..., embed=True),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer()) if users_config else None,
):
    user_name = None
    if users_config:
        for user, user_data in users_config.items():
            if credentials.scheme.lower() == 'bearer' and credentials.credentials == user_data['token']:
                user_name = user
                break
        else:
            raise HTTPException(status_code=401, detail='Unauthorized')
    plugins_to_use = get_plugins(user_name)
    llm_prompt = await process_prompt(user_prompt, plugins_to_use)
    return JSONResponse(content={"prompt": llm_prompt}, media_type="application/json")

@app.post("/update")
async def update_plugins_endpoint(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer()) if users_config else None,
):
    if users_config:
        for user, user_data in users_config.items():
            if credentials.scheme.lower() == 'bearer' and credentials.credentials == user_data['token']:
                break
        else:
            raise HTTPException(status_code=401, detail='Unauthorized')
    update_plugins()
    return JSONResponse(content={"success": True}, media_type="application/json")

plugins_directory = "plugins"
plugins = instantiate_plugins(plugins_directory, config)
plugins_by_user = {}
if users_config:
    for user_name in users_config:
        user_data = users_config[user_name]
        plugins_by_user[user_name] = instantiate_plugins(plugins_directory, user_data)

if __name__ == "__main__":
    update_plugins()
    update_thread = threading.Thread(target=update_plugins_thread)
    update_thread.daemon = True
    update_thread.start()
    logger.info("Update started, starting API")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)