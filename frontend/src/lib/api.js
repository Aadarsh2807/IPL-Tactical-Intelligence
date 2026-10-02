/**
 * One HTTP client for the whole app.
 *
 * Every previous component had its own copy of the fetch wrapper, and none of
 * them cancelled in-flight requests, so a fast season change could paint the
 * previous season's teams. `useResource` fixes both problems in one place.
 */
import { useEffect, useState } from 'react'

async function request(path, { method = 'GET', body, signal } = {}) {
  const options = { method, signal }
  if (body !== undefined) {
    options.headers = { 'Content-Type': 'application/json' }
    options.body = JSON.stringify(body)
  }
  const response = await fetch(path, options)

  const text = await response.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = null
    }
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed (${response.status})`)
  }
  return payload
}

export const get = (path, options) => request(path, options)
export const post = (path, body, options = {}) =>
  request(path, { ...options, method: 'POST', body })

/** Fetch whenever `path` changes, cancelling the previous request. */
export function useResource(path) {
  const [state, setState] = useState({ data: null, error: '', loading: Boolean(path) })

  useEffect(() => {
    if (!path) {
      setState({ data: null, error: '', loading: false })
      return undefined
    }
    const controller = new AbortController()
    setState({ data: null, error: '', loading: true })
    get(path, { signal: controller.signal })
      .then(data => setState({ data, error: '', loading: false }))
      .catch(error => {
        if (error.name === 'AbortError') return
        setState({ data: null, error: error.message, loading: false })
      })
    return () => controller.abort()
  }, [path])

  return state
}

export const encode = encodeURIComponent
