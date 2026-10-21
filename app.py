from urllib import response

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Json
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
from starlette.responses import StreamingResponse

load_dotenv()  # This loads the key from the .env file automatically
app = FastAPI(title="External JSON API Agent")

client = genai.Client()


# --- 1. DEFINE THE WEB API TOOL ---
def fetch_online_json_data(resource: str) :
    """Fetches free public test data from JSONPlaceholder API.

    Args:
        resource: The dataset to fetch. Choose from 'users', 'posts', or 'todos'.
    """
    valid_resources = ["users", "posts", "todos"]
    if resource not in valid_resources:
        return f"Error: Invalid resource. Choose from {valid_resources}"

    url = f"https://jsonplaceholder.typicode.com/{resource}"

    try:
        # Use httpx to make the synchronous HTTP request to the external JSON API
        response = httpx.get(url, timeout=10.0)
        data = response.json()
        if resource == 'todos':
            yettodo = [item["title"] for item in data if item["completed"] == False]
            return ",".join(yettodo)
        return str(data)
    except Exception as e:
        return f"API Request Error: {str(e)}"

def create_online_todo(title: str):
    url = "https://jsonplaceholder.typicode.com/todos"
    payload = {
        "title": title,
        "completed": False,
        "userId": 1
    }
    try:
        # Use httpx.post to send data to the external API
        response = httpx.post(url, json=payload, timeout=10.0)

        if response.status_code == 201:
            result = response.json()
            return f"Successfully created! Assigned ID: {result.get('id')}, Title: '{result.get('title')}', Completed: {result.get('completed')}"
        else:
            return f"Failed to create todo. Server returned status code: {response.status_code}"

    except Exception as e:
        return f"API Request Error: {str(e)}"

def get_weather(city: str) -> str:
    """Gets the current weather for a given city using a live weather API.

    Args:
        city: The name of the city (e.g., 'Tokyo', 'London', 'New York').
    """
    try:
        # Step 1: Geocode city name to get lat/lon coordinates
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_res = httpx.get(geo_url, timeout=5.0).json()

        if not geo_res.get("results"):
            return f"Could not find coordinates for city: {city}"

        location = geo_res["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]
        country = location.get("country", "")

        # Step 2: Fetch current weather using coordinates
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        weather_res = httpx.get(weather_url, timeout=5.0).json()
        current = weather_res.get("current_weather", {})

        temp = current.get("temperature")
        windspeed = current.get("windspeed")

        return f"Weather in {city}, {country}: {temp}°C, Wind speed: {windspeed} km/h."
    except Exception as e:
        return f"Weather API Error: {str(e)}"

# --- 2. REQUEST & RESPONSE MODELS ---
class QueryRequest(BaseModel):
    prompt: str


# class QueryResponse(BaseModel):
#     answer: str


# --- 3. AGENT ENDPOINT ---
@app.post("/ask")
def ask_agent(request: QueryRequest):
    system_instruction = """
        You are an intelligent workflow assistant agent. You have access to tools that can fetch data 
        and tools that can create new records (like todos). 
        Choose the appropriate tool based on what the user wants to do, and provide a clear, natural response.
        """

    try:
        # response = client.models.generate_content(
        #     model="gemini-3.7-flash",
        #     contents=request.prompt,
        #     config=types.GenerateContentConfig(
        #         system_instruction=system_instruction,
        #         tools=[fetch_online_json_data],  # Pass the web-fetching function as a tool
        #         temperature=0.0
        #     ),
        # )
        #
        # return QueryResponse(answer=response.text)

        chat = client.chats.create(
            model="gemini-3.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[fetch_online_json_data, create_online_todo, get_weather],
            )
        )

        response_stream = chat.send_message_stream(request.prompt)
        def generate():
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        return StreamingResponse(generate(), media_type="text/plain")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.post("/create/todo", response_model=QueryResponse)
# def create_todo(request:QueryRequest):
#     system_instructions=("You are a helper, when a user wants to craete todo and calls this api, "
#                          "help them to create new todo by using 'create_online_todo'"
#                          "to create todos  as per their request")
#     chat = client.chats.create(model="gemini-3.5-flash",
#                                 config=types.GenerateContentConfig
#                                 (system_instructions=system_instructions,
#                                  tools=[create_online_todo],
#                                 temperature=0))
#     response = chat.send_message(request.prompt)
#     return QueryResponse(answer=response.text)