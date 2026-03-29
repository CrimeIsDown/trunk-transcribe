import { describe, expect, it } from 'vitest'

import { extractTranscriptGeoPoint } from './transcriptGeo'

describe('transcriptGeo', () => {
  it('extracts coordinates from common geo payload shapes', () => {
    expect(
      extractTranscriptGeoPoint({
        _geoloc: { lat: 41.88, lng: -87.63 },
        geo_formatted_address: 'Chicago, IL',
      }),
    ).toEqual({
      lat: 41.88,
      lng: -87.63,
      address: 'Chicago, IL',
    })

    expect(
      extractTranscriptGeoPoint({
        coordinates: [-87.65, 41.91],
      }),
    ).toEqual({
      lat: 41.91,
      lng: -87.65,
      address: undefined,
    })

    expect(
      extractTranscriptGeoPoint({
        geo: {
          latitude: '41.9',
          longitude: '-87.7',
        },
      }),
    ).toEqual({
      lat: 41.9,
      lng: -87.7,
      address: undefined,
    })
  })

  it('returns undefined when no coordinates exist', () => {
    expect(extractTranscriptGeoPoint({ geo_formatted_address: 'Chicago, IL' })).toBeUndefined()
  })
})
