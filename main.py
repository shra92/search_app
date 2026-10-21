import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="SQLite Text-to-SQL Agent")

client = genai.Client()

DB_FILE = "shop.db"


# --- 0. INITIALIZE A SAMPLE LOCAL DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL
        )
    """)
    # Insert some mock products if empty
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)", [
            ("Wireless Mouse", "Electronics", 29.99, 150),
            ("Mechanical Keyboard", "Electronics", 89.99, 45),
            ("Ergonomic Office Chair", "Furniture", 199.99, 12),
            ("Standing Desk", "Furniture", 349.99, 5),
            ("USB-C Hub", "Electronics", 19.99, 200)
        ])
        conn.commit()
    conn.close()


init_db()  # Run setup on startup


# --- 1. DEFINE DATABASE TOOLS ---
def get_database_schema() -> str:
    """Returns the schema information for the local SQLite database so the model knows what tables and columns are available."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        schema_info = []
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = [col[1] for col in cursor.fetchall()]
            schema_info.append(f"Table '{table_name}' with columns: {', '.join(columns)}")

        conn.close()
        return "\n".join(schema_info)
    except Exception as e:
        return f"Error fetching schema: {str(e)}"


def run_sql_query(query: str) -> str:
    """Executes a read-only SQL query on the local SQLite database and returns the results.

    Args:
        query: A valid SQLite SELECT SQL query.
    """
    # Basic safety check to ensure it's a read query
    if not query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries are permitted for safety reasons."

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        return str(rows)
    except Exception as e:
        return f"SQL Execution Error: {str(e)}"


# --- 2. REQUEST MODEL ---
class QueryRequest(BaseModel):
    prompt: str


# --- 3. AGENT ENDPOINT WITH STREAMING & SQL TOOLS ---
@app.post("/ask")
def ask_agent_stream(request: QueryRequest):
    system_instruction = """
    You are an expert database assistant agent. You have access to tools that can inspect 
    database schemas and execute SQL queries. 
    When a user asks a data question:
    1. First check the database schema if you aren't sure of the structure.
    2. Write and execute a precise SQL query using `run_sql_query`.
    3. Translate the raw database output rows into a clean, natural language response.
    """

    try:
        chat = client.chats.create(
            model="gemini-3.7-flash",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[get_database_schema, run_sql_query],
                temperature=0.0
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