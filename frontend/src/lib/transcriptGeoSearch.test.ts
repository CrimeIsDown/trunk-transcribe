import { describe, expect, it } from 'vitest'

import { formatInsideBoundingBox } from './transcriptGeoSearch'

describe('transcriptGeoSearch', () => {
  it('formats map bounds for insideBoundingBox search parameters', () => {
    expect(
      formatInsideBoundingBox({
        getSouth: () => 41.5,
        getWest: () => -88.1,
        getNorth: () => 42.05,
        getEast: () => -87.3,
      }),
    ).toBe('41.5,-88.1,42.05,-87.3')
  })
})
