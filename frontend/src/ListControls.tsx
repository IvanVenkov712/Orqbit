import { Fragment, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Icon } from './Icon'
import styles from './App.module.css'

export type ListOption = { value: string; label: string }
export type ListFilter = { key: string; label: string; placeholder?: string; type?: string; maxLength?: number; options?: ListOption[] }

export function ListControls({ resource, filters, sorts, defaultSort, groups, children }: {
  resource: 'jobs' | 'workers'; filters: ListFilter[]; sorts: ListOption[]; defaultSort: string; groups: ListOption[]; children?: ReactNode
}) {
  const [params, setParams] = useSearchParams()
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => { if (open) panel.current?.querySelector<HTMLInputElement>('input, select')?.focus() }, [open])
  const filterKey = filters.map(({ key }) => `${key}:${params.get(key) ?? ''}`).join('|')
  const applied = filters.filter(({ key }) => params.has(key) && params.get(key) !== '')
  const sort = sorts.some(({ value }) => value === params.get('sort')) ? params.get('sort')! : defaultSort
  const group = groups.some(({ value }) => value === params.get('group')) ? params.get('group')! : ''
  const clear = new URLSearchParams(params)
  filters.forEach(({ key }) => clear.delete(key))
  clear.delete('offset')

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'group') next.delete('offset')
    setParams(next)
  }

  function close() { panel.current?.querySelector('form')?.reset(); setOpen(false); trigger.current?.focus() }

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const next = new URLSearchParams(params)
    for (const { key } of filters) {
      const value = String(form.get(key) ?? '')
      if (value) next.set(key, value)
      else next.delete(key)
    }
    next.delete('offset')
    setParams(next)
    close()
  }

  function setRecentRange(days: number) {
    const now = Date.now()
    for (const [name, instant] of [['created_from', now - days * 86_400_000], ['created_before', now]] as const) {
      const input = panel.current?.querySelector<HTMLInputElement>(`[name="${name}"]`)
      const date = new Date(instant)
      if (input) input.value = new Date(instant - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 19)
    }
  }

  return <>
    <div className={styles.listToolbar}>
      <div className={styles.toolbarStart}>
        <button ref={trigger} className={styles.controlButton} type="button" aria-expanded={open}
          aria-controls={`${resource}-filters`} onClick={() => open ? close() : setOpen(true)}><Icon name="filter" /> Filters
          {applied.length > 0 && <span className={styles.countBadge} aria-hidden="true">{applied.length}</span>}
        </button>
        {children}
      </div>
      <div className={styles.viewControls}>
        <label className={styles.selectControl}><Icon name="sort" /><span className={styles.srOnly}>Sort {resource}</span>
          <select value={sort} onChange={(event) => update('sort', event.target.value)}>
            {sorts.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className={styles.selectControl}><Icon name="group" /><span className={styles.srOnly}>Group {resource}</span>
          <select value={group} onChange={(event) => update('group', event.target.value)}>
            <option value="">No grouping</option>
            {groups.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>
    </div>
    <div ref={panel} id={`${resource}-filters`} hidden={!open} className={styles.filterPanel} onKeyDown={(event) => { if (event.key === 'Escape') close() }}>
      <div className={styles.panelHeading}><div><h2>Filter {resource}</h2><p>Narrow down the entire collection.</p></div>
        <button className={styles.iconButton} type="button" aria-label="Close filters" onClick={close}><Icon name="close" /></button>
      </div>
      <form key={filterKey} onSubmit={apply} aria-label={`Filter ${resource}`}>
        <div className={styles.dateShortcuts}><span>Created within</span>
          <button className={styles.controlButton} type="button" onClick={() => setRecentRange(1)}>Last 24 hours</button>
          <button className={styles.controlButton} type="button" onClick={() => setRecentRange(7)}>Last 7 days</button>
          <button className={styles.controlButton} type="button" onClick={() => setRecentRange(30)}>Last 30 days</button>
        </div>
        <div className={`${styles.authFields} ${styles.filters}`}>
          {filters.map(({ key, label, placeholder, type, maxLength, options }) => {
            let inputValue = params.get(key) ?? ''
            if (type === 'datetime-local' && inputValue && !Number.isNaN(Date.parse(inputValue))) {
              const date = new Date(inputValue)
              inputValue = new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 19)
            }
            return <div key={key}>
              <label htmlFor={`${resource}-${key}`}>{label}</label>
              {options ? <select id={`${resource}-${key}`} name={key} defaultValue={params.get(key) ?? ''}>
                <option value="">All statuses</option>{options.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
              </select> : <input id={`${resource}-${key}`} name={key} type={type ?? 'text'} step={type === 'datetime-local' ? '1' : undefined}
                maxLength={maxLength} placeholder={placeholder} defaultValue={inputValue} />}
            </div>
          })}
        </div>
        <div className={styles.filterFooter}><small>Exact owner and type. Dates use local time; “before” is exclusive.</small>
          <div className={styles.inlineActions}><button className={styles.controlButton} type="button" onClick={close}>Cancel</button><button type="submit">Apply filters</button></div>
        </div>
      </form>
    </div>
    {applied.length > 0 && <div className={styles.filterChips} aria-label="Active filters">
      {applied.map(({ key, label, options }) => <button key={key} className={styles.filterChip} type="button"
        aria-label={`Remove ${label.toLowerCase()} filter`} onClick={() => update(key, '')}>
        <span>{label}: <strong>{options?.find(({ value }) => value === params.get(key))?.label ?? params.get(key)}</strong></span><Icon name="close" size={13} />
      </button>)}
      <Link to={`/${resource}${clear.size ? `?${clear}` : ''}`}>Clear filters</Link>
    </div>}
    {group && <p className={styles.groupNotice}><Icon name="group" size={14} /> Groups and counts reflect this page. Sorting applies to all matching records.</p>}
  </>
}

export function SortHeading({ label, ascending, descending, current, onSort }: {
  label: string; ascending: string; descending: string; current: string; onSort: (sort: string) => void
}) {
  const active = current === ascending || current === descending
  return <th scope="col" aria-sort={active ? current === ascending ? 'ascending' : 'descending' : 'none'}>
    <button className={styles.columnSort} type="button" onClick={() => onSort(current === ascending ? descending : ascending)}>
      {label}<span aria-hidden="true" className={active ? styles.sortActive : styles.sortHint}>{active ? current === ascending ? '↑' : '↓' : '↕'}</span>
    </button>
  </th>
}

export function GroupedRows<T extends { id: number }>({ items, group, groupLabel, columns, renderRow }: {
  items: T[]; group: string; groupLabel: (item: T) => string; columns: number; renderRow: (item: T) => ReactNode
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  if (!group) return <tbody>{items.map(renderRow)}</tbody>
  const buckets = new Map<string, T[]>()
  items.forEach((item) => { const label = groupLabel(item); buckets.set(label, [...(buckets.get(label) ?? []), item]) })
  return <>{[...buckets].map(([label, rows]) => <tbody key={label} aria-label={`${label} group`}>
    <tr className={styles.groupRow}><th scope="rowgroup" colSpan={columns}>
      <button type="button" aria-expanded={!collapsed.has(label)} onClick={() => setCollapsed((previous) => {
        const next = new Set(previous)
        if (next.has(label)) next.delete(label)
        else next.add(label)
        return next
      })}><Icon name="chevron" size={14} style={{ transform: collapsed.has(label) ? undefined : 'rotate(90deg)' }} />
        {label}<span className={styles.countBadge}>{rows.length}</span>
      </button>
    </th></tr>
    {!collapsed.has(label) && rows.map((item) => <Fragment key={item.id}>{renderRow(item)}</Fragment>)}
  </tbody>)}</>
}
