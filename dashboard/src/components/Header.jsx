export default function Header({ title, children }) {
  return (
    <header className="h-16 flex-shrink-0 flex items-center justify-between px-6 border-b border-slate-700 bg-slate-950">
      <h1 className="text-lg font-semibold text-white">{title}</h1>
      {children && (
        <div className="flex items-center gap-3">{children}</div>
      )}
    </header>
  );
}
