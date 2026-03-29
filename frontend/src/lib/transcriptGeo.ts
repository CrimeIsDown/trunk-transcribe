export interface TranscriptGeoPoint {
  lat: number
  lng: number
  address?: string
}

function toFiniteNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim()) {
    const parsed = Number.parseFloat(value)
    return Number.isFinite(parsed) ? parsed : undefined
  }

  return undefined
}

function parseGeoCoordinates(value: unknown): { lat: number; lng: number } | undefined {
  if (Array.isArray(value) && value.length >= 2) {
    const lng = toFiniteNumber(value[0])
    const lat = toFiniteNumber(value[1])
    if (lat !== undefined && lng !== undefined) {
      return { lat, lng }
    }
    return undefined
  }

  if (typeof value !== 'object' || value === null) {
    return undefined
  }

  const candidate = value as Record<string, unknown>
  const lat = toFiniteNumber(candidate.lat ?? candidate.latitude)
  const lng = toFiniteNumber(candidate.lng ?? candidate.lon ?? candidate.longitude)
  if (lat !== undefined && lng !== undefined) {
    return { lat, lng }
  }

  if ('coordinates' in candidate) {
    return parseGeoCoordinates(candidate.coordinates)
  }

  if ('_geoloc' in candidate) {
    return parseGeoCoordinates(candidate._geoloc)
  }

  return undefined
}

export function extractTranscriptGeoPoint(
  hit: Record<string, unknown>,
): TranscriptGeoPoint | undefined {
  const candidates = [hit._geoloc, hit.geo, hit.location, hit.coordinates, hit.position]
  for (const candidate of candidates) {
    const point = parseGeoCoordinates(candidate)
    if (point) {
      return {
        ...point,
        address:
          typeof hit.geo_formatted_address === 'string'
            ? hit.geo_formatted_address
            : undefined,
      }
    }
  }

  return undefined
}
