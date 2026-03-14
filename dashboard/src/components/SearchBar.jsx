import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';

export default function SearchBar({
  value: controlledValue,
  onChange,
  onSubmit,
  placeholder = 'Search...',
}) {
  const [internalValue, setInternalValue] = useState('');
  const value = controlledValue !== undefined ? controlledValue : internalValue;
  const inputRef = useRef(null);

  useEffect(() => {
    function handleKeyDown(e) {
      if (
        e.key === '/' &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes(
          document.activeElement.tagName
        )
      ) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  function handleChange(newValue) {
    if (controlledValue !== undefined) {
      onChange?.(newValue);
    } else {
      setInternalValue(newValue);
      onChange?.(newValue);
    }
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit?.(value);
  }

  return (
    <form onSubmit={handleSubmit} className="relative w-full max-w-md">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-prd-text-secondary pointer-events-none" />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        className="w-full pl-10 pr-16 py-2 bg-prd-bg border border-prd-border rounded-md text-sm text-prd-text-primary placeholder-prd-text-secondary focus:outline-none focus:ring-1 focus:ring-prd-tool focus:border-prd-tool transition-colors"
      />
      <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
        {value ? (
          <button
            type="button"
            onClick={() => handleChange('')}
            className="p-0.5 text-prd-text-secondary hover:text-prd-text-primary transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        ) : (
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-prd-text-secondary bg-prd-surface rounded border border-prd-border">
            /
          </kbd>
        )}
      </div>
    </form>
  );
}
