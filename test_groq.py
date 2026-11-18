
import os
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# Find .env in the same folder as this test file
env_path = Path(__file__).resolve().parent / "backend" / ".env"

print("Checking .env:", env_path.exists())

load_dotenv(dotenv_path=env_path, override=True)

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

if not api_key:
    print("ERROR: GROQ_API_KEY not found.")
else:
    try:
        client = Groq(api_key=api_key, timeout=30)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful and friendly assistant."
                },
                {
                    "role": "user",
                    "content": "Say hello and introduce yourself in one sentence."
                }
            ],
            temperature=0.5,
            max_tokens=150
        )

        print("\nGROQ SUCCESS!")
        print(response.choices[0].message.content)

    except Exception as e:
        print("\nGROQ FAILED!")
        print(type(e).__name__, str(e))
