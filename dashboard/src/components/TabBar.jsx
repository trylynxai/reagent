export default function TabBar({ tabs, activeTab, onChange }) {
  return (
    <div className="flex border-b border-prd-border">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
            activeTab === tab.id
              ? 'text-prd-tool border-prd-tool'
              : 'text-prd-text-secondary border-transparent hover:text-prd-text-primary hover:border-prd-border'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
