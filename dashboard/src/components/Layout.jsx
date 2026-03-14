import { Outlet } from 'react-router-dom';
import Header from './Header.jsx';
import Sidebar from './Sidebar.jsx';
import StatusBar from './StatusBar.jsx';

export default function Layout() {
  return (
    <div className="flex flex-col h-screen bg-prd-bg text-prd-text-primary font-sans">
      <Header />
      <div className="flex flex-1 min-h-0">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <Outlet />
        </main>
      </div>
      <StatusBar />
    </div>
  );
}
