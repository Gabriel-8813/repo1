import React, { useState, useEffect } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Truck, CheckCircle, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ResetPasswordPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [missingToken, setMissingToken] = useState(false);

  useEffect(() => {
    const t = searchParams.get('token');
    if (!t) {
      setMissingToken(true);
      return;
    }
    setToken(t);
  }, [searchParams]);

  const submit = async (e) => {
    e.preventDefault();
    if (password !== confirm) {
      toast.error('Passwords do not match');
      return;
    }
    if (password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/auth/reset-password`, { token, new_password: password });
      setDone(true);
      setTimeout(() => navigate('/login'), 3000);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not reset password');
    } finally {
      setSubmitting(false);
    }
  };

  if (missingToken) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-6">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center">
            <div className="w-14 h-14 rounded-full bg-amber-100 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-7 h-7 text-amber-600" />
            </div>
            <h1 className="font-archivo font-bold text-xl text-slate-900 mb-2">Invalid reset link</h1>
            <p className="text-slate-600 text-sm mb-6">This page needs a valid reset token. Request a new link from the login page.</p>
            <Link to="/forgot-password"><Button variant="outline">Request new link</Button></Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-slate-50 to-blue-50 flex items-center justify-center px-6 py-10" data-testid="reset-password-page">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-2 mb-8">
          <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-6 h-6 text-white" />
          </div>
          <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
        </div>

        {done ? (
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]" data-testid="reset-done-card">
            <CardContent className="p-8 text-center">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-5">
                <CheckCircle className="w-8 h-8 text-emerald-600" />
              </div>
              <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Password updated</h1>
              <p className="text-slate-600 text-sm mb-6">You'll be redirected to the login page in a moment.</p>
              <Link to="/login"><Button className="bg-blue-600 hover:bg-blue-700 rounded-full">Log in now</Button></Link>
            </CardContent>
          </Card>
        ) : (
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-8">
              <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Set a new password</h1>
              <p className="text-slate-600 text-sm mb-6">Choose a strong password of at least 8 characters.</p>
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label htmlFor="new-pwd">New password</Label>
                  <Input
                    id="new-pwd"
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                    data-testid="reset-new-password-input"
                  />
                </div>
                <div>
                  <Label htmlFor="confirm-pwd">Confirm new password</Label>
                  <Input
                    id="confirm-pwd"
                    type="password"
                    value={confirm}
                    onChange={e => setConfirm(e.target.value)}
                    required
                    autoComplete="new-password"
                    data-testid="reset-confirm-password-input"
                  />
                </div>
                <Button
                  type="submit"
                  disabled={submitting || !password || !confirm}
                  className="w-full bg-blue-600 hover:bg-blue-700 rounded-full py-6"
                  data-testid="reset-submit-btn"
                >
                  {submitting ? 'Updating...' : 'Update Password'}
                </Button>
              </form>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default ResetPasswordPage;
