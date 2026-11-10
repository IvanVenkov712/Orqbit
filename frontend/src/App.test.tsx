// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import App from './App'

afterEach(cleanup)

test('opens Jobs by default and shows the signed-out user area', async () => {
  window.history.replaceState(null, '', '/')
  render(<App />)

  expect(await screen.findByRole('heading', { level: 1, name: 'Jobs' })).toBeTruthy()
  expect(window.location.pathname).toBe('/jobs')
  expect(screen.getByRole('link', { name: 'Jobs' }).getAttribute('aria-current')).toBe('page')
  expect(screen.getByRole('group', { name: 'Current user' }).textContent).toContain('Not signed in')
})

test('navigates between Jobs and Workers and follows browser back/forward', async () => {
  window.history.replaceState(null, '', '/jobs')
  render(<App />)

  fireEvent.click(screen.getByRole('link', { name: 'Workers' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Workers' })).toBeTruthy()
  expect(window.location.pathname).toBe('/workers')
  expect(screen.getByRole('link', { name: 'Workers' }).getAttribute('aria-current')).toBe('page')
  expect(screen.getByRole('link', { name: 'Jobs' }).hasAttribute('aria-current')).toBe(false)

  await act(async () => { window.history.back() })
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Jobs'))

  await act(async () => { window.history.forward() })
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Workers'))
})

test.each([
  ['/jobs', 'Jobs', 'Jobs'],
  ['/jobs/new', 'Submit a job', 'Jobs'],
  ['/jobs/42', 'Job details', 'Jobs'],
  ['/workers', 'Workers', 'Workers'],
  ['/workers/17', 'Worker details', 'Workers'],
  ['/login', 'Sign in', null],
  ['/register', 'Create an account', null],
])('loads %s directly with an explicit placeholder', (path, title, activeLink) => {
  window.history.replaceState(null, '', path)
  render(<App />)

  expect(screen.getByRole('heading', { level: 1, name: title })).toBeTruthy()
  expect(screen.getByText('Planned screen')).toBeTruthy()
  expect(screen.getByText('No account or live data is connected yet.')).toBeTruthy()
  if (activeLink) {
    expect(screen.getByRole('link', { name: activeLink }).getAttribute('aria-current')).toBe('page')
  }
})

test('offers recovery from an unknown route', async () => {
  window.history.replaceState(null, '', '/missing/page')
  render(<App />)

  expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
  fireEvent.click(screen.getByRole('link', { name: 'Back to Jobs' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Jobs' })).toBeTruthy()
})

test('links to submission and authentication placeholders', async () => {
  window.history.replaceState(null, '', '/jobs')
  render(<App />)

  fireEvent.click(screen.getByRole('link', { name: 'Preview job submission' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Submit a job' })).toBeTruthy()
  fireEvent.click(screen.getByRole('link', { name: 'Sign in' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  fireEvent.click(screen.getByRole('link', { name: 'Preview registration' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Create an account' })).toBeTruthy()
})
