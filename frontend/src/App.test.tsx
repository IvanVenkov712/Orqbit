// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test } from 'vitest'
import App from './App'
import orqbitIcon from './assets/orqbit-icon.svg'
import { fetchMock, enterApp, setupAppTests } from './tests/app-test-utils'

setupAppTests()

test('requires login by default and shows the signed-out user area', () => {
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
  expect(window.location.pathname).toBe('/login')
  expect(screen.getByRole('group', { name: 'Current user' }).textContent).toContain('Not signed in')
  expect(fetchMock).not.toHaveBeenCalled()
})

test.each(['/login', '/register'])('uses the Orqbit icon on %s without session implementation text', (path) => {
  window.history.replaceState(null, '', path)
  render(<App />)
  const brandIcon = screen.getByRole('link', { name: 'Orqbit home' }).querySelector('img')
  expect(brandIcon?.getAttribute('src')).toBe(orqbitIcon)
  expect(document.querySelector('main img')?.getAttribute('src')).toBe(brandIcon?.getAttribute('src'))
  expect(screen.queryByText(/Your session stays in memory/)).toBeNull()
})

test.each(['/jobs', '/jobs/new', '/jobs/42', '/jobs/42/attempts', '/workers', '/workers/new', '/workers/17'])(
  'protects direct entry to %s', (path) => {
    window.history.replaceState(null, '', path)
    render(<App />)
    expect(window.location.pathname).toBe('/login')
    expect(screen.queryByText('Planned screen')).toBeNull()
  },
)

test('navigates between Jobs and Workers and follows browser back/forward', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Workers' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Workers' })).toBeTruthy()
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
  ['/jobs/42/attempts', 'Attempt history', 'Jobs'],
  ['/workers', 'Workers', 'Workers'],
  ['/workers/new', 'Register a worker', 'Workers'],
  ['/workers/17', 'Worker details', 'Workers'],
])('restores %s after login and highlights its section', async (path, title, activeLink) => {
  await enterApp(path)
  expect(screen.getByRole('heading', { level: 1, name: title })).toBeTruthy()
  if (path === '/jobs/new') {
    expect(screen.queryByText('Planned screen')).toBeNull()
    expect(screen.getByRole('form', { name: 'Submit a job' })).toBeTruthy()
  } else if (path === '/jobs/42') {
    expect(screen.queryByText('Planned screen')).toBeNull()
    expect(await screen.findByRole('region', { name: 'Job overview' })).toBeTruthy()
  } else if (path === '/jobs') {
    expect(await screen.findByRole('table', { name: 'Submitted jobs' })).toBeTruthy()
  } else if (path === '/jobs/42/attempts') {
    expect(await screen.findByRole('region', { name: 'Execution attempts' })).toBeTruthy()
  } else if (path === '/workers') {
    expect(await screen.findByRole('table', { name: 'Registered workers' })).toBeTruthy()
  } else if (path === '/workers/new') {
    expect(screen.getByRole('form', { name: 'Register a worker' })).toBeTruthy()
  } else {
    expect(await screen.findByRole('region', { name: 'Worker metadata' })).toBeTruthy()
  }
  expect(screen.queryByText(/frontend roadmap|does not load live data|Refreshes every/)).toBeNull()
  expect(screen.getByRole('link', { name: activeLink }).getAttribute('aria-current')).toBe('page')
})

test('offers recovery from an unknown route', async () => {
  window.history.replaceState(null, '', '/missing/page')
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: 'Page not found' })).toBeTruthy()
  fireEvent.click(screen.getByRole('link', { name: 'Back to Jobs' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeTruthy()
})

test('links to job submission after authentication', async () => {
  await enterApp()
  fireEvent.click(screen.getByRole('link', { name: 'Submit a job' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'Submit a job' })).toBeTruthy()
})
