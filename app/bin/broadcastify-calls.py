#!/usr/bin/env python3

import functools
import sys
import argparse
import json
import logging
import os
import tempfile
import time
from uuid import uuid4

import requests
from dotenv import load_dotenv

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.utils import api_client

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36 Edg/112.0.1722.64"
TAGS = {
    1: "Multi-Dispatch",
    2: "Law Dispatch",
    3: "Fire Dispatch",
    4: "EMS Dispatch",
    6: "Multi-Tac",
    7: "Law Tac",
    8: "Fire-Tac",
    9: "EMS-Tac",
    11: "Interop",
    12: "Hospital",
    13: "Ham",
    14: "Public Works",
    15: "Aircraft",
    16: "Federal",
    17: "Business",
    20: "Railroad",
    21: "Other",
    22: "Multi-Talk",
    23: "Law Talk",
    24: "Fire-Talk",
    25: "EMS-Talk",
    26: "Transportation",
    29: "Emergency Ops",
    30: "Military",
    31: "Media",
    32: "Schools",
    33: "Security",
    34: "Utilities",
    35: "Data",
    36: "Deprecated",
    37: "Corrections",
}
GET_NEW_CALLS_INTERVAL = 5


http = requests.Session()
http.request = functools.partial(http.request, timeout=10)  # type: ignore


def bcfy_login(redirect_path: str):
    r = http.post(
        "https://www.broadcastify.com/login/",
        headers={
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-US,en;q=0.9",
            "cache-control": "max-age=0",
            "Referer": "https://www.broadcastify.com/calls/",
            "user-agent": USER_AGENT,
        },
        data={
            "username": os.getenv("BCFY_USER"),
            "password": os.getenv("BCFY_PASS"),
            "action": "auth",
            "redirect": redirect_path,
        },
        allow_redirects=False,
    )
    r.raise_for_status()
    if "bcfyuser1" not in r.cookies:
        raise Exception("Did not find Broadcastify session cookie")
    logging.info("Logged in successfully to Broadcastify.")
    return r.cookies


def process_calls(
    short_name: str,
    systemId: int = 0,
    sid: int = 0,
    onlyTalkgroups: list[int] = [],
    transcribe: bool = True,
    openmhz: bool = False,
    rdio: bool = False,
):
    request_time = time.time()
    pos = request_time - GET_NEW_CALLS_INTERVAL
    sessionKey = str(uuid4())[:13]
    doInit = 1
    path = f"/calls/{'trs/' + str(sid) if sid else 'node/' + str(systemId)}"
    jar = bcfy_login(path)

    while True:
        logging.debug("Making request to Broadcastify")
        r = http.post(
            "https://www.broadcastify.com/calls/apis/live-calls",
            data={
                "pos": round(pos),
                "doInit": doInit,
                "systemId": systemId,
                "sid": sid,
                "sessionKey": sessionKey,
            },
            headers={
                "origin": "https://www.broadcastify.com",
                "referer": f"https://www.broadcastify.com{path}",
                "user-agent": USER_AGENT,
                "x-requested-with": "XMLHttpRequest",
            },
            cookies=jar,
        )
        if r.status_code == 403:
            jar = bcfy_login(path)
            continue
        r.raise_for_status()
        doInit = 0

        calls = r.json()["calls"]

        logging.debug(f"Processing {len(calls)} calls")
        for call in calls:
            if len(onlyTalkgroups) == 0 or call["call_tg"] in onlyTalkgroups:
                try:
                    process_call(call, short_name, jar, transcribe, openmhz, rdio)
                except Exception as e:
                    logging.error(
                        f"Got exception while trying to process call: {repr(e)}",
                        exc_info=e,
                    )

        # If it took less than 5s to process calls, wait up to 5s
        execution_time = time.time() - request_time
        if execution_time < GET_NEW_CALLS_INTERVAL:
            time.sleep(GET_NEW_CALLS_INTERVAL - execution_time)

        request_time = time.time()
        lastPos = r.json()["lastPos"]
        if lastPos:
            pos = lastPos + 1


def process_call(
    call: dict,
    short_name: str,
    jar,
    transcribe: bool = True,
    openmhz: bool = False,
    rdio: bool = False,
):
    if "metadata" in call:
        metadata = call["metadata"]
        metadata["short_name"] = short_name
        metadata["talkgroup_tag"] = call["display"]
        metadata["talkgroup_description"] = call["descr"]
        metadata["talkgroup_group"] = call["grouping"]
        metadata["talkgroup_group_tag"] = TAGS[call["tag"]]
    else:
        freq = int(call["call_freq"] * 1e6)

        metadata = {
            "freq": freq,
            "start_time": call["meta_starttime"],
            "stop_time": call["meta_stoptime"],
            "emergency": 0,
            "encrypted": 0,
            "call_length": call["call_duration"],
            "talkgroup": call["call_tg"],
            "talkgroup_tag": call["display"],
            "talkgroup_description": call["descr"],
            "talkgroup_group_tag": TAGS[call["tag"]],
            "talkgroup_group": call["grouping"],
            "audio_type": "digital",
            "short_name": short_name,
            "freqList": [
                {
                    "freq": freq,
                    "time": call["meta_starttime"],
                    "pos": 0.0,
                    "len": call["call_duration"],
                    "error_count": "0",
                    "spike_count": "0",
                }
            ],
            "srcList": [
                {
                    "src": call["call_src"],
                    "time": call["meta_starttime"],
                    "pos": 0.0,
                    "emergency": 0,
                    "signal_system": "",
                    "tag": "",
                }
            ],
        }

    logging.debug(metadata)

    extension = call["enc"] if call["enc"] else "m4a"
    url = f"https://calls.broadcastify.com/{call['hash']}/{call['systemId']}/{call['filename']}.{extension}"
    logging.debug(f"Downloading {url}")
    with http.get(url, cookies=jar, stream=True) as r:
        r.raise_for_status()
        with (
            tempfile.NamedTemporaryFile(suffix=".json") as metadata_file,
            tempfile.NamedTemporaryFile(suffix=f".{extension}") as audio_file,
        ):
            metadata_file.write(bytes(json.dumps(metadata), encoding="utf-8"))
            metadata_file.flush()
            metadata_file.seek(0)

            for chunk in r.iter_content(chunk_size=1024 * 1024):
                audio_file.write(chunk)
            audio_file.flush()
            audio_file.seek(0)

            if transcribe:
                try:
                    logging.info(
                        f"Queueing call on '{call['display']}' (TG {call['call_tg']}) for transcription - {url}"
                    )
                    api_client.call(
                        "POST",
                        "calls",
                        files={"call_json": metadata_file, "call_audio": audio_file},
                    )
                    audio_file.seek(0)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code > 400:
                        raise e

            if openmhz:
                logging.info(
                    f"Sending call on '{call['display']}' (TG {call['call_tg']}) to OpenMHz - {url}"
                )
                data = {
                    "api_key": os.getenv("OPENMHZ_API_KEY", ""),
                    "freq": metadata["freq"],
                    "start_time": metadata["start_time"],
                    "stop_time": metadata["stop_time"],
                    "call_length": metadata["call_length"],
                    "talkgroup_num": metadata["talkgroup"],
                    "emergency": metadata["emergency"],
                    "source_list": json.dumps(metadata["srcList"]),
                }
                r = http.post(
                    f"https://api.openmhz.com/{os.getenv('OPENMHZ_SYSTEM', short_name)}/upload",
                    data=data,
                    files={"call": (f"{call['filename']}.m4a", audio_file)},
                )
                audio_file.seek(0)
                r.raise_for_status()

            if rdio:
                logging.info(
                    f"Sending call on '{call['display']}' (TG {call['call_tg']}) to Rdio Scanner - {url}"
                )
                data = {
                    "key": os.getenv("RDIO_API_KEY", ""),
                    "system": os.getenv("RDIO_SYSTEM_ID", ""),
                    "systemLabel": metadata["short_name"],
                    "dateTime": metadata["start_time"],
                    "talkgroup": metadata["talkgroup"],
                    "frequency": metadata["freq"],
                    "frequencies": json.dumps(metadata["freqList"]),
                    "source": call["call_src"],
                    "sources": json.dumps(metadata["srcList"]),
                    "talkgroupGroup": metadata["talkgroup_group"],
                    "talkgroupLabel": metadata["talkgroup_tag"],
                    "talkgroupTag": metadata["talkgroup_group_tag"],
                    "talkgroupName": metadata["talkgroup_description"],
                }
                r = http.post(
                    f"{os.getenv('RDIO_URL', '')}/api/call-upload",
                    data=data,
                    files={"audio": (f"{call['filename']}.{extension}", audio_file)},
                )
                audio_file.seek(0)
                r.raise_for_status()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe calls from Broadcastify")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--node-id",
        type=int,
        metavar="ID",
        help="Node ID",
    )
    parser.add_argument(
        "--system-id",
        type=int,
        metavar="ID",
        help="System ID",
    )
    parser.add_argument(
        "--short-name",
        type=str,
        required=True,
        help="Short name to use",
    )
    parser.add_argument(
        "--talkgroups",
        type=str,
        metavar="TGIDS",
        help="Comma seperated list or range of talkgroups to limit uploads to",
    )
    parser.add_argument(
        "--transcribe",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Whether or not to send the calls to be transcribed",
    )
    parser.add_argument(
        "--openmhz",
        default=False,
        action=argparse.BooleanOptionalAction,
        help="Whether or not to send the calls to OpenMHz.com",
    )
    parser.add_argument(
        "--rdio",
        default=False,
        action=argparse.BooleanOptionalAction,
        help="Whether or not to send the calls to Rdio Scanner",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if (args.node_id and args.system_id) or (not args.node_id and not args.system_id):
        logging.error("You must specify either a node ID or a system ID")
        sys.exit(1)

    onlyTalkgroups = []
    if args.talkgroups:
        for item in args.talkgroups.split(","):
            if "-" in item:
                bounds = item.split("-")
                for i in range(int(bounds[0]), int(bounds[1]) + 1):
                    onlyTalkgroups.append(i)
            else:
                onlyTalkgroups.append(int(item))

    process_calls(
        short_name=args.short_name,
        systemId=args.node_id,
        sid=args.system_id,
        onlyTalkgroups=onlyTalkgroups,
        transcribe=args.transcribe,
        openmhz=args.openmhz,
        rdio=args.rdio,
    )
