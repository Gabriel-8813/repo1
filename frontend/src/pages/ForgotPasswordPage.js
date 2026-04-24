import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Truck, ArrowLeft, Mail, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ForgotPasswordPage = () => {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [devLink, setDevLink] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const r = await axios.post(`${API}/auth/forgot-password`, { email });
      setSent(true);
      // Dev-mode fallback: backend returns dev_reset_link when Resend isn't configured
      if (r.data.dev_reset_link) setDevLink(r.data.dev_reset_link);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not send reset email');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-slate-50 to-blue-50 flex items-center justify-center px-6 py-10" data-testid="forgot-password-page">
      <div className="w-full max-w-md">
        <Link to="/login" className="inline-flex items-center gap-2 text-slate-600 hover:text-blue-600 text-sm mb-6">
          <ArrowLeft className="w-4 h-4" /> Back to login
        </Link>
        <div className="flex items-center gap-2 mb-8">
          <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-6 h-6 text-white" />
          </div>
          <span className="font-archivo font-bold text-xl text-slate-900">MediTrans</span>
        </div>

        {!sent ? (
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
            <CardContent className="p-8">
              <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Forgot your password?</h1>
              <p className="text-slate-600 text-sm mb-6">
                Enter your email and we'll send you a link to reset it.
              </p>
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    required
                    autoComplete="email"
                    data-testid="forgot-email-input"
                  />
                </div>
                <Button
                  type="submit"
                  disabled={submitting || !email}
                  className="w-full bg-blue-600 hover:bg-blue-700 rounded-full py-6"
                  data-testid="send-reset-btn"
                >
                  {submitting ? 'Sending...' : 'Send Reset Link'}
                </Button>
              </form>
            </CardContent>
          </Card>
        ) : (
          <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]" data-testid="forgot-sent-card">
            <CardContent className="p-8 text-center">
              <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-5">
                <Mail className="w-8 h-8 text-emerald-600" />
              </div>
              <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Check your email</h1>
              <p className="text-slate-600 text-sm mb-6">
                If <span className="font-medium">{email}</span> is registered, you'll receive a password reset link shortly. The link expires in 1 hour.
              </p>
              {devLink && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 text-left">
                  <p className="text-xs font-semibold text-amber-700 mb-2 flex items-center gap-1">
                    ⚠️ Dev mode — email provider not configured
                  </p>
                  <p className="text-xs text-slate-600 mb-2">Use this link to reset:</p>
                  <a href={devLink} className="text-xs text-blue-600 break-all underline" data-testid="dev-reset-link">
                    {devLink}
                  </a>
                </div>
              )}
              <Link to="/login">
                <Button variant="outline" className="rounded-full">Back to login</Button>
              </Link>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
