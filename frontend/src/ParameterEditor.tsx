import styles from './App.module.css'

type ValueType = 'text' | 'number' | 'boolean' | 'null' | 'object' | 'array'

export type Parameter = {
  id: string
  name: string
  type: ValueType
  value: string
  children: Parameter[]
}

// oxlint-disable-next-line react/only-export-components -- Keep conversion beside the editor's draft model.
export function readParameters(parameters: Parameter[]): Record<string, unknown> {
  function readObject(fields: Parameter[], path: string): Record<string, unknown> {
    const names = new Set<string>()
    return Object.fromEntries(fields.map((field) => {
      if (!field.name.trim()) throw new Error(`${path}: each parameter needs a name.`)
      if (names.has(field.name)) throw new Error(`${path}: duplicate parameter name "${field.name}".`)
      names.add(field.name)
      return [field.name, readValue(field, `${path}.${field.name}`)]
    }))
  }

  function readValue(field: Parameter, path: string): unknown {
    switch (field.type) {
      case 'text': return field.value
      case 'boolean': return field.value === 'true'
      case 'null': return null
      case 'object': return readObject(field.children, path)
      case 'array': return field.children.map((child, index) => readValue(child, `${path}[${index}]`))
      case 'number': {
        const number = Number(field.value)
        if (!/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(field.value) || !Number.isFinite(number)) {
          throw new Error(`${path}: enter a finite number, for example 3 or -1.5.`)
        }
        return number
      }
    }
  }

  return readObject(parameters, 'Parameters')
}

export function ParameterEditor({ parameters, onChange, array = false, path = 'Parameters' }: {
  parameters: Parameter[]
  onChange: (parameters: Parameter[]) => void
  array?: boolean
  path?: string
}) {
  function update(id: string, changes: Partial<Parameter>) {
    onChange(parameters.map((parameter) => parameter.id === id ? { ...parameter, ...changes } : parameter))
  }

  return <div className={styles.parameterList}>
    {parameters.length === 0 && <p>{array ? 'No items. This list will be empty.' : 'No parameters. This object will be empty.'}</p>}
    {parameters.map((parameter, index) => {
      const title = `${path} ${index + 1}`
      return <fieldset key={parameter.id} className={styles.parameterRow}>
        <legend>{title}</legend>
        <div className={styles.parameterControls}>
          {!array && <div>
            <label htmlFor={`${parameter.id}-name`}>Name</label>
            <input id={`${parameter.id}-name`} aria-label={`Name for ${title}`} value={parameter.name}
              onChange={(event) => update(parameter.id, { name: event.target.value })} />
          </div>}
          <div>
            <label htmlFor={`${parameter.id}-type`}>Type</label>
            <select id={`${parameter.id}-type`} aria-label={`Type for ${title}`} value={parameter.type}
              onChange={(event) => update(parameter.id, {
                type: event.target.value as ValueType, value: event.target.value === 'boolean' ? 'false' : '', children: [],
              })}>
              <option value="text">Text</option>
              <option value="number">Number</option>
              <option value="boolean">Boolean</option>
              <option value="null">Null</option>
              <option value="object">Object</option>
              <option value="array">List</option>
            </select>
          </div>
        </div>
        {parameter.type === 'object' || parameter.type === 'array' ? <ParameterEditor
          parameters={parameter.children} onChange={(children) => update(parameter.id, { children })}
          array={parameter.type === 'array'} path={`${title} ${parameter.type === 'array' ? 'items' : 'fields'}`} />
          : parameter.type === 'null' ? <p>This value is null.</p> : <div>
            <label htmlFor={`${parameter.id}-value`}>Value</label>
            {parameter.type === 'boolean' ? <select id={`${parameter.id}-value`} aria-label={`Value for ${title}`} value={parameter.value}
              onChange={(event) => update(parameter.id, { value: event.target.value })}>
              <option value="false">False</option>
              <option value="true">True</option>
            </select> : parameter.type === 'text' ? <textarea id={`${parameter.id}-value`} rows={2}
              aria-label={`Value for ${title}`} value={parameter.value}
              onChange={(event) => update(parameter.id, { value: event.target.value })} />
              : <input id={`${parameter.id}-value`} aria-label={`Value for ${title}`} inputMode="decimal"
                value={parameter.value} onChange={(event) => update(parameter.id, { value: event.target.value })} />}
          </div>}
        <div><button type="button" aria-label={`Remove ${title}`}
          onClick={() => onChange(parameters.filter(({ id }) => id !== parameter.id))}>
          {array ? 'Remove item' : 'Remove parameter'}
        </button></div>
      </fieldset>
    })}
    <div><button type="button" aria-label={`Add ${array ? 'item' : 'parameter'} to ${path}`}
      onClick={() => onChange([...parameters, { id: crypto.randomUUID(), name: '', type: 'text', value: '', children: [] }])}>
      {array ? 'Add item' : 'Add parameter'}
    </button></div>
  </div>
}
