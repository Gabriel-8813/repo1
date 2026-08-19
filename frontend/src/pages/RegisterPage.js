import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth, roleHome } from '../context/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent } from '../components/ui/card';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Badge } from '../components/ui/badge';
import { Truck, AlertCircle, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';

const RegisterPage = () => {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    full_name: '',
    phone: ''
  });
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (formData.password !== formData.confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (formData.password.length < 6) {
      setError('Password must be at least 6 characters');
      return;
    }

    if (!privacyAccepted) {
      setError('You must accept the privacy policy to create an account');
      return;
    }

    setLoading(true);

    try {
      const userData = await register(formData.email, formData.password, formData.full_name, formData.phone);
      toast.success('Registration successful! Welcome to MediTrans.');
      navigate(roleHome(userData));
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 py-12 px-6">
      <div className="max-w-xl mx-auto">
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-2 mb-6">
            <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center">
              <Truck className="w-7 h-7 text-white" />
            </div>
            <span className="font-archivo font-bold text-2xl text-slate-900">MediTrans</span>
          </Link>
          <h1 className="font-archivo font-bold text-3xl text-slate-900">Become a Driver</h1>
          <p className="text-slate-600 mt-2">Join Ontario's medical transport network</p>
        </div>

        <Card className="border-0 shadow-[0_4px_20px_rgba(0,0,0,0.08)]">
          <CardContent className="p-8">
            {/* Requirements reminder */}
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
              <h3 className="font-semibold text-amber-800 mb-2">Requirements to drive:</h3>
              <ul className="text-sm text-amber-700 space-y-1">
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" /> Valid Ontario Driver's License
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" /> CVOR Certificate (or willingness to obtain)
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" /> Commercial Vehicle Insurance
                </li>
              </ul>
            </div>

            {error && (
              <Alert variant="destructive" className="mb-6">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="full_name">Full Name</Label>
                <Input
                  id="full_name"
                  name="full_name"
                  type="text"
                  placeholder="John Smith"
                  value={formData.full_name}
                  onChange={handleChange}
                  required
                  className="h-12"
                  data-testid="register-name-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="email">Email Address</Label>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="driver@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  required
                  className="h-12"
                  data-testid="register-email-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="phone">Phone Number</Label>
                <Input
                  id="phone"
                  name="phone"
                  type="tel"
                  placeholder="+1 (416) 555-0123"
                  value={formData.phone}
                  onChange={handleChange}
                  required
                  className="h-12"
                  data-testid="register-phone-input"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    name="password"
                    type="password"
                    placeholder="••••••••"
                    value={formData.password}
                    onChange={handleChange}
                    required
                    className="h-12"
                    data-testid="register-password-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirmPassword">Confirm Password</Label>
                  <Input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    placeholder="••••••••"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    required
                    className="h-12"
                    data-testid="register-confirm-password-input"
                  />
                </div>
              </div>

              <label className="flex items-start gap-2 cursor-pointer bg-slate-50 rounded-lg px-3 py-2.5">
                <input type="checkbox" className="mt-0.5 accent-blue-600" checked={privacyAccepted} onChange={(e) => setPrivacyAccepted(e.target.checked)} data-testid="privacy-accept-checkbox" />
                <span className="text-xs text-slate-600">
                  I have read and accept the <a href="/privacy" target="_blank" className="text-blue-600 underline font-semibold">MediTrans Privacy Policy</a>, including how personal and health-adjacent information is collected, protected and retained.
                </span>
              </label>

              <div className="pt-2">
                <Button
                  type="submit"
                  className="w-full h-12 bg-blue-600 hover:bg-blue-700 rounded-full text-lg"
                  disabled={loading}
                  data-testid="register-submit-btn"
                >
                  {loading ? 'Creating Account...' : 'Create Account'}
                </Button>
              </div>
            </form>

            <div className="mt-6 text-center">
              <p className="text-slate-600">
                Already have an account?{' '}
                <Link to="/login" className="text-blue-600 hover:text-blue-700 font-medium">
                  Sign in
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>

        <p className="text-center text-slate-500 text-sm mt-8">
          By registering, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  );
};

export default RegisterPage;
