import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Truck, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function DeleteAccountPage() {
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirmText, setConfirmText] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await axios.post(`${API}/auth/delete-account`, { password }, { headers: { Authorization: `Bearer ${token}` } });
      toast.success('Your account has been deleted.');
      logout();
      navigate('/');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not delete account');
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-10" data-testid="delete-account-page">
      <div className="max-w-lg mx-auto">
        <Link to="/" className="flex items-center gap-2 mb-8">
          <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center"><Truck className="w-6 h-6 text-white" /></div>
          <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
        </Link>
        <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Delete your account</h1>
        <p className="text-sm text-slate-600 mb-6">
          Deleting your account permanently removes your name, email, phone number and profile.
          Chain-of-custody and audit records for completed deliveries are kept in de-identified form,
          as required for legal and billing compliance.
        </p>
        <Card className="border border-red-200">
          <CardContent className="p-6">
            {user ? (
              <form onSubmit={submit} className="space-y-4">
                <div className="flex items-start gap-2 text-red-700 text-sm bg-red-50 rounded-lg p-3">
                  <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" /> This cannot be undone. Signed in as {user.email}.
                </div>
                <Input type="password" required placeholder="Confirm your password" value={password}
                  onChange={(e) => setPassword(e.target.value)} data-testid="delete-password-input" />
                <Input required placeholder='Type DELETE to confirm' value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)} data-testid="delete-confirm-input" />
                <Button type="submit" disabled={busy || confirmText !== 'DELETE' || !password}
                  className="w-full bg-red-600 hover:bg-red-700 rounded-full" data-testid="delete-account-btn">
                  {busy ? 'Deleting…' : 'Permanently delete my account'}
                </Button>
              </form>
            ) : (
              <div className="text-sm text-slate-600 space-y-3">
                <p><Link to="/login" className="text-blue-600 underline">Sign in</Link> to delete your account directly, or email
                  <span className="font-medium"> support@meditranscanada.com</span> from your registered address and we will
                  process the deletion within 30 days.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
