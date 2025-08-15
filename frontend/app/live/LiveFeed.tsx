'use client';

import moment from 'moment';
import React, { useEffect, useState } from 'react';
import { Hit } from '../Hit';

interface Geo {
  lat: number;
  lng: number;
  geo_formatted_address: string;
}

interface Source {
  pos: number;
  src: number;
  tag: string;
  time: number;
  emergency: number;
  signal_system: string;
  transcript_prompt: string;
}

interface Message {
  geo: Geo | null;
  transcript_plaintext: string;
  id: number;
  raw_transcript: [Source, string][];
  raw_metadata: any;
  raw_audio_url: string;
  start_time: string;
}

const processMessage = (message: Message) => {
  let hit: any = message.raw_metadata;
  hit.id = message.id;
  hit = {...hit, ...message.geo};
  hit.raw_audio_url = message.raw_audio_url;
  hit.raw_transcript = message.raw_transcript;
  hit.json = JSON.stringify(message, null, 2);

  if (hit.audio_type == 'digital tdma') {
    hit.audio_type = 'digital';
  }
  hit.audio_type = hit.audio_type.charAt(0).toUpperCase() + hit.audio_type.slice(1);

  switch (hit.talkgroup_group_tag) {
    case 'Law Dispatch':
    case 'Law Tac':
    case 'Law Talk':
    case 'Security':
      hit.talkgroup_group_tag_color = 'primary';
      break;
    case 'Fire Dispatch':
    case 'Fire-Tac':
    case 'Fire-Talk':
    case 'EMS Dispatch':
    case 'EMS-Tac':
    case 'EMS-Talk':
      hit.talkgroup_group_tag_color = 'danger';
      break;
    case 'Public Works':
    case 'Utilities':
      hit.talkgroup_group_tag_color = 'success';
      break;
    case 'Multi-Tac':
    case 'Emergency Ops':
      hit.talkgroup_group_tag_color = 'warning';
      break;
    default:
      hit.talkgroup_group_tag_color = 'secondary';
  }

  let start_time = moment.unix(hit.start_time);
  if (hit.short_name == 'chi_cpd' && hit.encrypted) {
    hit.time_warning = ` - delayed until ${start_time
        .toDate()
        .toLocaleTimeString()}`;
    start_time = start_time.subtract(30, 'minutes');
  }
  hit.start_time_ms = hit.start_time * 1000 + 1; // Add 1 since OpenMHz shows calls older than the specified time, and we want to include the current one
  hit.start_time_string = start_time.toDate().toLocaleString();
  hit.relative_time = start_time.fromNow();

  for (let i = 0; i < hit.raw_transcript.length; i++) {
    const segment = hit.raw_transcript[i];
    const src = segment[0];
    if (src) {
      src.filter_link = '#';
      if (src.tag.length > 0) {
        src.label = src.tag;
      } else {
        src.label = String(src.src);
      }
    }
    // Show newlines properly
    segment[1] = segment[1].replaceAll('\n', '<br>');
  }

  return hit;
};

const websocketUrl = (process.env.WEBSOCKET_URL || 'ws://localhost:8000/ws') + '?api_key=' + (process.env.API_KEY || 'testing');

const LiveFeed = () => {
  const [hits, setHits] = useState<any[]>([]);

  useEffect(() => {
    const socket = new WebSocket(websocketUrl);

    socket.onmessage = (event) => {
      const message: Message = JSON.parse(event.data);
      const hit = processMessage(message);
      setHits((prevHits) => [hit, ...prevHits]);
    };

    return () => {
      socket.close();
    };
  }, []);

  return (
    <>
      <h1>Live Feed</h1>
      {hits.map((hit) => (
        <Hit key={hit.id} hit={hit} />
      ))}
    </>
  );
};

export default LiveFeed;
