'use client'

import { useEffect, useState } from 'react'
import { Col, Row } from 'react-bootstrap'
import { FaCalendar } from 'react-icons/fa'
import { useRange } from 'react-instantsearch'

import {
  clampTranscriptSearchRangeToMonth,
  type TranscriptSearchIndexConfig,
} from '@/lib/transcriptSearchIndex'
import {
  epochSecondsToLocalDateTimeValue,
  toEpochSeconds,
} from '@/lib/searchState'

type CallTimeRangeFilterProps = {
  archiveConfig?: TranscriptSearchIndexConfig
}

export default function CallTimeRangeFilter({
  archiveConfig,
}: CallTimeRangeFilterProps) {
  const { start, refine } = useRange({
    attribute: 'start_time',
  })

  const [minValue, setMinValue] = useState('')
  const [maxValue, setMaxValue] = useState('')

  useEffect(() => {
    setMinValue(epochSecondsToLocalDateTimeValue(start[0]))
  }, [start[0]])

  useEffect(() => {
    setMaxValue(epochSecondsToLocalDateTimeValue(start[1]))
  }, [start[1]])

  const updateRange = (nextMinValue: string, nextMaxValue: string) => {
    const nextMin = toEpochSeconds(nextMinValue)
    const nextMax = toEpochSeconds(nextMaxValue)
    const nextRange = `${nextMin ?? ''}:${nextMax ?? ''}`

    if (archiveConfig?.splitByMonth && nextMin !== undefined) {
      const clampedRange = clampTranscriptSearchRangeToMonth(nextRange)
      if (clampedRange) {
        const [clampedMin, clampedMax] = clampedRange.split(':', 2)
        const clampedMinValue = Number.parseInt(clampedMin || '', 10)
        const clampedMaxValue = Number.parseInt(clampedMax || '', 10)
        refine([
          Number.isFinite(clampedMinValue) ? clampedMinValue : undefined,
          Number.isFinite(clampedMaxValue) ? clampedMaxValue : undefined,
        ])
      }
      return
    }

    refine([nextMin, nextMax])
  }

  return (
    <Row>
      <Col>
        <label htmlFor="minStartTime">From Time</label>
        <div className="input-group date">
          <input
            type="datetime-local"
            id="minStartTime"
            className="form-control"
            value={minValue}
            onChange={(event) => {
              const nextValue = event.target.value
              setMinValue(nextValue)
              updateRange(nextValue, maxValue)
            }}
          />
          <span className="input-group-text">
            <FaCalendar />
          </span>
        </div>
      </Col>
      <Col>
        <label htmlFor="maxStartTime">To Time</label>
        <div className="input-group date">
          <input
            type="datetime-local"
            id="maxStartTime"
            className="form-control"
            value={maxValue}
            onChange={(event) => {
              const nextValue = event.target.value
              setMaxValue(nextValue)
              updateRange(minValue, nextValue)
            }}
          />
          <span className="input-group-text">
            <FaCalendar />
          </span>
        </div>
      </Col>
    </Row>
  )
}
