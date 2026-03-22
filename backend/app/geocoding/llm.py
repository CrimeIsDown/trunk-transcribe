import logging
import os
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel

from app.geocoding.types import AddressParts
from app.models.metadata import Metadata


class ExtractedAddress(BaseModel):
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


def create_model() -> OpenAI | None:
    if not os.getenv("GOOGLE_GEMINI_API_KEY"):
        return None

    return OpenAI(
        api_key=os.getenv("GOOGLE_GEMINI_API_KEY"),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


def extract_address(
    client: OpenAI, transcript: str, metadata: Metadata
) -> AddressParts | None:
    prompt_parts = [
        "You are a 911 dispatch transcript analyzer. Extract the address, city, and state from the given transcript if present. Use the additional talkgroup data to help determine the city and state.",
        f"Department: {metadata['talkgroup_group']}",
        f"Radio Channel: {metadata['talkgroup_description']}",
        f"Transcript: {transcript}",
    ]
    if os.getenv("GEOCODING_STATE"):
        prompt_parts.insert(1, f"State: {os.getenv('GEOCODING_STATE')}")

    prompt = "\n".join(prompt_parts)
    logging.debug("Prompt: " + prompt)

    try:
        response = client.beta.chat.completions.parse(
            model="gemini-2.5-flash-lite",
            messages=[{"role": "user", "content": prompt}],
            response_format=ExtractedAddress,
        )

        extracted = response.choices[0].message.parsed
        if extracted and extracted.address and extracted.city and extracted.state:
            return AddressParts(
                {
                    "address": extracted.address,
                    "city": extracted.city,
                    "state": extracted.state,
                }
            )
    except Exception as e:
        logging.debug(f"Error extracting address: {e}")

    return None
