import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Truck, LogOut, Radio } from 'lucide-react';

export default function DispatchHomePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="dispatch-home">
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-5 h-5 text-white" />
          </div>
          <span className="font-archivo font-bold text-lg text-slate-900">MediTrans</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-600" data-testid="role-home-user-name">
            {user?.full_name} <span className="text-slate-400">({user?.role})</span>
          </span>
          <Button variant="outline" size="sm" onClick={handleLogout} data-testid="role-home-logout-btn">
            <LogOut className="w-4 h-4 mr-1" /> Sign out
          </Button>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-24 text-center">
        <div className="w-16 h-16 bg-blue-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
          <Radio className="w-8 h-8 text-blue-600" />
        </div>
        <h1 className="font-archivo font-bold text-3xl text-slate-900 mb-3">Dispatch Console</h1>
        <p className="text-slate-600 text-base">
          Your dispatch console is coming soon. From here you'll see every job across the network, assign verified drivers, and monitor deliveries live.
        </p>
      </main>
    </div>
  );
}
