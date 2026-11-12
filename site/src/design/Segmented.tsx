type Option<T extends string> = { value: T; label: string }

/** 分段控制（參考設計中的膠囊分頁）。選中項用強調色。 */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  size = 'sm',
}: {
  value: T
  options: Option<T>[]
  onChange: (v: T) => void
  label: string
  size?: 'xs' | 'sm'
}) {
  const pad = size === 'xs' ? 'h-6 px-2 text-2xs' : 'h-7 px-2.5 text-xs'
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-control bg-raised p-0.5">
      {options.map((o) => {
        const active = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={`${pad} rounded-[5px] font-medium transition-colors duration-150 ${
              active ? 'bg-accent text-canvas' : 'text-text-2 hover:text-text-1'
            }`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
