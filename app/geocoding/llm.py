import json
import logging
import os

import google.generativeai as genai
import google.ai.generativelanguage as generativelanguage

from app.models.metadata import Metadata


def create_model() -> genai.GenerativeModel | None:
    if not os.getenv("GOOGLE_GEMINI_API_KEY"):
        return None

    genai.configure(api_key=os.getenv("GOOGLE_GEMINI_API_KEY"))

    # Set up the model
    generation_config = genai.GenerationConfig(
        temperature=0.9,
        max_output_tokens=2048,
        top_p=1.0,
        top_k=1,
    )

    safety_settings = [
        {
            "category": generativelanguage.HarmCategory.HARM_CATEGORY_HARASSMENT,
            "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE,
        },
        {
            "category": generativelanguage.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE,
        },
        {
            "category": generativelanguage.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE,
        },
        {
            "category": generativelanguage.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            "threshold": genai.types.HarmBlockThreshold.BLOCK_NONE,
        },
    ]

    return genai.GenerativeModel(
        model_name="gemini-1.0-pro",
        generation_config=generation_config,
        safety_settings=safety_settings,
    )


def generate_content(model: genai.GenerativeModel, prompt: str | list[str]) -> str:
    return model.generate_content(prompt).text


def extract_address(
    model: genai.GenerativeModel, transcript: str, metadata: Metadata
) -> dict[str, str] | None:
    prompt = [
        "You are a 911 dispatch transcript analyzer. You respond only in JSON. You return the address, city, and state found in a given transcript, if an address is present. If no address is present, you return null. Use the additional talkgroup data in determining the city and state.\n",
        f"Department: {metadata['talkgroup_group']}",
        f"Radio Channel: {metadata['talkgroup_description']}",
        f"Transcript: {transcript}",
    ]
    if os.getenv("GEOCODING_STATE"):
        prompt.insert(1, f"State: {os.getenv('GEOCODING_STATE')}")

    logging.debug("Prompt: " + "\n".join(prompt))
    try:
        output = generate_content(model, prompt)
        logging.debug("Generated content: " + output)
        result = json.loads(output[output.index("{") : output.rindex("}") + 1])
        if result["address"] and result["city"] and result["state"]:
            return {
                "address": result["address"],
                "city": result["city"],
                "state": result["state"],
            }
    except Exception as e:
        logging.debug(e)

    return None
